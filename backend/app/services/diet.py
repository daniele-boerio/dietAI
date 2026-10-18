"""La dieta: lettura del PDF, creazione (PDF, a mano, questionario) e correzione dei pasti.

Il router fa solo HTTP — il file caricato, il client del modello, la proprietà — e
qui sta il resto: come si legge un PDF, come si scrivono i pasti di una dieta nuova e
come si corregge quella attiva senza portarsi via il piano.
"""

import base64
import logging
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import DietPlan, MealSlot
from ..schemas import QuestionnaireRequest
from ..utils import frequencies as freq
from ..utils import nutrition
from . import planner, prompts, weight
from .ai_client import AIError
from .pdf import extract_text, looks_scanned
from .planner import get_active_diet, meal_slots_of

logger = logging.getLogger(__name__)


def own_diet(db: Session, user_id: int, diet_id: int) -> DietPlan:
    diet = (
        db.query(DietPlan)
        .filter(DietPlan.id == diet_id, DietPlan.user_id == user_id)
        .first()
    )
    if not diet:
        raise HTTPException(404, "Dieta non trovata")
    return diet


def _deactivate_previous(db: Session, user_id: int) -> list[dict]:
    """Archivia la dieta attiva e restituisce le sue frequenze settimanali.

    Le frequenze passano alla dieta nuova quando quella non ne porta di sue: chi
    ricalcola i macro dal questionario perché è cambiato il peso non ha cambiato idea
    sul pesce due volte a settimana, e perderle a ogni ricalcolo vorrebbe dire
    riscriverle ogni volta.
    """
    attiva = get_active_diet(db, user_id)
    precedenti = freq.clean(attiva.frequencies) if attiva else []
    db.query(DietPlan).filter(
        DietPlan.user_id == user_id, DietPlan.is_active.is_(True)
    ).update({"is_active": False})
    return precedenti


def serialize_diet(db: Session, diet: DietPlan) -> dict:
    slots = meal_slots_of(db, diet.id)
    data = diet.parsed_data if isinstance(diet.parsed_data, dict) else {}
    return {
        "id": diet.id,
        "filename": diet.filename,
        "total_daily_calories": diet.total_daily_calories,
        "notes": diet.notes,
        # Da dove vengono questi numeri: un PDF, il questionario o le dita dell'utente.
        # Serve alla pagina della dieta per riaprire il questionario già compilato —
        # il peso cambia, e ricalcolare deve costare tre secondi, non riscrivere tutto.
        "source": data.get("source") or ("pdf" if diet.filename else "manuale"),
        "profile": data.get("profile"),
        "frequencies": freq.clean(diet.frequencies),
        "created_at": diet.created_at.isoformat() if diet.created_at else None,
        "meals": [
            {
                "id": s.id,
                "name": s.name,
                "order": s.order_index,
                "calories": s.target_calories,
                "protein_g": s.target_protein_g,
                "carbs_g": s.target_carbs_g,
                "fat_g": s.target_fat_g,
                "notes": s.notes,
                "auto_generate": s.auto_generate,
                "servings": s.servings,
                "batch_days": s.batch_days,
            }
            for s in slots
        ],
    }


def _numero(value, massimo: float) -> float:
    """Un numero letto dal modello, nei limiti che l'editor impone a mano.

    Il PDF lo legge il modello: «650 kcal» in stringa era un 500, un valore negativo o
    da 50000 kcal entrava così com'era. Si prende la prima cifra, e si tiene fra 0 e il
    tetto di `MealSlotInput`.
    """
    if isinstance(value, str):
        trovato = re.search(r"\d+(?:[.,]\d+)?", value)
        value = trovato.group(0).replace(",", ".") if trovato else None
    try:
        numero = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return min(max(numero, 0.0), massimo)


def _slot_fields(index: int, meal: dict) -> dict:
    return {
        "name": str(meal.get("name") or f"Pasto {index + 1}").strip()[:100],
        "order_index": index,
        "target_calories": int(round(_numero(meal.get("calories"), 5000))),
        "target_protein_g": _numero(meal.get("protein_g"), 500),
        "target_carbs_g": _numero(meal.get("carbs_g"), 1000),
        "target_fat_g": _numero(meal.get("fat_g"), 500),
        "notes": (str(meal.get("notes"))[:500] if meal.get("notes") else None),
        "auto_generate": bool(meal.get("auto_generate", True)),
        "servings": max(1, int(_numero(meal.get("servings") or 1, 8))),
        "batch_days": max(1, int(_numero(meal.get("batch_days") or 1, 4))),
    }


