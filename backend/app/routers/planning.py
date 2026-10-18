"""Piano settimanale: lettura della griglia, generazione e modifica dei singoli pasti."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_user_id
from ..database import get_db
from ..models import DayPlan, MealSlot, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import (
    AssignMealRequest,
    EatenInsteadRequest,
    FollowedRequest,
    GenerateWeekRequest,
    RecurringRequest,
    RegenerateMealRequest,
    SkipDayRequest,
)
from ..services import meals, planner
from ..services.ai_client import get_client
from ..services.ownership import own_meal, own_week
from ..services.planner import (
    current_week_start,
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
)
from ..services.shopping import (
    rebuild_shopping_list,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/planning", tags=["Pianificazione"])


# Il controllo di proprietà sta in `services/ownership.py`: qui solo i nomi di sempre.
_get_week = own_week
_get_meal = own_meal


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
    if not 2000 <= week_start.year <= 2100:
        # Vicino ai bordi del calendario `monday_of` va in OverflowError, cioè in 500.
        raise HTTPException(400, "Data fuori dall'intervallo gestito.")
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
    response: Response,
    week_id: int,
    regenerate_all: bool = False,
    body: GenerateWeekRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera le ricette della settimana. Può richiedere anche un minuto.

    Di default riempie solo le caselle vuote. Con `regenerate_all` rifà tutti i pasti
    generabili: costa una chiamata al modello su tutta la settimana, quindi la UI lo
    fa confermare.

    Nel corpo arriva la selezione della dialog — quali giorni, quali pasti — e senza
    corpo si genera tutta la settimana, che è come funzionava prima. `regenerate_all`
    resta anche come parametro in query perché è così che lo chiamano i test e i
    vecchi indirizzi: basta uno dei due a valere.
    """
    week = _get_week(db, user.id, week_id)
    scelta = body or GenerateWeekRequest()
    result = generate_week(
        db,
        user,
        week,
        only_missing=not (regenerate_all or scelta.regenerate_all),
        days=scelta.days,
        slot_ids=scelta.slot_ids,
        background=planner.GENERATION_IN_BACKGROUND,
    )
    # In background la risposta arriva subito: 202, settimana con `is_generating`
    # acceso, e l'esito lo dirà la settimana stessa al polling.
    if result.get("status") == "started":
        response.status_code = 202
    db.refresh(week)
    payload = serialize_week(db, week)
    payload["generation"] = result
    return payload


@router.get("/weeks/{week_id}/progress")
def generation_progress(
    week_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
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
    meal_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    meal, day, week = _get_meal(db, user_id, meal_id)
    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.post("/meals/{meal_id}/regenerate")
@limiter.limit(AI_LIMIT)
def regenerate(
    request: Request,
    meal_id: int,
    body: RegenerateMealRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera la ricetta di questa casella: a scelta del modello, o su indicazione.

    Il corpo è facoltativo — senza, è la generazione di sempre. Con `user_request`
    dentro ("qualcosa con la zucca", "ho del salmone da finire") il piatto lo decide
    l'utente e l'AI ci pesa sopra i macro del pasto.
    """
    meal, day, week = _get_meal(db, user.id, meal_id)
    richiesta = (body.user_request or "").strip() if body else ""
    regenerate_meal(db, user, meal, user_request=richiesta or None)
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
    meal, day, _week = _get_meal(db, user.id, meal_id)
    return meals.assign(
        db,
        user,
        meal,
        day,
        body.recipe_id,
        body.recipe.model_dump() if body.recipe else None,
    )


@router.delete("/meals/{meal_id}/recipe")
def clear_meal(
    meal_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Svuota la casella; la ricetta resta nel ricettario (`meals.clear`)."""
    meal, day, _week = _get_meal(db, user_id, meal_id)
    return meals.clear(db, user_id, meal, day)


@router.put("/meals/{meal_id}/recurring")
def set_recurring(
    meal_id: int,
    body: RecurringRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Marca il pasto come fisso: non verrà più rigenerato e si ripete ogni settimana."""
    meal, day, _week = _get_meal(db, user_id, meal_id)
    return meals.set_recurring(
        db, user_id, meal, day, body.is_recurring, body.recurring_rule
    )


@router.put("/meals/{meal_id}/eaten")
@limiter.limit(AI_LIMIT)
def set_eaten_instead(
    request: Request,
    meal_id: int,
    body: EatenInsteadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """«Ho mangiato altro: cosa?» — il testo e la stima (`meals.eaten_instead`)."""
    meal, day, _week = _get_meal(db, user.id, meal_id)
    return meals.eaten_instead(
        db, lambda: get_client(db, user, "chat"), meal, day, body.text, body.nothing
    )


@router.put("/meals/{meal_id}/followed")
def set_followed(
    meal_id: int,
    body: FollowedRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Traccia com'è andata (`meals.set_followed`): la dispensa si scala o si rimette."""
    meal, day, week = _get_meal(db, user_id, meal_id)
    return meals.set_followed(
        db, user_id, meal, day, week, body.is_followed, body.deviation_notes
    )


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
