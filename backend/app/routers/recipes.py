"""Ricettario: archivio delle ricette, voti, preferiti e sostituzione ingredienti."""

import logging
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_user_id
from ..database import get_db
from ..models import DayPlan, PlannedMeal, Recipe, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import (
    FavoriteRequest,
    RatingRequest,
    RecipeCreate,
    RecipeFromText,
    RecipeUpdate,
    SubstituteRequest,
)
from ..services.ai_client import get_client
from ..services.planner import DAY_NAMES
from ..services.ownership import own_week
from ..services.recipes import (
    create_from_text,
    create_recipe,
    edit_recipe,
    low_rated_clause,
    proposable_clause,
    saved_clause,
    serialize_recipe,
)
from ..services import substitution

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recipes", tags=["Ricette"])


def _get_recipe(db: Session, user_id: int, recipe_id: int) -> Recipe:
    recipe = (
        db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.user_id == user_id).first()
    )
    if not recipe:
        raise HTTPException(404, "Ricetta non trovata")
    return recipe


def _usage_history(db: Session, recipe_id: int) -> list[dict]:
    """Quando è stata mangiata questa ricetta: serve a capire se è già stata usata di recente."""
    rows = (
        db.query(DayPlan, PlannedMeal)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .filter(PlannedMeal.recipe_id == recipe_id)
        .order_by(DayPlan.date.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "meal_id": meal.id,
            "date": day.date.isoformat(),
            "day_name": DAY_NAMES[day.day_of_week],
            "is_followed": meal.is_followed,
        }
        for day, meal in rows
    ]