def _replace_meals(db: Session, diet: DietPlan, meals: list[dict]) -> None:
    """Scrive i pasti di una dieta **appena creata** (PDF, questionario, a mano).

    Una dieta nuova non ha caselle attaccate: quelle delle settimane le riporta sui
    suoi pasti `realign_to_diet`. Per correggere la dieta attiva c'è
    `update_meals_in_place`, perché cancellare i suoi pasti porterebbe via in
    CASCADE tutte le caselle del piano, passate comprese.
    """
    db.query(MealSlot).filter(MealSlot.diet_plan_id == diet.id).delete()
    db.flush()

    for index, meal in enumerate(sorted(meals, key=lambda m: m.get("order", 0))):
        db.add(MealSlot(diet_plan_id=diet.id, **_slot_fields(index, meal)))
    db.flush()


def update_meals_in_place(db: Session, diet: DietPlan, meals: list[dict]) -> None:
    """Corregge i pasti della dieta tenendo le righe che esistono già.

    Prima questa rotta cancellava i `MealSlot` e li ricreava: `PlannedMeal.meal_slot_id`
    è in CASCADE, e ritoccare 20 kcal della merenda svuotava il piano di tutte le
    settimane — ricette, «l'ho seguito», stime, dispensa scalata — e al giro dopo
    healthAI cancellava anche i pasti già mandati. Ora ogni pasto si abbina al suo
    `MealSlot` per id (o, se manca, per nome) e si aggiorna; si cancella solo il pasto
    che l'utente ha tolto, che per definizione non deve più stare in griglia.
    """
    liberi = {s.id: s for s in meal_slots_of(db, diet.id)}

    ordinati = sorted(meals, key=lambda m: m.get("order", 0))
    abbinati: list[MealSlot | None] = [liberi.pop(m.get("id"), None) for m in ordinati]
    for i, meal in enumerate(ordinati):
        if abbinati[i] is not None:
            continue
        chiave = planner._slot_key(meal.get("name"))
        for slot_id, slot in list(liberi.items()):
            if planner._slot_key(slot.name) == chiave:
                abbinati[i] = liberi.pop(slot_id)
                break

    for slot in liberi.values():
        db.delete(slot)
    db.flush()

    # `uq_meal_slot_order` vieta due pasti sulla stessa posizione anche per un attimo:
    # prima si spostano tutti fuori dall'intervallo, poi si scrivono gli indici veri.
    for n, slot in enumerate(s for s in abbinati if s is not None):
        slot.order_index = -1 - n
    db.flush()

    for index, (meal, slot) in enumerate(zip(ordinati, abbinati)):
        campi = _slot_fields(index, meal)
        if slot is None:
            db.add(MealSlot(diet_plan_id=diet.id, **campi))
        else:
            for chiave, valore in campi.items():
                setattr(slot, chiave, valore)
    db.flush()


def correct_meals(db: Session, diet: DietPlan, meals: list[dict]) -> None:
    """Corregge a mano i pasti della dieta (l'AI sbaglia, i PDF sono brutti)."""
    update_meals_in_place(db, diet, meals)
    diet.total_daily_calories = sum(m["calories"] for m in meals)


def set_frequencies(diet: DietPlan, frequencies: list[dict]) -> None:
    sconosciuti = [f["food"] for f in frequencies if f["food"] not in freq.FOODS]
    if sconosciuti:
        raise HTTPException(400, f"Gruppo di alimenti non valido: {', '.join(sconosciuti)}")
    diet.frequencies = freq.clean(frequencies)


# ── Dal PDF ────────────────────────────────────────────────────────────────────


def read_pdf(client, content: bytes) -> dict:
    """Fa leggere il PDF al modello: il testo se c'è, le pagine se è una scansione.

    Prima si prova a estrarre il testo (services/pdf.py): quasi tutte le diete sono
    PDF generati da un gestionale, l'estrazione è gratis e funziona con qualunque
    modello. Solo se il PDF è una scansione serve un modello che veda la pagina.
    """
    text = extract_text(content)

    if looks_scanned(text):
        if not client.supports_native_pdf:
            raise HTTPException(
                400,
                "Questo PDF sembra una scansione o una foto: non contiene testo da "
                "leggere, e il modello configurato non può guardarne le pagine. "
                "Inserisci i pasti a mano dalla schermata della dieta — sono pochi "
                "campi e li correggi una volta sola.",
            )
        logger.info("PDF senza testo: passo al modello il documento originale")
        return client.parse_pdf(
            prompts.DIET_PARSE_SYSTEM,
            base64.standard_b64encode(content).decode(),
            prompts.DIET_PARSE_PROMPT,
        )
    logger.info("PDF con testo: %s caratteri estratti", len(text))
    return client.generate_json(
        prompts.DIET_PARSE_SYSTEM,
        prompts.render(prompts.DIET_PARSE_TEXT_PROMPT, text=text[:120_000]),
        max_tokens=8000,
    )


