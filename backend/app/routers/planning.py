"""Piano settimanale: lettura della griglia, generazione e modifica dei singoli pasti."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_user_id
from ..database import get_db
from ..models import DayPlan, MealSlot, PlannedMeal, Recipe, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import AssignMealRequest, FollowedRequest, RecurringRequest, SkipDayRequest
from ..services.planner import (
    current_week_start,
    ensure_not_skipped,
    generate_week,
    generation_error,
    get_or_create_week,
    is_generating,
    monday_of,
    next_week_start,
    refresh_week_statuses,
    regenerate_meal,
    serialize_meal,
    serialize_week,
    skip_day,
    skip_meal,
    unskip_meal,
)
from ..services.recipes import create_recipe
from ..services.shopping import (
    consume_from_pantry,
    rebuild_shopping_list,
    restore_to_pantry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planning", tags=["Pianificazione"])


def _get_week(db: Session, user_id: int, week_id: int) -> WeekPlan:
    week = (
        db.query(WeekPlan)
        .filter(WeekPlan.id == week_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not week:
        raise HTTPException(404, "Settimana non trovata")
    return week


def _get_meal(db: Session, user_id: int, meal_id: int) -> tuple[PlannedMeal, DayPlan, WeekPlan]:
    """Recupera il pasto verificando che la catena pasto → giorno → settimana sia dell'utente.

    Il filtro su user_id sta qui e non nel chiamante apposta: dimenticarlo in uno
    solo degli endpoint significherebbe far modificare i piani altrui.
    """
    row = (
        db.query(PlannedMeal, DayPlan, WeekPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(PlannedMeal.id == meal_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Pasto non trovato")
    return row


# ── Settimane ──────────────────────────────────────────────────────────────────


@router.get("/weeks/current")
def get_current_week(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    refresh_week_statuses(db, user_id)
    week = get_or_create_week(db, user_id, current_week_start())
    return serialize_week(db, week)


@router.get("/weeks/next")
def get_next_week(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    refresh_week_statuses(db, user_id)
    week = get_or_create_week(db, user_id, next_week_start())
    return serialize_week(db, week)


@router.get("/weeks/by-date/{week_start}")
def get_week_by_date(
    week_start: date,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Una settimana qualunque, indietro o avanti quanto si vuole.

    La data viene riportata al suo lunedì, così un indirizzo con un giorno qualsiasi
    apre comunque la settimana giusta.

    Avanti vale la regola di sempre — la settimana esiste appena la si apre — e
    quanto spingersi lo decide l'utente, come per la spesa: chi apre la settimana fra
    un mese la sta pianificando. Il passato invece non si inventa: se in quella
    settimana non c'era nessun piano si risponde con una settimana vuota (`id` a
    None) e non la si crea adesso, o sfogliare all'indietro riempirebbe l'archivio di
    settimane mai vissute, coi pasti fissi ricopiati in giorni già passati.
    """
    refresh_week_statuses(db, user_id)
    monday = monday_of(week_start)

    if monday < current_week_start():
        week = (
            db.query(WeekPlan)
            .filter(WeekPlan.user_id == user_id, WeekPlan.week_start_date == monday)
            .first()
        )
        if not week:
            # Stessa forma di una settimana vera: la pagina cambia solo il contenuto,
            # non il modo di leggerlo.
            return {
                "id": None,
                "week_start_date": monday.isoformat(),
                "status": "empty",
                "is_current": False,
                "is_past": True,
                "is_generating": False,
                "generation_error": None,
                "meals_total": 0,
                "meals_filled": 0,
                "meals_self_managed": 0,
                "days_skipped": 0,
                "days": [],
            }
        return serialize_week(db, week)

    return serialize_week(db, get_or_create_week(db, user_id, monday))