@router.get("")
def list_recipes(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    rating_min: int | None = Query(None, ge=1, le=5),
    is_favorite: bool | None = None,
    # «saved» è il ricettario (preferite, votate, scritte da te), «proposable» la scelta
    # per un pasto (niente voti bassi), «low» le votate male.
    scope: Literal["saved", "proposable", "low"] = "saved",
    difficulty: str | None = None,
    search: str | None = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    query = db.query(Recipe).filter(Recipe.user_id == user_id)
    query = query.filter(
        {"saved": saved_clause, "proposable": proposable_clause, "low": low_rated_clause}[
            scope
        ]()
    )

    if rating_min is not None:
        query = query.filter(Recipe.rating >= rating_min)
    if is_favorite:
        query = query.filter(Recipe.is_favorite.is_(True))
    if difficulty in ("easy", "medium", "hard"):
        query = query.filter(Recipe.difficulty == difficulty)
    if search:
        query = query.filter(Recipe.title.ilike(f"%{search.strip()}%"))

    total = query.count()
    rows = (
        query.order_by(Recipe.is_favorite.desc(), Recipe.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "items": [serialize_recipe(db, r, full=False) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.post("/from-text", status_code=201)
@limiter.limit(AI_LIMIT)
def create_recipe_from_text(
    request: Request,
    body: RecipeFromText,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Una ricetta tua — ingredienti, procedimento, porzioni — pesata per una porzione.

    Il modello divide le quantità, il server calcola i macro dagli ingredienti
    (`recipes.create_from_text`). Nasce nel ricettario, pronta da mettere in un pasto.
    """
    client = get_client(db, user, "chat")
    recipe = create_from_text(
        db,
        client,
        user.id,
        title=body.title,
        ingredients=body.ingredients,
        instructions=body.instructions,
        portions=body.portions,
    )
    db.commit()
    return serialize_recipe(db, recipe, full=True)


@router.get("/unsaved")
def unsaved_recipes(
    week_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Le ricette di questa settimana e della precedente che non hai ancora salvato.

    Le chiede la finestra di generazione: le ricette non salvate escono dal ricettario,
    e una settimana nuova è il momento in cui quelle vecchie smettono di servire —
    quindi è lì che si chiede se ce n'è qualcuna da tenere.
    """
    week = own_week(db, user_id, week_id)
    inizio = week.week_start_date - timedelta(days=7)
    fine = week.week_start_date + timedelta(days=6)
    rows = (
        db.query(Recipe, DayPlan)
        .join(PlannedMeal, PlannedMeal.recipe_id == Recipe.id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(
            WeekPlan.user_id == user_id,
            Recipe.user_id == user_id,
            DayPlan.date >= inizio,
            DayPlan.date <= fine,
            ~saved_clause(),
        )
        .order_by(DayPlan.date)
        .all()
    )
    visti: dict[int, dict] = {}
    for recipe, day in rows:
        visti.setdefault(
            recipe.id,
            {
                "id": recipe.id,
                "title": recipe.title,
                "calories": recipe.calories,
                "date": day.date.isoformat(),
                "day_name": DAY_NAMES[day.day_of_week],
                "rating": recipe.rating,
                "is_favorite": recipe.is_favorite,
            },
        )
    return list(visti.values())


@router.get("/{recipe_id}")
def get_recipe(
    recipe_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    recipe = _get_recipe(db, user_id, recipe_id)
    data = serialize_recipe(db, recipe, full=True)
    data["usage_history"] = _usage_history(db, recipe.id)
    return data


@router.post("", status_code=201)
def create_custom_recipe(
    body: RecipeCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    recipe = create_recipe(db, user_id, body.model_dump(), is_custom=True)
    db.commit()
    return serialize_recipe(db, recipe, full=True)


@router.put("/{recipe_id}")
def update_recipe(
    recipe_id: int,
    body: RecipeUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Correggere a mano una ricetta del ricettario (`recipes.edit_recipe`)."""
    recipe = _get_recipe(db, user_id, recipe_id)
    edit_recipe(db, user_id, recipe, body.model_dump())
    db.commit()
    data = serialize_recipe(db, recipe, full=True)
    data["usage_history"] = _usage_history(db, recipe.id)
    return data


@router.put("/{recipe_id}/rate")
def rate_recipe(
    recipe_id: int,
    body: RatingRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Il voto non è decorativo: entra nel contesto delle generazioni successive."""
    recipe = _get_recipe(db, user_id, recipe_id)
    recipe.rating = body.rating
    db.commit()
    return serialize_recipe(db, recipe, full=False)


@router.put("/{recipe_id}/favorite")
def favorite_recipe(
    recipe_id: int,
    body: FavoriteRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    recipe = _get_recipe(db, user_id, recipe_id)
    recipe.is_favorite = body.is_favorite
    db.commit()
    return serialize_recipe(db, recipe, full=False)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(
    recipe_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    recipe = _get_recipe(db, user_id, recipe_id)
    in_use = db.query(PlannedMeal).filter(PlannedMeal.recipe_id == recipe.id).first()
    if in_use:
        raise HTTPException(409, "La ricetta è usata in un piano: rimuovila prima da lì.")
    db.delete(recipe)
    db.commit()
    return Response(status_code=204)


@router.post("/{recipe_id}/substitute")
@limiter.limit(AI_LIMIT)
def substitute_ingredient(
    request: Request,
    recipe_id: int,
    body: SubstituteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chiede a Claude un sostituto per un ingrediente e aggiorna la ricetta.

    L'aggiornamento è immediato: se non piace, l'utente ha comunque la chat del
    pasto e il pulsante di rigenerazione. Con `meal_id` vale per quella casella
    soltanto (`substitution.substitute`).
    """
    recipe = _get_recipe(db, user.id, recipe_id)
    meal = None
    if body.meal_id is not None:
        meal = (
            db.query(PlannedMeal)
            .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
            .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
            .filter(
                PlannedMeal.id == body.meal_id,
                PlannedMeal.recipe_id == recipe.id,
                WeekPlan.user_id == user.id,
            )
            .first()
        )
        if meal is None:
            # Senza pasto la sostituzione vale per il piatto ovunque: un `meal_id`
            # sbagliato non deve allargarla a tutti i giorni che lo condividono.
            raise HTTPException(404, "Pasto non trovato")

    match, target_name = substitution.find_target(db, recipe, body.ingredient_to_replace)
    client = get_client(db, user, "chat")
    return substitution.substitute(
        db, client, user, recipe, meal, match, target_name, body.reason
    )
