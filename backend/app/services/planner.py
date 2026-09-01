"""Pianificazione settimanale: struttura delle settimane e generazione AI.

Il modello mentale: una settimana esiste sempre (lunedì → domenica) e contiene già
una casella per ogni incrocio giorno × pasto della dieta, anche vuota. Generare
significa riempire le caselle libere; rigenerare significa svuotarne una e
richiederla di nuovo. Le caselle "fissate" (pasti ricorrenti e ricette scelte a mano
dall'utente) l'AI non le tocca mai.
"""

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from ..models import (
    BaseIngredient,
    DayPlan,
    DietPlan,
    ExcludedIngredient,
    Ingredient,
    MealSlot,
    PantryItem,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    User,
    UserPreferences,
    WeekPlan,
)
from ..utils.seasonality import current_month, current_month_name, in_season
from ..utils.units import format_quantity
from . import prompts
from .ai_client import AIError, get_client
from .recipes import create_recipe, recipe_for_prompt, serialize_recipe

logger = logging.getLogger(__name__)

DAY_NAMES = [
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
]


# ── Settimane ──────────────────────────────────────────────────────────────────


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def today() -> date:
    """Il punto unico da cui l'app legge la data di oggi.

    Esiste perché parecchie regole dipendono da che giorno è — la lista della spesa
    guarda da oggi in avanti, un pasto saltato si accoda a un giorno futuro — e i test
    devono poterlo spostare, altrimenti la stessa suite darebbe risultati diversi il
    lunedì e il venerdì.
    """
    return date.today()


def current_week_start() -> date:
    return monday_of(today())


def next_week_start() -> date:
    return current_week_start() + timedelta(days=7)


def get_active_diet(db: Session, user_id: int) -> DietPlan | None:
    return (
        db.query(DietPlan)
        .filter(DietPlan.user_id == user_id, DietPlan.is_active.is_(True))
        .order_by(DietPlan.created_at.desc())
        .first()
    )


def require_active_diet(db: Session, user_id: int) -> DietPlan:
    diet = get_active_diet(db, user_id)
    if not diet:
        raise HTTPException(
            400, "Nessuna dieta attiva: carica il PDF del nutrizionista per iniziare."
        )
    return diet