def create_from_pdf(db: Session, user_id: int, filename: str | None, data) -> DietPlan:
    """La dieta nuova da quello che il modello ha letto nel PDF."""
    if not isinstance(data, dict) or not isinstance(data.get("meals"), list) or not data["meals"]:
        raise AIError("Nel PDF non ho trovato pasti riconoscibili. Inseriscili a mano.")

    meals = [m for m in data["meals"] if isinstance(m, dict)][:20]
    if not meals:
        raise AIError("Nel PDF non ho trovato pasti riconoscibili. Inseriscili a mano.")
    # Il totale è la somma dei pasti, non il numero che il modello ha letto a parte:
    # i due potevano non tornare, e il contesto diceva 1800 kcal su pasti da 2100.
    daily = sum(int(round(_numero(m.get("calories"), 5000))) for m in meals)

    # Una sola dieta attiva: la precedente resta in archivio, disattivata.
    precedenti = _deactivate_previous(db, user_id)

    diet = DietPlan(
        user_id=user_id,
        filename=filename,
        parsed_data=data,
        total_daily_calories=daily,
        notes=(data.get("notes") or None),
        # Le frequenze lette dal PDF; se il PDF non ne parla, quelle che c'erano.
        frequencies=freq.clean(data.get("frequencies")) or precedenti,
        is_active=True,
    )
    db.add(diet)
    db.flush()
    _replace_meals(db, diet, meals)
    logger.info("Dieta caricata per utente %s: %s pasti, %s kcal", user_id, len(meals), daily)
    return diet


# ── A mano ─────────────────────────────────────────────────────────────────────


def create_manual(db: Session, user_id: int, meals: list[dict]) -> DietPlan:
    """La dieta scritta a mano, senza PDF (o quando il parsing non ha funzionato)."""
    precedenti = _deactivate_previous(db, user_id)

    diet = DietPlan(
        user_id=user_id,
        filename=None,
        parsed_data={"meals": meals, "source": "manuale"},
        total_daily_calories=sum(m["calories"] for m in meals),
        frequencies=precedenti,
        is_active=True,
    )
    db.add(diet)
    db.flush()
    _replace_meals(db, diet, meals)
    return diet


# ── Dal questionario ───────────────────────────────────────────────────────────


def compute(body: QuestionnaireRequest) -> dict:
    """Il calcolo, con gli errori di elenco tradotti in 400 leggibili."""
    try:
        return nutrition.compute_plan(
            sex=body.sex,
            age=body.age,
            height_cm=body.height_cm,
            weight_kg=body.weight_kg,
            activity=body.activity,
            goal=body.goal,
            meals_count=body.meals_count,
            meals=body.meals,
            targets=body.targets.model_dump() if body.targets else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def create_from_questionnaire(db: Session, user_id: int, body: QuestionnaireRequest) -> DietPlan:
    """Calcola la dieta dai dati della persona, quando non c'è un nutrizionista.

    Il risultato è una dieta come le altre — stessi `MealSlot`, stessi target, stessa
    modificabilità: da qui in poi l'app non sa e non deve sapere da dove vengono i
    numeri. Le risposte restano dentro `parsed_data`, così il questionario si riapre
    già compilato quando il peso cambia (e resta scritto, nella dieta archiviata, con
    che dati era stato fatto quel calcolo).
    """
    computed = compute(body)

    precedenti = _deactivate_previous(db, user_id)

    # I pasti effettivi finiscono nel profilo anche quando la richiesta diceva solo
    # quanti erano: riaprendo il questionario le caselle sono già quelle di prima.
    profile = {**body.model_dump(), "meals": [m["key"] for m in computed["meals"]]}
    forzati = computed["daily_calories"] != computed["proposed"]["daily_calories"]

    diet = DietPlan(
        user_id=user_id,
        filename=None,
        parsed_data={
            "source": "questionario",
            "profile": profile,
            "computed": {
                key: computed[key]
                for key in ("bmr", "tdee", "daily_calories", "protein_g", "carbs_g", "fat_g")
            },
            "meals": computed["meals"],
        },
        total_daily_calories=computed["daily_calories"],
        frequencies=precedenti,
        notes=(
            f"Calcolata dal questionario: metabolismo basale {computed['bmr']} kcal, "
            f"fabbisogno {computed['tdee']} kcal, obiettivo «{body.goal}»."
            + (
                f" Totali corretti a mano: la formula diceva "
                f"{computed['proposed']['daily_calories']} kcal."
                if forzati
                else ""
            )
        ),
        is_active=True,
    )
    db.add(diet)
    db.flush()
    _replace_meals(db, diet, computed["meals"])
    # Il peso scritto nel questionario è anche una pesata: è il punto da cui lo
    # storico parte, e il riferimento contro cui si misura quando ricalcolare.
    weight.upsert(db, user_id, planner.today(), body.weight_kg)

    logger.info(
        "Dieta da questionario per utente %s: %s kcal su %s pasti",
        user_id,
        computed["daily_calories"],
        len(computed["meals"]),
    )
    return diet