@router.post("/weeks/{week_id}/generate")
@limiter.limit(AI_LIMIT)
def generate(
    request: Request,
    week_id: int,
    regenerate_all: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera le ricette della settimana. Può richiedere anche un minuto.

    Di default riempie solo le caselle vuote. Con `regenerate_all=true` rifà tutti i
    pasti generabili: costa una chiamata al modello su tutta la settimana, quindi la
    UI lo fa confermare.
    """
    week = _get_week(db, user.id, week_id)
    result = generate_week(db, user, week, only_missing=not regenerate_all)
    payload = serialize_week(db, week)
    payload["generation"] = result
    return payload


@router.get("/weeks/{week_id}/progress")
def generation_progress(
    week_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Cosa sta scrivendo il modello in questo momento.

    Chiamata a raffica mentre la generazione è in corso, quindi non ricostruisce
    niente: legge la riga della settimana e la restituisce. A generazione finita
    risponde con `is_generating` falso e il diario vuoto, che è il segnale per la
    pagina di smettere di chiedere — e, se è finita male, col motivo: la risposta
    della POST che l'avrebbe detto è quasi sempre già stata tagliata da un proxy.
    """
    week = _get_week(db, user_id, week_id)
    running = is_generating(week)
    started = week.generation_started_at
    return {
        "is_generating": running,
        "started_at": started.isoformat() if running and started else None,
        **(week.generation_progress or {} if running else {}),
        "error": generation_error(week),
    }


# ── Pasti ──────────────────────────────────────────────────────────────────────


@router.get("/meals/{meal_id}")
def get_meal(
    meal_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    meal, day, week = _get_meal(db, user_id, meal_id)
    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.post("/meals/{meal_id}/regenerate")
@limiter.limit(AI_LIMIT)
def regenerate(
    request: Request,
    meal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meal, day, week = _get_meal(db, user.id, meal_id)
    regenerate_meal(db, user, meal)
    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.put("/meals/{meal_id}/assign")
def assign_meal(
    meal_id: int,
    body: AssignMealRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assegna al pasto una ricetta del ricettario o una scritta al momento."""
    meal, day, week = _get_meal(db, user.id, meal_id)
    ensure_not_skipped(day, meal)

    if body.recipe_id:
        recipe = (
            db.query(Recipe)
            .filter(Recipe.id == body.recipe_id, Recipe.user_id == user.id)
            .first()
        )
        if not recipe:
            raise HTTPException(404, "Ricetta non trovata")
        meal.recipe_id = recipe.id
        meal.source = "from_favorites" if recipe.is_favorite else "user_custom"
    elif body.recipe:
        recipe = create_recipe(db, user.id, body.recipe.model_dump(), is_custom=True)
        meal.recipe_id = recipe.id
        meal.source = "user_custom"
    else:
        raise HTTPException(400, "Serve recipe_id oppure una ricetta completa.")

    meal.is_followed = None
    # Il piatto è un altro: quello che era stato scalato dalla dispensa resta scalato
    # (mangiato è mangiato), ma non ha più senso rimetterlo se domani si corregge.
    meal.pantry_used = None
    db.commit()

    rebuild_shopping_list(db, user.id)
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.delete("/meals/{meal_id}/recipe")
def clear_meal(
    meal_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Svuota la casella (la ricetta resta nel ricettario)."""
    meal, day, week = _get_meal(db, user_id, meal_id)

    meal.recipe_id = None
    meal.source = "ai_generated"
    meal.is_recurring = False
    meal.recurring_rule = None
    meal.is_followed = None
    meal.pantry_used = None
    db.commit()

    rebuild_shopping_list(db, user_id)
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.put("/meals/{meal_id}/recurring")
def set_recurring(
    meal_id: int,
    body: RecurringRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Marca il pasto come fisso: non verrà più rigenerato e si ripete ogni settimana."""
    meal, day, week = _get_meal(db, user_id, meal_id)

    if body.is_recurring and not meal.recipe_id:
        raise HTTPException(400, "Assegna prima una ricetta a questo pasto.")

    rule = body.recurring_rule or {"type": "weekly", "day": day.day_of_week}
    if rule.get("type") not in ("daily", "weekly"):
        raise HTTPException(400, "Regola di ricorrenza non valida")
    if rule["type"] == "weekly":
        rule = {"type": "weekly", "day": int(rule.get("day", day.day_of_week))}

    meal.is_recurring = body.is_recurring
    meal.recurring_rule = rule if body.is_recurring else None
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.put("/meals/{meal_id}/followed")
def set_followed(
    meal_id: int,
    body: FollowedRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Traccia com'è andata — e con "ho mangiato altro" rimanda il piatto più avanti.

    Funziona anche a piano bloccato, anzi soprattutto: a spesa fatta gli ingredienti
    sono in frigo, quindi un piatto non cucinato non è perso, si accoda alla prima
    casella libera di quel pasto. Dire invece "l'ho seguito" annulla il rinvio e la
    ricetta torna al suo posto.

    "L'ho seguito" è anche il momento in cui gli ingredienti finiscono davvero: la
    dispensa si scala qui, una volta sola per pasto (`pantry_used` è la memoria di
    cosa è stato tolto), e si rimette identica se il pasto viene corretto.
    """
    meal, day, week = _get_meal(db, user_id, meal_id)
    meal.is_followed = body.is_followed
    meal.deviation_notes = body.deviation_notes

    pantry_used: list[dict] = []
    pantry_skipped: list[dict] = []
    if body.is_followed:
        unskip_meal(db, meal)
        moved = {"moved_to": None}
        if meal.pantry_used is None:
            pantry_used, pantry_skipped = consume_from_pantry(db, user_id, meal.recipe_id)
            # Niente scalato, niente da ricordare: `pantry_used` risponde a "cosa ho
            # tolto", ed è anche la guardia contro il doppio scalo. Segnarci una lista
            # vuota vorrebbe dire "già fatto" per sempre, e un pasto segnato prima
            # della spesa non si scalerebbe più nemmeno a dispensa piena.
            meal.pantry_used = pantry_used or None
    else:
        moved = skip_meal(db, user_id, meal, day, week)
        restore_to_pantry(db, user_id, meal.pantry_used)
        meal.pantry_used = None
    db.commit()

    rebuild_shopping_list(db, user_id)
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    data = serialize_meal(db, day, meal, slot, full=True)
    data["moved_to"] = moved["moved_to"]
    # Quello che è appena uscito dalla dispensa: la pagina lo dice, altrimenti la
    # scorta cala di nascosto e nessuno si fida più del numero. E quello che non è
    # uscito, col motivo: una dispensa che resta ferma senza spiegazioni sembra un
    # pulsante che non funziona.
    data["pantry_used"] = pantry_used
    data["pantry_skipped"] = pantry_skipped
    return data


@router.put("/days/{day_id}/skip")
def set_day_skipped(
    day_id: int,
    body: SkipDayRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Salta l'intera giornata: weekend fuori, pranzo dai suoceri.

    Tutte le ricette del giorno si accodano ai giorni successivi, una per pasto. Vale
    solo da oggi in avanti: i giorni passati senza spesa li salta già il piano da sé.
    """
    row = (
        db.query(DayPlan, WeekPlan)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(DayPlan.id == day_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Giorno non trovato")
    day, week = row

    skip_day(db, user_id, day, week, body.is_skipped)
    db.commit()

    rebuild_shopping_list(db, user_id)
    db.commit()
    return serialize_week(db, week)
