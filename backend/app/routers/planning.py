"""Piano settimanale: lettura della griglia, generazione e modifica dei singoli pasti."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_user_id
from ..database import get_db
from ..models import DayPlan, MealSlot, PlannedMeal, Recipe, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import AssignMealRequest, FollowedRequest, RecurringRequest
from ..services.planner import (
    LOCK_DAYS,
    current_week_start,
    ensure_unlocked,
    generate_week,
    get_or_create_week,
    next_week_start,
    refresh_week_statuses,
    regenerate_meal,
    serialize_meal,
    serialize_week,
)
from ..services.recipes import create_recipe
from ..services.shopping import complete_shopping, get_or_create_list, rebuild_shopping_list

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
async def get_current_week(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    refresh_week_statuses(db, user_id)
    week = get_or_create_week(db, user_id, current_week_start())
    return serialize_week(db, week)


@router.get("/weeks/next")
async def get_next_week(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    refresh_week_statuses(db, user_id)
    week = get_or_create_week(db, user_id, next_week_start())
    return serialize_week(db, week)


@router.post("/weeks/{week_id}/generate")
@limiter.limit(AI_LIMIT)
async def generate(
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


@router.post("/weeks/{week_id}/lock")
async def lock_week(
    week_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Blocca la settimana a mano (di norma lo fa il completamento della spesa)."""
    week = _get_week(db, user_id, week_id)
    if week.is_locked:
        raise HTTPException(409, "Piano già bloccato")

    now = datetime.now(timezone.utc)
    week.is_locked = True
    week.locked_at = now
    week.lock_expires_at = now + timedelta(days=LOCK_DAYS)
    week.status = "locked"
    db.commit()
    return {
        "locked_at": week.locked_at.isoformat(),
        "lock_expires_at": week.lock_expires_at.isoformat(),
    }


@router.post("/weeks/{week_id}/unlock")
async def unlock_week(
    week_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Sblocco d'emergenza: la UI lo chiede con una conferma esplicita."""
    week = _get_week(db, user_id, week_id)
    week.is_locked = False
    week.locked_at = None
    week.lock_expires_at = None
    week.status = "active" if week.week_start_date == current_week_start() else "draft"
    db.commit()
    return serialize_week(db, week)


@router.post("/weeks/{week_id}/shopping-done")
async def shopping_done(
    week_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Alias di /api/shopping/current/complete per la settimana indicata."""
    week = _get_week(db, user_id, week_id)
    lst = get_or_create_list(db, week)
    return complete_shopping(db, user_id, week, lst)


# ── Pasti ──────────────────────────────────────────────────────────────────────


@router.get("/meals/{meal_id}")
async def get_meal(
    meal_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    meal, day, week = _get_meal(db, user_id, meal_id)
    slot = db.get(MealSlot, meal.meal_slot_id)
    data = serialize_meal(db, day, meal, slot, full=True)
    data["week"] = {
        "id": week.id,
        "week_start_date": week.week_start_date.isoformat(),
        "is_locked": week.is_locked,
        "status": week.status,
        "is_current": week.week_start_date == current_week_start(),
    }
    return data


@router.post("/meals/{meal_id}/regenerate")
@limiter.limit(AI_LIMIT)
async def regenerate(
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
async def assign_meal(
    meal_id: int,
    body: AssignMealRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Assegna al pasto una ricetta del ricettario o una scritta al momento."""
    meal, day, week = _get_meal(db, user.id, meal_id)
    ensure_unlocked(week)

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
    db.commit()

    rebuild_shopping_list(db, user.id, week)
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.delete("/meals/{meal_id}/recipe")
async def clear_meal(
    meal_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Svuota la casella (la ricetta resta nel ricettario)."""
    meal, day, week = _get_meal(db, user_id, meal_id)
    ensure_unlocked(week)

    meal.recipe_id = None
    meal.source = "ai_generated"
    meal.is_recurring = False
    meal.recurring_rule = None
    meal.is_followed = None
    db.commit()

    rebuild_shopping_list(db, user_id, week)
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)


@router.put("/meals/{meal_id}/recurring")
async def set_recurring(
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
async def set_followed(
    meal_id: int,
    body: FollowedRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Traccia se il pasto è stato davvero seguito. Funziona anche a piano bloccato:
    non modifica il piano, racconta com'è andata."""
    meal, day, week = _get_meal(db, user_id, meal_id)
    meal.is_followed = body.is_followed
    meal.deviation_notes = body.deviation_notes
    db.commit()

    slot = db.get(MealSlot, meal.meal_slot_id)
    return serialize_meal(db, day, meal, slot, full=True)
