"""I pasti consumati vanno a healthAI, il server dei dati di salute dell'amministratore.

healthAI incrocia l'alimentazione con allenamenti, sonno e recupero, e la legge Claude
dal suo server MCP. DietAI non scrive in Apple Salute: questo è l'unico canale.

**Non è una coda di azioni, è un confronto di stati.** Un pasto si segna, si
corregge, si desegna, cambia ricetta, cambia giorno; le strade che lo toccano sono una
dozzina (seguito, «ho mangiato altro», la chat, la sostituzione, il cestino, la
rigenerazione, il cambio di dieta...) e agganciare un invio a ognuna vorrebbe dire
dimenticarne una alla prima rotta nuova. Qui invece un giro (`sync`, ogni minuto, nel
thread di `start_scheduler`) guarda cosa dice **adesso** ogni pasto degli ultimi
`HEALTHAI_DAYS` giorni, lo confronta con l'impronta di quello che healthAI ha
(`HealthSync.sent_hash`), e manda solo la differenza:

- pasto consumato con un payload diverso da quello inviato → POST (healthAI fa upsert
  su `external_meal_id`, quindi è anche la modifica);
- pasto non più consumato, o cancellato, ma presente su healthAI → DELETE.

Così l'ordine è giusto per costruzione: un POST vecchio non può arrivare dopo una
DELETE, perché il POST vecchio non esiste più — esiste solo lo stato di adesso.

**Cosa vuol dire "consumato"** è la stessa lettura di «quanto si è mangiato davvero»
dell'andamento (`tracking.weekly_tracking`): «l'ho seguito» → il piatto in programma
(o i target del pasto, se è un «lo faccio io»); «ho mangiato altro» con la stima →
la stima. Il resto non si sa, e non si manda: un pasto saltato non è un pasto a zero.

**Solo l'amministratore.** healthAI è il suo: i pasti di un ospite finirebbero nei
dati di salute di un altro.

**L'invio non fa mai fallire niente.** Gira dopo, in un thread suo, con timeout di
10 s. Rete giù, timeout, 5xx → si riprova dopo 1, 5, 30 minuti e poi ogni ora, per
24 ore; 401 → il token è sbagliato, si scrive nel log e ci si ferma fino al riavvio
(che è anche quando una variabile d'ambiente cambia); 422 → è un bug del payload, si
scrive il dettaglio e quel payload non si ritenta. Un fallimento definitivo si
sblocca da sé quando il pasto cambia, perché cambia l'impronta.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from .. import config
from ..models import DayPlan, HealthSync, MealSlot, PlannedMeal, Recipe, WeekPlan
from .accounts import admin_user
from .macros import CAMPI_DETTAGLIO, round_detail

logger = logging.getLogger(__name__)

SOURCE = "dietai"
TIMEOUT_S = 10.0
DELETE = "DELETE"
# Dopo il primo fallimento: 1, 5, 30 minuti, poi ogni ora finché non ne sono passate 24.
_ATTESE_MIN = (1, 5, 30)
_ATTESA_POI_MIN = 60
_RESA_DOPO = timedelta(hours=24)


def enabled() -> bool:
    return bool(config.HEALTHAI_URL and config.HEALTHAI_TOKEN)


# ── Cosa si manda ──────────────────────────────────────────────────────────────


def _num(valore, decimali: int = 1) -> float:
    return round(float(valore or 0), decimali)


def meal_payload(day: DayPlan, meal: PlannedMeal, slot: MealSlot, recipe: Recipe | None) -> dict | None:
    """Il body del POST per quel pasto, o None se il pasto non è consumato.

    I valori sono per la porzione mangiata: quella di una persona. Le porzioni di
    `MealSlot.servings` moltiplicano la spesa, non quello che si mette nel piatto.
    """
    if meal.is_followed is True and not meal.is_skipped:
        if recipe is not None:
            valori = {
                "calories": recipe.calories,
                "protein_g": recipe.protein_g,
                "carbs_g": recipe.carbs_g,
                "fat_g": recipe.fat_g,
                **{campo: getattr(recipe, campo) for campo in CAMPI_DETTAGLIO},
            }
            titolo = recipe.title
        elif not slot.auto_generate:
            # «Lo faccio io»: l'utente ha detto di avere il suo pasto con quei macro, e
            # l'andamento lo conta così. Degli altri valori non si sa niente.
            valori = {
                "calories": slot.target_calories,
                "protein_g": slot.target_protein_g,
                "carbs_g": slot.target_carbs_g,
                "fat_g": slot.target_fat_g,
            }
            titolo = None
        else:
            return None
    elif meal.is_followed is False and meal.eaten_nutrition:
        valori = meal.eaten_nutrition
        titolo = meal.deviation_notes
    else:
        return None

    payload = {
        "date": day.date.isoformat(),
        "meal_name": (slot.name or "Pasto")[:60],
        "recipe_title": (titolo or "").strip()[:200] or None,
        "calories": int(round(float(valori.get("calories") or 0))),
        "protein_g": _num(valori.get("protein_g")),
        "carbs_g": _num(valori.get("carbs_g")),
        "fat_g": _num(valori.get("fat_g")),
        "source": SOURCE,
        "external_meal_id": meal.id,
    }
    for campo in CAMPI_DETTAGLIO:
        valore = valori.get(campo)
        # None resta None ("non lo so"), lo zero resta zero ("non ce n'è").
        payload[campo] = round_detail(campo, float(valore)) if valore is not None else None
    return payload


def _hash(payload: dict | None) -> str:
    if payload is None:
        return DELETE
    testo = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


def desired_payloads(db: Session, user_id: int, oggi: date, giorni: int) -> dict[int, dict | None]:
    """Tutti i pasti della finestra, con il payload che healthAI dovrebbe avere.

    None = quel pasto non dev'esserci. La finestra si ferma a oggi: un pasto di domani
    segnato per sbaglio non è stato mangiato, e se lo sarà partirà domani.
    """
    dal = oggi - timedelta(days=giorni)
    rows = (
        db.query(DayPlan, PlannedMeal, MealSlot)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .filter(WeekPlan.user_id == user_id, DayPlan.date >= dal, DayPlan.date <= oggi)
        .all()
    )
    out: dict[int, dict | None] = {}
    for day, meal, slot in rows:
        recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
        out[meal.id] = meal_payload(day, meal, slot, recipe)
    return out


# ── Il trasporto ───────────────────────────────────────────────────────────────


@dataclass
class Esito:
    ok: bool
    status: int | None = None  # None = errore di rete o timeout
    detail: str = ""

    @property
    def riprova(self) -> bool:
        """Rete, timeout, 5xx, 429: passeggeri. Il resto (401, 422...) no."""
        return not self.ok and (self.status is None or self.status >= 500 or self.status == 429)


def http_send(method: str, meal_id: int, payload: dict | None) -> Esito:
    """Una chiamata a healthAI. Non solleva: l'esito dice com'è andata."""
    headers = {"Authorization": f"Bearer {config.HEALTHAI_TOKEN}"}
    if method == "POST":
        url = f"{config.HEALTHAI_URL}/api/nutrition"
    else:
        url = f"{config.HEALTHAI_URL}/api/nutrition/by-external/{SOURCE}/{meal_id}"
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            r = client.request(method, url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        # Solo il tipo d'errore: niente URL né header nel log, il token non esce.
        return Esito(False, None, type(exc).__name__)
    if r.status_code in (200, 201, 204):
        return Esito(True, r.status_code)
    return Esito(False, r.status_code, r.text[:500])


# ── Il giro ────────────────────────────────────────────────────────────────────


@dataclass
class Giro:
    inviati: int = 0
    cancellati: int = 0
    falliti: int = 0
    saltati: int = 0
    fermato: str | None = None
    errori: list[str] = field(default_factory=list)


# Stato del processo, non del database: un 401 non si ritenta finché l'app non si
# riavvia (ed è lì che una variabile d'ambiente corretta arriva), e con healthAI giù
# il giro intero si mette in pausa invece di pagare un timeout per ogni pasto.
_non_autorizzato = False
_pausa_fino: datetime | None = None


def _attesa(tentativi: int) -> timedelta:
    minuti = _ATTESE_MIN[tentativi - 1] if tentativi <= len(_ATTESE_MIN) else _ATTESA_POI_MIN
    return timedelta(minutes=minuti)


def _utc(momento: datetime | None) -> datetime | None:
    if momento is not None and momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)  # SQLite non conserva il fuso
    return momento


def _segna_fallimento(row: HealthSync, target: str, esito: Esito, ora: datetime) -> None:
    if row.failed_hash != target:
        row.failed_hash = target
        row.attempts = 0
        row.first_failed_at = ora
    row.attempts = (row.attempts or 0) + 1
    row.last_error = f"{esito.status or 'rete'}: {esito.detail}"[:500]
    primo = _utc(row.first_failed_at)
    if esito.riprova and (primo is None or ora - primo < _RESA_DOPO):
        row.next_attempt_at = ora + _attesa(row.attempts)
    else:
        row.next_attempt_at = None  # definitivo: si riparte quando il pasto cambia


def _in_attesa(row: HealthSync, target: str, ora: datetime) -> bool:
    if row.failed_hash != target:
        return False
    prossimo = _utc(row.next_attempt_at)
    return prossimo is None or prossimo > ora


def _pulisci(row: HealthSync) -> None:
    row.failed_hash = row.next_attempt_at = row.first_failed_at = row.last_error = None
    row.attempts = 0


def sync(
    db: Session,
    *,
    ora: datetime | None = None,
    oggi: date | None = None,
    giorni: int | None = None,
    send=None,
    force: bool = False,
) -> Giro:
    """Porta healthAI allo stato dei pasti dell'amministratore. Un giro.

    `force` rimanda anche i pasti che healthAI ha già e ignora le attese (è
    l'allineamento iniziale, o il dopo un periodo offline): l'upsert non crea doppioni.
    """
    global _non_autorizzato, _pausa_fino
    giro = Giro()
    if not enabled():
        giro.fermato = "spento"
        return giro
    ora = ora or datetime.now(timezone.utc)
    if _non_autorizzato and not force:
        giro.fermato = "token rifiutato"
        return giro
    if _pausa_fino is not None and ora < _pausa_fino and not force:
        giro.fermato = "healthAI non raggiungibile"
        return giro
    send = send or http_send

    admin = admin_user(db)
    if admin is None:
        giro.fermato = "nessun amministratore"
        return giro
    oggi = oggi or _oggi_italiano(ora)
    desiderati = desired_payloads(db, admin.id, oggi, giorni or config.HEALTHAI_DAYS)
    righe = {r.meal_id: r for r in db.query(HealthSync).filter(HealthSync.user_id == admin.id)}

    da_guardare = set(desiderati) | set(righe)
    for meal_id in sorted(da_guardare):
        row = righe.get(meal_id)
        if meal_id in desiderati:
            payload = desiderati[meal_id]
        elif db.get(PlannedMeal, meal_id) is not None:
            # C'è ancora, ma è uscito dalla finestra: quello che healthAI ha resta lì.
            continue
        else:
            payload = None  # il pasto è stato cancellato: va tolto anche da healthAI
        target = _hash(payload)
        presente = row.sent_hash if row else None

        if payload is None and presente is None:
            if row is not None:
                db.delete(row)  # mai arrivato, niente da togliere
            continue
        if presente == target and not force:
            if row.failed_hash:
                _pulisci(row)  # si è tornati a quello che healthAI ha già
            continue
        if row is not None and not force and _in_attesa(row, target, ora):
            giro.saltati += 1
            continue

        metodo = "DELETE" if payload is None else "POST"
        esito = send(metodo, meal_id, payload)
        if row is None:
            row = HealthSync(meal_id=meal_id, user_id=admin.id, attempts=0)
            db.add(row)
            righe[meal_id] = row

        if esito.ok:
            if payload is None:
                db.delete(row)
                giro.cancellati += 1
                logger.info("healthAI: pasto %s tolto", meal_id)
            else:
                row.sent_hash = target
                row.updated_at = ora
                _pulisci(row)
                giro.inviati += 1
                logger.info("healthAI: pasto %s inviato", meal_id)
            continue

        giro.falliti += 1
        _segna_fallimento(row, target, esito, ora)
        giro.errori.append(f"pasto {meal_id}: {row.last_error}")
        if esito.status in (401, 403):
            _non_autorizzato = True
            giro.fermato = "token rifiutato"
            logger.error(
                "healthAI ha rifiutato il token (%s): controlla HEALTHAI_TOKEN. "
                "Niente più invii fino al riavvio.", esito.status,
            )
            break
        if esito.riprova:
            _pausa_fino = row.next_attempt_at or ora + _attesa(1)
            giro.fermato = "healthAI non raggiungibile"
            logger.warning(
                "healthAI non risponde (%s) sul pasto %s: riprovo dopo le %s UTC",
                esito.status or esito.detail, meal_id, _pausa_fino.strftime("%H:%M"),
            )
            break
        # Nei log solo l'identificativo e la risposta di healthAI, niente del pasto.
        logger.warning(
            "healthAI ha scartato il pasto %s (%s): %s — non lo ritento finché non cambia",
            meal_id, esito.status, esito.detail,
        )
    db.commit()
    if giro.fermato is None:
        _pausa_fino = None
    return giro


def _oggi_italiano(ora: datetime) -> date:
    """La data del pasto è quella di casa: il container gira in UTC."""
    from .push import FUSO

    return ora.astimezone(FUSO).date()


def reset_process_state() -> None:
    """Per i test: dimentica il 401 e la pausa del processo."""
    global _non_autorizzato, _pausa_fino
    _non_autorizzato = False
    _pausa_fino = None


# ── Il thread ──────────────────────────────────────────────────────────────────

_avviato = False


def start_scheduler(session_factory, intervallo: float = 60.0) -> None:
    """Fa girare `sync` ogni minuto, per tutta la vita del processo.

    Non parte se l'integrazione è spenta, né con `DIETAI_SCHEDULER=0` (i test).
    """
    global _avviato
    if _avviato or not enabled() or os.getenv("DIETAI_SCHEDULER", "1") == "0":
        return
    _avviato = True

    def giro():
        while True:
            try:
                db = session_factory()
                try:
                    sync(db)
                finally:
                    db.close()
            except Exception:  # noqa: BLE001 — il giro dopo ci riprova
                logger.warning("Giro di healthAI fallito", exc_info=True)
            time.sleep(intervallo)

    threading.Thread(target=giro, name="healthai", daemon=True).start()