def meal_slots_of(db: Session, diet_plan_id: int) -> list[MealSlot]:
    return (
        db.query(MealSlot)
        .filter(MealSlot.diet_plan_id == diet_plan_id)
        .order_by(MealSlot.order_index)
        .all()
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def refresh_week_statuses(db: Session, user_id: int) -> None:
    """Rimette a posto lo stato delle settimane: passate in archivio, questa attiva.

    Viene chiamato all'inizio di ogni lettura del piano, così lo stato è sempre
    coerente senza bisogno di uno scheduler. Archiviata non vuol dire intoccabile: una
    settimana passata si può ancora aprire e correggere, serve solo a distinguerla da
    quella in corso.
    """
    this_monday = current_week_start()
    changed = False

    for week in db.query(WeekPlan).filter(WeekPlan.user_id == user_id).all():
        if week.week_start_date < this_monday:
            target = "archived"
        elif week.week_start_date == this_monday:
            target = "active"
        else:
            continue
        if week.status != target:
            week.status = target
            changed = True

    if changed:
        db.commit()


def _slot_key(name: str | None) -> str:
    """Il nome di un pasto ridotto a chiave: due diete diverse scrivono «Pranzo» uguale."""
    return " ".join((name or "").split()).casefold()


def _casella_vissuta(meal: PlannedMeal) -> bool:
    """C'è qualcosa dentro questa casella, o è solo il buco che nasce con la settimana?"""
    return bool(
        meal.recipe_id
        or meal.is_followed is not None
        or meal.is_skipped
        or meal.is_recurring
        or meal.deviation_notes
    )


def realign_to_diet(db: Session, days: list[DayPlan], slots: list[MealSlot]) -> None:
    """Riporta le caselle già in griglia sui pasti della dieta **attiva**.

    Cambiare dieta — ricalcolare i macro dal questionario, caricare un altro PDF —
    non modifica i `MealSlot` esistenti: ne crea di nuovi, e i vecchi restano attaccati
    alla dieta archiviata. Le caselle della settimana però puntano ancora a quelli, e
    `ensure_week_structure` qui sotto aggiunge per ogni giorno una casella vuota per
    ogni pasto nuovo: senza questo passaggio la griglia finisce con due colazioni, due
    pranzi e due cene — quelle di prima, piene, e quelle della dieta nuova, vuote.

    Il pasto si sposta sul suo omonimo della dieta attiva invece di essere buttato via:
    la ricetta che c'è dentro è costata una chiamata al modello, e quello che l'utente
    ha già segnato («l'ho seguito», la dispensa scalata) è storia sua. Cambiano solo i
    target, che sono quelli della dieta nuova. Sparisce soltanto ciò che nella dieta
    nuova non ha più un posto dove stare: un pasto che non si fa più non può restare in
    griglia, o continuerebbe a pesare su spesa, totali del giorno e aderenza.
    """
    if not days:
        return

    slot_ids = {s.id for s in slots}
    meals = (
        db.query(PlannedMeal)
        .filter(PlannedMeal.day_plan_id.in_([d.id for d in days]))
        .all()
    )
    orfane = [m for m in meals if m.meal_slot_id not in slot_ids]
    if not orfane:
        return

    # Il primo pasto vince, se la dieta ha due pasti con lo stesso nome: sono due
    # caselle diverse, ma una delle due deve pur essere quella dove atterrare.
    per_nome: dict[str, MealSlot] = {}
    for slot in slots:
        per_nome.setdefault(_slot_key(slot.name), slot)

    nomi_vecchi = {
        s.id: _slot_key(s.name)
        for s in db.query(MealSlot)
        .filter(MealSlot.id.in_({m.meal_slot_id for m in orfane}))
        .all()
    }
    occupanti = {
        (m.day_plan_id, m.meal_slot_id): m for m in meals if m.meal_slot_id in slot_ids
    }

    da_rimuovere: list[PlannedMeal] = []
    da_spostare: list[tuple[PlannedMeal, int]] = []
    spostate: set[int] = set()

    for orfana in orfane:
        destinazione = per_nome.get(nomi_vecchi.get(orfana.meal_slot_id, ""))
        if destinazione is None:
            da_rimuovere.append(orfana)
            continue

        occupante = occupanti.get((orfana.day_plan_id, destinazione.id))
        if occupante is not None:
            # La casella nuova esiste già: sopravvive quella che ha qualcosa da dire —
            # e chi ci è appena atterrato non lo si sfratta, o si finirebbe per
            # cancellare una riga che nello stesso giro è già stata spostata.
            if (
                occupante.id in spostate
                or _casella_vissuta(occupante)
                or not _casella_vissuta(orfana)
            ):
                da_rimuovere.append(orfana)
                continue
            da_rimuovere.append(occupante)

        da_spostare.append((orfana, destinazione.id))
        spostate.add(orfana.id)
        occupanti[(orfana.day_plan_id, destinazione.id)] = orfana

    # Prima si cancella e si scarica, poi si sposta: `uq_planned_meal` vieta due caselle
    # sullo stesso (giorno, pasto), e la UPDATE arriverebbe prima della DELETE.
    for meal in da_rimuovere:
        db.delete(meal)
    db.flush()

    for meal, slot_id in da_spostare:
        meal.meal_slot_id = slot_id
    db.flush()

    logger.info(
        "Settimana riallineata alla dieta attiva: %s caselle spostate, %s rimosse",
        len(da_spostare),
        len(da_rimuovere),
    )


def ensure_week_structure(db: Session, week: WeekPlan, slots: list[MealSlot]) -> None:
    """Crea i giorni e le caselle mancanti.

    Serve anche dopo una modifica della dieta (pasti aggiunti o rinominati): le
    settimane già create devono adeguarsi senza essere buttate via. Se la dieta è stata
    proprio sostituita, prima si riportano le caselle esistenti sui pasti di quella
    attiva (`realign_to_diet`), altrimenti alle vecchie si sommerebbero le nuove.
    """
    days = {
        d.day_of_week: d
        for d in db.query(DayPlan).filter(DayPlan.week_plan_id == week.id)
    }

    for offset in range(7):
        if offset not in days:
            day = DayPlan(
                week_plan_id=week.id,
                date=week.week_start_date + timedelta(days=offset),
                day_of_week=offset,
            )
            db.add(day)
            db.flush()
            days[offset] = day

    realign_to_diet(db, list(days.values()), slots)

    slot_ids = {s.id for s in slots}
    for day in days.values():
        existing = {
            m.meal_slot_id
            for m in db.query(PlannedMeal).filter(PlannedMeal.day_plan_id == day.id)
        }
        for slot_id in slot_ids - existing:
            db.add(
                PlannedMeal(
                    day_plan_id=day.id, meal_slot_id=slot_id, source="ai_generated"
                )
            )
    db.flush()


def get_or_create_week(db: Session, user_id: int, week_start: date) -> WeekPlan:
    diet = require_active_diet(db, user_id)
    slots = meal_slots_of(db, diet.id)
    if not slots:
        raise HTTPException(400, "La dieta attiva non ha pasti configurati.")

    week = (
        db.query(WeekPlan)
        .filter(WeekPlan.user_id == user_id, WeekPlan.week_start_date == week_start)
        .first()
    )
    created = week is None
    if created:
        week = WeekPlan(
            user_id=user_id,
            week_start_date=week_start,
            status="active" if week_start == current_week_start() else "draft",
        )
        db.add(week)
        db.flush()

    ensure_week_structure(db, week, slots)
    if created:
        apply_recurring_meals(db, user_id, week)
    db.commit()
    return week


# Oltre questo tempo una generazione si considera morta (processo riavviato, container
# ricreato): senza, una settimana resterebbe "in generazione" per sempre.
GENERATION_TIMEOUT = timedelta(minutes=15)


def is_generating(week: WeekPlan) -> bool:
    started = _as_utc(week.generation_started_at)
    if started is None:
        return False
    return datetime.now(timezone.utc) - started < GENERATION_TIMEOUT


class GenerationProgress:
    """Il diario di bordo della generazione: cosa sta uscendo dal modello, adesso.

    Una generazione dura minuti e finora la pagina non poteva dire altro che "sto
    lavorando": nessun modo di distinguere un modello che sta ragionando da uno
    piantato, o di capire a che ricetta è arrivato. Ora i pezzi che passano già in
    streaming vengono raccolti qui e messi dove la pagina può leggerli.

    Passa dal database, come `generation_started_at` e per lo stesso motivo: chi
    guarda non è per forza chi ha premuto il pulsante, e la pagina si può ricaricare.
    Se ne tiene solo la coda — a nessuno serve rileggere trentamila caratteri, e la
    riga deve restare piccola perché la si riscrive ogni paio di secondi.

    Le scritture vanno su una sessione a parte, aperta e chiusa a ogni giro: quella
    della richiesta ha in mano la settimana a metà, e non può essere committata solo
    per far vedere due righe di testo. Se il diario non si scrive non succede niente
    di grave, quindi ogni errore qui viene ingoiato: sarebbe assurdo perdere una
    generazione pagata per un log.
    """

    REASONING_TAIL = 4000
    CONTENT_TAIL = 2000
    FLUSH_EVERY = 2.0  # secondi

    def __init__(self, week_id: int, expected_recipes: int = 0, session_factory=None):
        self.week_id = week_id
        self.expected_recipes = expected_recipes
        self._session_factory = session_factory
        self._reasoning: list[str] = []
        self._content: list[str] = []
        self._last_flush = 0.0

    def __call__(self, kind: str, delta: str) -> None:
        (self._reasoning if kind == "reasoning" else self._content).append(delta)

        now = time.monotonic()
        if now - self._last_flush < self.FLUSH_EVERY:
            return
        self.flush()

    def snapshot(self) -> dict:
        reasoning = "".join(self._reasoning)
        content = "".join(self._content)
        return {
            "reasoning": reasoning[-self.REASONING_TAIL :],
            "content": content[-self.CONTENT_TAIL :],
            "reasoning_chars": len(reasoning),
            "content_chars": len(content),
            # Ogni ricetta comincia con la sua chiave "title": contarle è il modo più
            # economico di dire a che punto siamo senza parsare un JSON a metà.
            "recipes_written": content.count('"title"'),
            "expected_recipes": self.expected_recipes,
        }

    def flush(self) -> None:
        self._last_flush = time.monotonic()
        if not self._session_factory:
            return

        session = self._session_factory()
        try:
            session.query(WeekPlan).filter(WeekPlan.id == self.week_id).update(
                {WeekPlan.generation_progress: self.snapshot()},
                synchronize_session=False,
            )
            session.commit()
        except Exception:
            logger.debug("Diario della generazione non scritto", exc_info=True)
            session.rollback()
        finally:
            session.close()


def clear_generation_progress(db: Session, week: WeekPlan) -> None:
    """Cancella il diario nel database, non solo nell'oggetto in memoria.

    Il diario lo scrive un'altra sessione, quindi questa non sa che il valore sia mai
    cambiato: assegnare `None` all'attributo non produrrebbe nessuna UPDATE e la
    fotografia dell'ultima generazione resterebbe appesa alla settimana per sempre.
    """
    week.generation_progress = None
    db.query(WeekPlan).filter(WeekPlan.id == week.id).update(
        {WeekPlan.generation_progress: None}, synchronize_session=False
    )


def generation_error(week: WeekPlan) -> str | None:
    """Perché l'ultima generazione non è arrivata in fondo, se è andata male.

    Sta nella stessa colonna del diario, che a generazione ferma è libera: sono due
    facce della stessa domanda ("cosa sta succedendo / cos'è successo") e tenerle
    separate avrebbe voluto dire una colonna in più per un dato che vive quanto l'altro.
    """
    if is_generating(week):
        return None
    return (week.generation_progress or {}).get("error")


def record_generation_failure(db: Session, week: WeekPlan, reason: str) -> None:
    """Scrive sulla settimana perché la generazione è fallita, e sblocca la settimana.

    Serve perché la risposta HTTP quasi mai arriva a destinazione: una generazione dura
    minuti e la richiesta muore molto prima, tagliata dal proxy che sta davanti (nginx
    a 300s, Cloudflare a 100s). Il messaggio d'errore finiva così in una risposta che
    nessuno leggeva, e da fuori restava solo una settimana vuota senza spiegazioni —
    mentre il frontend, che segue il polling e non la risposta, annunciava pure
    "Settimana pronta ✓". Il motivo resta scritto qui finché non si riprova.

    Il rollback prima di scrivere è deliberato: una generazione interrotta a metà non
    si salva (le ricette già create senza il resto del piano sarebbero peggio di
    niente), l'errore sì.
    """
    db.rollback()
    payload = {"error": reason, "failed_at": datetime.now(timezone.utc).isoformat()}
    week.generation_started_at = None
    week.generation_progress = payload
    # Come sopra: il diario lo scrive un'altra sessione, quindi la UPDATE va esplicita.
    db.query(WeekPlan).filter(WeekPlan.id == week.id).update(
        {WeekPlan.generation_started_at: None, WeekPlan.generation_progress: payload},
        synchronize_session=False,
    )
    db.commit()


def _failure_reason(exc: BaseException) -> str:
    """Il messaggio da mostrare all'utente per un'eccezione della generazione.

    Gli `AIError` sono già scritti per essere letti da lui (dicono anche cosa fare);
    per tutto il resto si tiene il tipo, che a quel punto è l'informazione utile.
    """
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return f"{type(exc).__name__}: {exc}".strip()


def ensure_not_generating(week: WeekPlan) -> None:
    """Una generazione alla volta per settimana.

    Non è pignoleria: ogni chiamata si paga, e senza questo controllo bastava
    ricaricare la pagina e ripremere il pulsante per farne partire una seconda.
    """
    if is_generating(week):
        raise HTTPException(
            409,
            "C'è già una generazione in corso per questa settimana: aspetta che finisca.",
        )


def ensure_not_skipped(day: DayPlan, meal: PlannedMeal | None = None) -> None:
    if meal is not None and meal.is_skipped:
        raise HTTPException(
            409,
            "Questo pasto è saltato: la sua ricetta si è accodata più avanti. "
            "Segnalo come seguito per riportarlo qui.",
        )
    if day.is_skipped:
        raise HTTPException(
            409,
            "Questa giornata è saltata: le sue ricette si sono accodate più avanti. "
            "Rimettila in programma per tornare a modificarla.",
        )


# ── Pasti fissi ────────────────────────────────────────────────────────────────


def _is_fixed(meal: PlannedMeal, slot: MealSlot) -> bool:
    """Un pasto fissato non viene toccato né dalla generazione né dagli spostamenti.

    Tre modi per esserlo: è ricorrente, l'utente gli ha assegnato una ricetta a mano,
    oppure il pasto è marcato nella dieta come "lo gestisco io" (`auto_generate` a
    False) — la colazione di sempre, che non ha senso far reinventare ogni settimana.
    """
    return meal.is_recurring or meal.source == "user_custom" or not slot.auto_generate


# ── Pasti ricorrenti ───────────────────────────────────────────────────────────


def apply_recurring_meals(db: Session, user_id: int, week: WeekPlan) -> int:
    """Pre-assegna alla settimana i pasti marcati come ricorrenti nella precedente.

    La ricetta è la stessa riga, non una copia: la colazione di sempre è **un** piatto,
    e farne una copia a settimana (per giorno, con la regola "daily") era il modo più
    veloce di riempire il ricettario di doppioni. La garanzia che c'era prima non si
    perde: modificare la colazione di questa settimana non riscrive quella archiviata,
    perché chi modifica da dentro un pasto passa da `fork_recipe_for_meal`, che la
    copia stacca lì — quando serve davvero.
    """
    previous = (
        db.query(WeekPlan)
        .filter(
            WeekPlan.user_id == user_id, WeekPlan.week_start_date < week.week_start_date
        )
        .order_by(WeekPlan.week_start_date.desc())
        .first()
    )
    if not previous:
        return 0

    recurring = (
        db.query(PlannedMeal, DayPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(
            DayPlan.week_plan_id == previous.id,
            PlannedMeal.is_recurring.is_(True),
            PlannedMeal.recipe_id.isnot(None),
        )
        .all()
    )
    if not recurring:
        return 0

    days = {
        d.day_of_week: d
        for d in db.query(DayPlan).filter(DayPlan.week_plan_id == week.id)
    }
    applied = 0

    for meal, source_day in recurring:
        rule = meal.recurring_rule or {"type": "weekly", "day": source_day.day_of_week}
        if rule.get("type") == "daily":
            targets = list(days.values())
        else:
            day = days.get(rule.get("day", source_day.day_of_week))
            targets = [day] if day else []

        recipe = db.get(Recipe, meal.recipe_id)
        if not recipe:
            continue

        for target_day in targets:
            target = (
                db.query(PlannedMeal)
                .filter(
                    PlannedMeal.day_plan_id == target_day.id,
                    PlannedMeal.meal_slot_id == meal.meal_slot_id,
                )
                .first()
            )
            if not target or target.recipe_id:
                continue
            target.recipe_id = recipe.id
            target.source = meal.source
            target.is_recurring = True
            target.recurring_rule = rule
            applied += 1

    db.flush()
    return applied


def clear_meal_cell(db: Session, meal: PlannedMeal) -> None:
    """Riporta la casella a com'era prima che ci finisse dentro qualcosa.

    Non è `_empty_meal`, che serve a un'altra cosa — lì la ricetta se n'è andata da
    un'altra parte, qui non c'è più — e infatti spegne anche il pasto fisso: una
    casella vuota che si ripete ogni settimana non vuol dire niente. La ricetta resta
    nel ricettario: quello che si svuota è il posto, non il piatto.

    Se il pasto è rimandato (is_skipped), svuota anche la casella dove era stata
    accodata la ricetta, altrimenti rimane orfana.
    """
    # Se il pasto è rimandato, svuota anche la casella dove era stata accodata la ricetta
    if meal.is_skipped and meal.skipped_to_meal_id:
        accodata = db.get(PlannedMeal, meal.skipped_to_meal_id)
        if accodata is not None and accodata.recipe_id and not accodata.is_skipped:
            _empty_meal(db, accodata)

    meal.recipe_id = None
    meal.source = "ai_generated"
    meal.is_recurring = False
    meal.recurring_rule = None
    meal.is_followed = None
    meal.is_skipped = False
    meal.deviation_notes = None
    meal.pantry_used = None
    meal.skipped_to_meal_id = None
    forget_queued_meal(db, meal)


def stop_recurring_forward(
    db: Session, user_id: int, meal: PlannedMeal, day: DayPlan
) -> int:
    """Togliendo il «fisso», leva quel piatto anche dalle caselle che l'hanno ricevuto.

    Un pasto fisso si ricopia da sé sulle settimane che si aprono — e una settimana si
    apre anche solo sfogliandola — quindi quando si toglie la spunta quelle copie sono
    già scritte in giro: spegnere l'interruttore e trovare la luce accesa lo stesso è
    il motivo per cui la spunta sembrava non funzionare. Si tolgono le caselle che
    hanno **quella** ricetta su **quel** pasto e il segno di fisso addosso: una
    colazione uguale scelta a mano un altro giorno non è una copia, e resta dov'è.

    Due limiti, per non cancellare fatti invece di previsioni. Solo **dopo** questa
    casella e mai prima di oggi: quello che è già stato è storia, anche se lo si
    scopre sfogliando all'indietro. E mai una casella dove l'utente ha già segnato
    com'è andata — seguita o rimandata: lì la ricetta non è un programma, è il
    racconto di una giornata.

    Le altre — quelle che restano, perché vengono prima o perché sono già state
    vissute — perdono comunque il **segno** di fisso, che è la parte che si propaga:
    `apply_recurring_meals` legge la settimana precedente, quindi con la regola
    "daily" bastava una casella accesa il lunedì per far ricomparire tutto la
    settimana dopo, e togliere la spunta dal mercoledì sarebbe sembrato non aver
    fatto niente. La ricetta lì non si tocca: è già in programma, ed è un piatto che
    l'utente ha davanti.
    """
    if not meal.recipe_id:
        return 0

    caselle = (
        db.query(PlannedMeal, DayPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date >= today(),
            PlannedMeal.id != meal.id,
            PlannedMeal.meal_slot_id == meal.meal_slot_id,
            PlannedMeal.recipe_id == meal.recipe_id,
            PlannedMeal.is_recurring.is_(True),
        )
        .all()
    )

    tolte = 0
    for casella, giorno in caselle:
        vissuta = casella.is_followed is not None or casella.is_skipped
        if giorno.date <= day.date or vissuta:
            casella.is_recurring = False
            casella.recurring_rule = None
            continue
        clear_meal_cell(db, casella)
        tolte += 1

    db.flush()
    return tolte


# ── Pasti saltati ──────────────────────────────────────────────────────────────


def forget_queued_meal(db: Session, meal: PlannedMeal) -> None:
    """Questa casella non è più «il piatto che avevo rimandato».

    Da chiamare quando ci si mette dentro qualcos'altro di proposito — rigenerata,
    riassegnata, svuotata: da lì in poi annullare il salto non deve più portarsela via,
    perché quello che c'è ora l'ha scelto l'utente.
    """
    db.query(PlannedMeal).filter(PlannedMeal.skipped_to_meal_id == meal.id).update(
        {"skipped_to_meal_id": None}
    )


def _empty_meal(db: Session, meal: PlannedMeal) -> None:
    """Svuota una casella: la ricetta se n'è andata da un'altra parte."""
    meal.recipe_id = None
    meal.source = "ai_generated"
    meal.is_followed = None
    meal.deviation_notes = None
    meal.skipped_to_meal_id = None
    forget_queued_meal(db, meal)


def _overflow_week(db: Session, user_id: int, week: WeekPlan) -> WeekPlan | None:
    """La settimana dopo, dove finisce quello che in questa non entra più."""
    if not get_active_diet(db, user_id):
        return None
    return get_or_create_week(db, user_id, week.week_start_date + timedelta(days=7))


def _free_cells(
    db: Session, user_id: int, week: WeekPlan, slot_id: int
) -> list[PlannedMeal]:
    """Le caselle libere di quello slot da oggi in avanti, in ordine di giorno.

    Prima quelle rimaste vuote in questa settimana, poi quelle della prossima: è la
    coda su cui si accoda un piatto saltato.
    """
    now = today()
    out = []
    for source in (week, _overflow_week(db, user_id, week)):
        if source is None:
            continue
        for day, meal, slot in week_meals(db, source):
            if slot.id != slot_id or _is_fixed(meal, slot):
                continue
            if day.is_skipped or meal.is_skipped or meal.recipe_id:
                continue
            if source is week and day.date < now:
                continue  # un giorno già passato non è un posto dove rimandare niente
            out.append(meal)
    return out


def skip_meal(
    db: Session, user_id: int, meal: PlannedMeal, day: DayPlan, week: WeekPlan
) -> dict:
    """ "Ho mangiato altro": il piatto non è stato cucinato, la ricetta va in fondo.

    Non fa slittare niente: gli altri giorni restano dove sono e la ricetta saltata si
    accoda sulla prima casella libera di quel pasto — più avanti in settimana se ce
    n'è una, altrimenti nella settimana prossima. È la lettura giusta a spesa fatta:
    gli ingredienti sono in frigo, quel piatto lo cucini un altro giorno.

    La casella saltata tiene la sua `recipe_id` come memoria di cosa c'era in
    programma, ma smette di contare ovunque: spesa, totali, tracking, generazione.
    """
    if meal.is_skipped:
        return {"moved_to": None}

    slot = db.get(MealSlot, meal.meal_slot_id)
    meal.is_skipped = True

    # Un pasto fisso o gestito dall'utente non si sposta: è ancorato a quel giorno
    # per scelta di chi l'ha messo lì, e la settimana prossima si ricopia da solo.
    if _is_fixed(meal, slot) or not meal.recipe_id:
        db.flush()
        return {"moved_to": None}

    free = _free_cells(db, user_id, week, slot.id)
    if not free:
        db.flush()
        return {"moved_to": None}

    target = free[0]
    target.recipe_id = meal.recipe_id
    target.source = meal.source
    target.is_followed = None
    target.deviation_notes = None
    # Dove è finito il piatto, scritto invece che indovinato: annullare il salto deve
    # svuotare **questa** casella, non un'altra che per caso ha lo stesso piatto — e da
    # quando lo stesso piatto in due giorni è una riga di ricetta sola, "stessa ricetta"
    # non è più un indirizzo.
    meal.skipped_to_meal_id = target.id
    db.flush()

    target_day = db.get(DayPlan, target.day_plan_id)
    return {
        "moved_to": {
            "meal_id": target.id,
            "date": target_day.date.isoformat(),
            "day_name": DAY_NAMES[target_day.day_of_week],
            "next_week": target_day.week_plan_id != week.id,
        }
    }


def unskip_meal(db: Session, meal: PlannedMeal) -> None:
    """Annulla il salto: la ricetta torna qui e la casella dove si era accodata si svuota.

    Quale casella lo dice `skipped_to_meal_id`, scritto da `skip_meal`. Prima lo si
    cercava per somiglianza — stesso pasto, stessa `recipe_id` — e finché ogni casella
    aveva la sua riga di ricetta era un indirizzo univoco; ora che lo stesso piatto in
    due giorni è **una** riga, quella ricerca svuoterebbe la prima colazione uguale che
    incontra.
    """
    if not meal.is_skipped:
        return

    meal.is_skipped = False
    accodata = (
        db.get(PlannedMeal, meal.skipped_to_meal_id)
        if meal.skipped_to_meal_id
        else None
    )
    meal.skipped_to_meal_id = None

    # Basta che là ci sia ancora qualcosa: il puntatore è l'indirizzo, e vale finché
    # nessuno ci ha messo dentro altro di proposito — chi rigenera, riassegna o svuota
    # quella casella lo cancella (`forget_queued_meal`). Non si confrontano le ricette,
    # perché nel frattempo il piatto rimandato può essere stato modificato in chat, e
    # quella modifica gliene ha staccata una copia sua.
    if accodata is not None and accodata.recipe_id and not accodata.is_skipped:
        _empty_meal(db, accodata)

    db.flush()


def skip_day(
    db: Session, user_id: int, day: DayPlan, week: WeekPlan, skipped: bool
) -> None:
    """Salta (o rimette) l'intera giornata: vale per tutti i suoi pasti insieme.

    Serve per il weekend fuori, e vale da oggi in avanti: una giornata già passata la
    si racconta pasto per pasto ("l'ho seguito" / "ho mangiato altro"), che è la
    stessa cosa ma detta bene.
    """
    if day.date < today():
        raise HTTPException(409, "Un giorno già passato non si salta a mano.")

    day.is_skipped = skipped
    meals = db.query(PlannedMeal).filter(PlannedMeal.day_plan_id == day.id).all()
    for meal in meals:
        if skipped:
            skip_meal(db, user_id, meal, day, week)
        else:
            unskip_meal(db, meal)
    db.flush()


# ── Contesto per i prompt ──────────────────────────────────────────────────────


def _excluded_names(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(ExcludedIngredient, Ingredient)
        .outerjoin(Ingredient, Ingredient.id == ExcludedIngredient.ingredient_id)
        .filter(ExcludedIngredient.user_id == user_id)
        .all()
    )
    return [
        ing.name if ing else (exc.custom_name or "")
        for exc, ing in rows
        if ing or exc.custom_name
    ]


def _base_names(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(Ingredient.name)
        .join(BaseIngredient, BaseIngredient.ingredient_id == Ingredient.id)
        .filter(BaseIngredient.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]


def _pantry_descriptions(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(PantryItem, Ingredient)
        .join(Ingredient, Ingredient.id == PantryItem.ingredient_id)
        .filter(PantryItem.user_id == user_id)
        .all()
    )
    out = []
    for item, ing in rows:
        if item.quantity_available:
            out.append(
                f"{ing.name} ({format_quantity(item.quantity_available, item.unit or 'unità')})"
            )
        else:
            out.append(ing.name)
    return out


def _rated_titles(db: Session, user_id: int, high: bool) -> list[str]:
    query = db.query(Recipe.title).filter(Recipe.user_id == user_id)
    query = (
        query.filter(Recipe.rating >= 4) if high else query.filter(Recipe.rating <= 2)
    )
    return [r[0] for r in query.order_by(Recipe.id.desc()).limit(15).all()]


def _fmt_list(values: list[str], empty: str = "nessuno") -> str:
    values = [v for v in values if v]
    return ", ".join(sorted(set(values))) if values else empty


def build_context(db: Session, user_id: int) -> str:
    """Il blocco di contesto comune a tutti i prompt di generazione."""
    diet = require_active_diet(db, user_id)
    slots = meal_slots_of(db, diet.id)
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()

    meals_config = "\n".join(
        f"  · {s.name}: {s.target_calories} kcal — proteine {s.target_protein_g:g}g, "
        f"carboidrati {s.target_carbs_g:g}g, grassi {s.target_fat_g:g}g"
        + (f" — note: {s.notes}" if s.notes else "")
        # Elencato lo stesso, perché conta nel bilancio della giornata, ma va detto
        # che non si tocca: senza, il modello prova a proporcelo comunque.
        + ("" if s.auto_generate else " — NON generare: se lo prepara l'utente")
        for s in slots
    )

    prefer_seasonal = prefs.prefer_seasonal if prefs else True
    prefer_italian = prefs.prefer_italian if prefs else True

    if prefer_seasonal:
        seasonal = ", ".join(in_season(current_month())[:25])
        seasonality = (
            f"privilegia gli ingredienti di stagione. Siamo a {current_month_name()}: "
            f"di stagione ci sono {seasonal}."
        )
    else:
        seasonality = "nessun vincolo di stagionalità."

    return prompts.render(
        prompts.CONTEXT_TEMPLATE,
        daily_calories=diet.total_daily_calories,
        meals_config=meals_config,
        excluded=_fmt_list(_excluded_names(db, user_id)),
        # Testo libero dell'utente: passa così com'è, senza interpretarlo. Regole
        # come "carne al massimo due volte a settimana" funzionano proprio perché il
        # piano si genera tutto in una volta e il modello vede l'intera settimana.
        extra_rules=((prefs.notes or "").strip() if prefs else "") or "nessuna",
        base=_fmt_list(_base_names(db, user_id)),
        pantry=_fmt_list(_pantry_descriptions(db, user_id), "vuota"),
        cuisine=(
            "italiana o mediterranea, piatti che si cucinano davvero in casa"
            if prefer_italian
            else "nessuna preferenza particolare"
        ),
        seasonality=seasonality,
        max_prep=(
            f"{prefs.max_prep_time_min} minuti"
            if prefs and prefs.max_prep_time_min
            else "nessun limite"
        ),
        budget=(prefs.budget_level if prefs and prefs.budget_level else "medio"),
        liked=_fmt_list(_rated_titles(db, user_id, True), "nessuna ancora"),
        disliked=_fmt_list(_rated_titles(db, user_id, False), "nessuna ancora"),
    )


# ── Lettura della settimana ────────────────────────────────────────────────────


def week_meals(
    db: Session, week: WeekPlan
) -> list[tuple[DayPlan, PlannedMeal, MealSlot]]:
    return (
        db.query(DayPlan, PlannedMeal, MealSlot)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .filter(DayPlan.week_plan_id == week.id)
        .order_by(DayPlan.day_of_week, MealSlot.order_index)
        .all()
    )


def serialize_meal(
    db: Session, day: DayPlan, meal: PlannedMeal, slot: MealSlot, *, full: bool = False
) -> dict:
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    data = {
        "id": meal.id,
        "day_of_week": day.day_of_week,
        "day_name": DAY_NAMES[day.day_of_week],
        "date": day.date.isoformat(),
        # Il giorno è passato senza spesa: la casella è in sola lettura come quando
        # il piano è bloccato, ma per un motivo diverso.
        "day_is_skipped": day.is_skipped,
        "slot_id": slot.id,
        "slot_name": slot.name,
        "slot_order": slot.order_index,
        "target": {
            "calories": slot.target_calories,
            "protein_g": slot.target_protein_g,
            "carbs_g": slot.target_carbs_g,
            "fat_g": slot.target_fat_g,
            "notes": slot.notes,
        },
        # "lo gestisco io": niente da generare, ma i macro contano nella giornata
        "self_managed": not slot.auto_generate,
        "source": meal.source,
        # "Ho mangiato altro": la ricetta qui sotto è quella che era in programma, ma
        # non è stata cucinata — si è accodata più avanti e qui non conta più.
        "is_skipped": meal.is_skipped,
        "is_recurring": meal.is_recurring,
        "recurring_rule": meal.recurring_rule,
        "is_followed": meal.is_followed,
        "deviation_notes": meal.deviation_notes,
        "recipe": serialize_recipe(db, recipe, full=full),
    }

    # Un pasto mostrato da solo (la pagina di dettaglio) ha bisogno di sapere in che
    # stato è la sua settimana: senza, non può nemmeno dire se è modificabile. Sta
    # qui e non nel router perché la pagina si ridisegna con la risposta del pulsante
    # appena premuto, non solo con la lettura iniziale: quando `week` c'era solo nella
    # GET, il primo clic su "L'ho seguito" restituiva un pasto senza settimana e la
    # schermata si spegneva con un TypeError.
    if full:
        week = db.get(WeekPlan, day.week_plan_id)
        data["week"] = {
            "id": week.id,
            "week_start_date": week.week_start_date.isoformat(),
            "status": week.status,
            "is_current": week.week_start_date == current_week_start(),
            # Solo per dire dove ci si trova: una settimana passata si modifica come
            # tutte le altre, semplicemente non è quella in corso.
            "is_past": week.week_start_date < current_week_start(),
        }
    return data


def serialize_week(db: Session, week: WeekPlan) -> dict:
    rows = week_meals(db, week)
    days: dict[int, dict] = {}

    for day, meal, slot in rows:
        entry = days.setdefault(
            day.day_of_week,
            {
                "id": day.id,
                "date": day.date.isoformat(),
                "day_of_week": day.day_of_week,
                "day_name": DAY_NAMES[day.day_of_week],
                # Giorno passato senza spesa: le ricette sono slittate via, la
                # griglia lo mostra spento e la lista della spesa lo ignora.
                "is_skipped": day.is_skipped,
                "meals": [],
            },
        )
        entry["meals"].append(serialize_meal(db, day, meal, slot))

    for entry in days.values():
        # I pasti gestiti dall'utente non hanno una ricetta, ma lui li mangia centrando
        # i target: contarli col loro target è l'unico modo perché il totale del giorno
        # rappresenti quello che si mangia davvero e non solo quello che ha scritto l'AI.
        def _macros(meal: dict) -> dict:
            # Un pasto saltato conserva la ricetta per memoria, ma non è stato
            # mangiato: contarlo gonfierebbe la giornata di un piatto mai cucinato.
            if meal["is_skipped"]:
                return {}
            if meal["recipe"]:
                return meal["recipe"]
            return meal["target"] if meal["self_managed"] else {}

        contributi = [_macros(m) for m in entry["meals"]]
        entry["totals"] = {
            "calories": sum(c.get("calories", 0) for c in contributi),
            "protein_g": round(sum(c.get("protein_g", 0) for c in contributi), 1),
            "carbs_g": round(sum(c.get("carbs_g", 0) for c in contributi), 1),
            "fat_g": round(sum(c.get("fat_g", 0) for c in contributi), 1),
            # Anche il target scende: un pasto saltato non è un buco da colmare, è un
            # pasto che quel giorno non era in programma mangiare.
            "target_calories": sum(
                m["target"]["calories"] for m in entry["meals"] if not m["is_skipped"]
            ),
        }

    # "Da riempire" conta solo le caselle che l'AI deve generare: includere quelle
    # gestite dall'utente farebbe sembrare il piano perennemente incompleto. Stesso
    # motivo per i giorni saltati: sono passati, non c'è più niente da riempirci.
    da_vivere = [(d, m, s) for d, m, s in rows if not d.is_skipped and not m.is_skipped]
    generabili = [(d, m, s) for d, m, s in da_vivere if s.auto_generate]
    total_slots = len(generabili)
    filled = sum(1 for _, meal, _ in generabili if meal.recipe_id)
    self_managed = len(da_vivere) - total_slots

    return {
        "id": week.id,
        "week_start_date": week.week_start_date.isoformat(),
        "status": week.status,
        "is_current": week.week_start_date == current_week_start(),
        # Serve solo a dire dove ci si trova sfogliando: passata, corrente o futura si
        # modificano tutte allo stesso modo.
        "is_past": week.week_start_date < current_week_start(),
        # La UI ci si aggancia per rimettere il loader quando si torna sulla pagina
        # a generazione avviata.
        "is_generating": is_generating(week),
        # E qui trova com'è finita, se è finita male: la risposta alla POST che
        # l'avrebbe detto è quasi sempre già stata buttata via da un proxy.
        "generation_error": generation_error(week),
        "meals_total": total_slots,
        "meals_filled": filled,
        "meals_self_managed": self_managed,
        "days_skipped": sum(1 for d in days.values() if d["is_skipped"]),
        "days": [days[k] for k in sorted(days)],
    }


# ── Generazione ────────────────────────────────────────────────────────────────


def _slot_line(slot: MealSlot) -> str:
    line = (
        f"{slot.name} — {slot.target_calories} kcal, P {slot.target_protein_g:g}g, "
        f"C {slot.target_carbs_g:g}g, G {slot.target_fat_g:g}g"
    )
    return line + (f" (note: {slot.notes})" if slot.notes else "")


def generate_week(
    db: Session,
    user: User,
    week: WeekPlan,
    *,
    only_missing: bool = True,
    days: list[int] | None = None,
    slot_ids: list[int] | None = None,
) -> dict:
    """Genera in un'unica chiamata le ricette della settimana.

    Una chiamata sola, non una per pasto: è l'unico modo perché l'AI possa
    distribuire gli avanzi (mezza zucchina lunedì, l'altra metà giovedì) e non
    ripetere gli stessi ingredienti in giorni consecutivi. Vale anche generando
    mezza settimana: quello che resta fuori dalla selezione ma una ricetta ce l'ha
    finisce comunque nel prompt come `PASTI GIÀ ASSEGNATI`.

    `only_missing` è il default perché ogni chiamata si paga: riempire i buchi è
    l'operazione di tutti i giorni, rifare da capo una settimana già piena è una
    scelta esplicita che la UI fa confermare.

    `days` (day_of_week) e `slot_ids` sono la selezione della dialog: `None` vuol dire
    tutto, che è come ha sempre funzionato il pulsante. Restringere non è un vezzo —
    chi la colazione se la prepara da sé non deve pagarne sette — e non cambia niente
    del resto: si genera sempre in una chiamata sola, solo su meno caselle.
    """
    ensure_not_generating(week)
    rows = week_meals(db, week)
    if not rows:
        raise HTTPException(400, "La settimana non ha pasti da generare.")

    # I giorni saltati sono passati e i pasti saltati sono già stati risolti altrove:
    # generarci una ricetta vorrebbe dire pagare una chiamata per un piatto che nessuno
    # cucinerà. Vale anche per "Rigenera tutto", che altrimenti li ripescherebbe.
    rows = [(d, m, s) for d, m, s in rows if not d.is_skipped and not m.is_skipped]
    generabili = [(d, m, s) for d, m, s in rows if not _is_fixed(m, s)]

    # La selezione fatta nella dialog. Sono filtri e non validazioni: un giorno o un
    # pasto che non esistono semplicemente non selezionano niente, e la lista vuota —
    # che è una scelta esplicita, non un campo dimenticato — cade nel messaggio qui
    # sotto invece di rifare tutta la settimana.
    scelti = generabili
    if days is not None:
        giorni = set(days)
        scelti = [t for t in scelti if t[0].day_of_week in giorni]
    if slot_ids is not None:
        pasti = set(slot_ids)
        scelti = [t for t in scelti if t[2].id in pasti]

    to_fill = [t for t in scelti if t[1].recipe_id is None] if only_missing else scelti

    if not to_fill:
        if days is not None or slot_ids is not None:
            raise HTTPException(
                400,
                "Nei giorni e nei pasti che hai scelto non c'è niente da generare: "
                "allarga la selezione, oppure spunta «rifai anche i pasti già pronti».",
            )
        if generabili:
            raise HTTPException(
                400,
                'Non ci sono pasti da riempire: usa "Rigenera tutto" per rifare la settimana.',
            )
        raise HTTPException(
            400,
            "Non c'è niente da generare: tutti i pasti sono fissi o gestiti da te.",
        )

    # Tutto ciò che conserva la sua ricetta va passato al modello come contesto: sono
    # i piatti da non ripetere e gli ingredienti già in casa da riutilizzare.
    da_rifare = {m.id for _, m, _ in to_fill}
    fixed = [(d, m, s) for d, m, s in rows if m.recipe_id and m.id not in da_rifare]

    by_day: dict[int, list[str]] = {}
    for day, _meal, slot in to_fill:
        by_day.setdefault(day.day_of_week, []).append(_slot_line(slot))
    slots_to_fill = "\n".join(
        f"{DAY_NAMES[dow]} (day_of_week {dow}):\n"
        + "\n".join(f"  · {line}" for line in lines)
        for dow, lines in sorted(by_day.items())
    )

    if fixed:
        already = "\n".join(
            f"  · {DAY_NAMES[d.day_of_week]} / {s.name}: "
            f"{db.get(Recipe, m.recipe_id).title}"
            for d, m, s in fixed
        )
    else:
        already = "  (nessuno)"

    prompt = prompts.render(
        prompts.WEEK_PLAN_PROMPT,
        context=build_context(db, user.id),
        slots_to_fill=slots_to_fill,
        already_assigned=already,
    )

    client = get_client(db, user, "planning")

    # Da qui in avanti la settimana risulta "in generazione". Il commit chiude anche
    # la transazione aperta dalle letture qui sopra: senza, Postgres si terrebbe una
    # connessione "idle in transaction" per tutta la durata della chiamata.
    week.generation_started_at = datetime.now(timezone.utc)
    clear_generation_progress(db, week)
    db.commit()

    progress = GenerationProgress(
        week.id,
        expected_recipes=len(to_fill),
        # Stesso database, connessione diversa: così il diario si committa da solo
        # senza portarsi dietro la settimana a metà che ha in mano questa sessione.
        session_factory=sessionmaker(bind=db.get_bind()),
    )
    progress.flush()  # una prima riga subito: la pagina ha già qualcosa da mostrare

    # Budget: ~2.000 token a ricetta più il margine per il ragionamento. Sopra la
    # soglia il client passa automaticamente in streaming.
    max_tokens = min(64000, 2000 * len(to_fill) + 6000)
    try:
        data = client.generate_json(
            prompts.WEEK_PLAN_SYSTEM,
            prompt,
            max_tokens=max_tokens,
            thinking=True,
            on_progress=progress,
        )
        # Anche l'applicazione della risposta sta dentro il try: una risposta parsabile
        # ma di forma sbagliata sollevava fuori di qui, e lasciava la settimana
        # bloccata su "sto generando" fino allo scadere del quarto d'ora.
        return _apply_generated_week(db, user, week, data, to_fill)
    except Exception as exc:
        # Il log è l'unico posto dove questo messaggio arriva per davvero: la risposta
        # HTTP viene scritta su una connessione che il proxy ha chiuso da minuti, e
        # senza questa riga una generazione fallita non lasciava alcuna traccia.
        logger.exception("Generazione fallita per la settimana %s", week.id)
        # Sblocca la settimana — altrimenti resta ferma fino al timeout — e ricorda
        # perché, per chi la sta guardando dal polling.
        record_generation_failure(db, week, _failure_reason(exc))
        raise


def _apply_generated_week(
    db: Session,
    user: User,
    week: WeekPlan,
    data: dict | list,
    to_fill: list[tuple[DayPlan, PlannedMeal, MealSlot]],
) -> dict:
    """Scrive nel piano le ricette uscite dal modello."""
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        raise AIError("Claude ha restituito un piano in un formato inatteso.")

    # Indice delle caselle da riempire: (giorno, nome pasto normalizzato) → riga DB.
    index = {(d.day_of_week, s.name.strip().lower()): (d, m, s) for d, m, s in to_fill}
    filled = 0

    for day_data in data["days"]:
        try:
            dow = int(day_data.get("day_of_week"))
        except (TypeError, ValueError):
            continue
        for meal_data in day_data.get("meals") or []:
            slot_name = (meal_data.get("slot_name") or "").strip().lower()
            target = index.pop((dow, slot_name), None)
            if not target:
                # L'AI ha inventato un pasto che non esiste (o l'ha già riempito):
                # ignorarlo è meglio che sovrascrivere qualcosa a caso.
                logger.info(
                    "Pasto ignorato dalla risposta AI: giorno %s, slot %r",
                    dow,
                    slot_name,
                )
                continue
            recipe_data = meal_data.get("recipe") or {}
            if not recipe_data.get("title"):
                continue
            _day, meal, _slot = target
            recipe = create_recipe(
                db, user.id, recipe_data, generation_prompt="week_plan"
            )
            meal.recipe_id = recipe.id
            meal.source = "ai_generated"
            meal.is_followed = None
            filled += 1

    week.generation_started_at = None
    clear_generation_progress(db, week)

    if filled == 0:
        # Niente commit: a rimettere in ordine la settimana — sbloccarla e segnare
        # perché — ci pensa chi cattura, che è anche l'unico a saperlo dire all'utente.
        raise AIError(
            "Il modello non ha prodotto nessuna ricetta utilizzabile. Riprova."
        )

    if week.status == "draft" and week.week_start_date == current_week_start():
        week.status = "active"

    db.commit()

    # La lista della spesa segue sempre il piano: le ricette appena generate chiedono
    # ingredienti che in dispensa non ci sono, e devono comparire subito in lista —
    # anche se la settimana generata è la prossima, perché la spesa è una sola.
    from .shopping import rebuild_shopping_list

    rebuild_shopping_list(db, user.id)
    db.commit()

    return {
        "filled": filled,
        "missing": len(index),
        "notes": data.get("ingredient_reuse_notes"),
    }


def _partial_ingredients(
    db: Session, week: WeekPlan, exclude_meal_id: int
) -> list[str]:
    """Ingredienti già previsti in settimana: la nuova ricetta dovrebbe riusarli."""
    rows = (
        db.query(Ingredient.name)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .join(PlannedMeal, PlannedMeal.recipe_id == RecipeIngredient.recipe_id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(DayPlan.week_plan_id == week.id, PlannedMeal.id != exclude_meal_id)
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def regenerate_meal(
    db: Session, user: User, meal: PlannedMeal, *, user_request: str | None = None
) -> Recipe:
    """Genera (o rigenera) la ricetta di un singolo pasto.

    Due modi, stesso pulsante. Senza `user_request` sceglie il modello, col vincolo di
    proporre qualcosa di diverso dal piatto di prima e dagli altri della settimana.
    Con `user_request` — un'idea, degli ingredienti da usare, un piatto preciso — decide
    l'utente e all'AI resta il mestiere: pesare gli ingredienti perché i macro del pasto
    tornino, completare quello che manca e scrivere il procedimento. È il caso che la
    chat non copriva: lì si parte da una ricetta e la si modifica, qui la casella può
    essere ancora vuota.

    La vecchia ricetta non viene cancellata: resta nel ricettario (magari era
    votata) e semplicemente non è più assegnata a questo pasto.
    """
    day = db.get(DayPlan, meal.day_plan_id)
    week = db.get(WeekPlan, day.week_plan_id)
    ensure_not_skipped(day, meal)

    slot = db.get(MealSlot, meal.meal_slot_id)
    previous = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None

    week_titles = [
        r.title
        for r in db.query(Recipe)
        .join(PlannedMeal, PlannedMeal.recipe_id == Recipe.id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(DayPlan.week_plan_id == week.id, PlannedMeal.id != meal.id)
        .all()
    ]

    prompt = prompts.render(
        prompts.SINGLE_MEAL_PROMPT,
        context=build_context(db, user.id),
        slot_name=slot.name,
        day_name=DAY_NAMES[day.day_of_week],
        target_calories=slot.target_calories,
        target_protein=f"{slot.target_protein_g:g}",
        target_carbs=f"{slot.target_carbs_g:g}",
        target_fat=f"{slot.target_fat_g:g}",
        slot_notes=slot.notes or "nessuna",
        previous_recipe=previous.title if previous else "nessuna",
        week_recipes=_fmt_list(week_titles, "nessuna"),
        partial_ingredients=_fmt_list(
            _partial_ingredients(db, week, meal.id), "nessuno"
        ),
        user_request=(
            "\nRICHIESTA DELL'UTENTE (ha la precedenza sulle regole di varietà qui "
            f"sopra): {user_request}\n"
            "Costruisci il piatto attorno a questa richiesta: scegli e pesa gli "
            "ingredienti perché i macro target tornino, e scrivi il procedimento."
            if user_request
            else ""
        ),
    )

    client = get_client(db, user, "planning")
    db.commit()  # come sopra: niente transazione aperta durante la chiamata al modello
    data = client.generate_json(
        prompts.SINGLE_MEAL_SYSTEM, prompt, max_tokens=8000, thinking=False
    )
    if not isinstance(data, dict) or not data.get("title"):
        raise AIError("Claude non ha restituito una ricetta valida.")

    recipe = create_recipe(
        db, user.id, data, generation_prompt=json.dumps({"slot": slot.name})
    )

    # Se il pasto era stato tracciato come seguito, reimmetti gli ingredienti nella dispensa
    if meal.is_followed is True and meal.pantry_used:
        from .shopping import restore_to_pantry

        restore_to_pantry(db, user.id, meal.pantry_used)

    meal.recipe_id = recipe.id
    meal.source = "ai_generated"
    meal.is_followed = None
    meal.pantry_used = None  # Reset since we're getting a new recipe
    # Qui dentro c'è un piatto nuovo, scelto adesso: se questa casella era la coda di un
    # pasto rimandato, non lo è più.
    forget_queued_meal(db, meal)
    db.commit()

    from .shopping import rebuild_shopping_list

    rebuild_shopping_list(db, user.id)
    db.commit()
    return recipe


def meal_context_for_chat(db: Session, meal: PlannedMeal) -> dict:
    """Dati del pasto usati per costruire il system prompt della chat."""
    day = db.get(DayPlan, meal.day_plan_id)
    week = db.get(WeekPlan, day.week_plan_id)
    slot = db.get(MealSlot, meal.meal_slot_id)
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    return {
        "day": day,
        "week": week,
        "slot": slot,
        "recipe": recipe,
        "recipe_json": (
            json.dumps(recipe_for_prompt(db, recipe), ensure_ascii=False, indent=2)
            if recipe
            else "nessuna ricetta ancora assegnata a questo pasto"
        ),
    }
