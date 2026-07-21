"""Ricettario: archivio delle ricette, voti, preferiti e sostituzione ingredienti."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, get_current_user_id
from ..database import get_db
from ..models import DayPlan, Ingredient, PlannedMeal, Recipe, RecipeIngredient, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import FavoriteRequest, RatingRequest, RecipeCreate, SubstituteRequest
from ..services import prompts
from ..services.ai_client import AIError, get_client
from ..services.ingredients import get_or_create_ingredient, normalize_name
from ..services.planner import DAY_NAMES, build_context
from ..services.recipes import create_recipe, ingredients_of, recipe_for_prompt, serialize_recipe
from ..services.shopping import rebuild_shopping_list

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
    difficulty: str | None = None,
    search: str | None = None,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    query = db.query(Recipe).filter(Recipe.user_id == user_id)

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
    pasto e il pulsante di rigenerazione.
    """
    recipe = _get_recipe(db, user.id, recipe_id)

    target_name = normalize_name(body.ingredient_to_replace)
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe.id)
        .all()
    )
    match = next((ri for ri, ing in rows if ing.name == target_name), None)
    if not match:
        raise HTTPException(404, "Quell'ingrediente non è in questa ricetta.")

    context = build_context(db, user.id)
    excluded_line = next(
        (line for line in context.splitlines() if "ESCLUSI" in line), "nessuno"
    )
    base_line = next((line for line in context.splitlines() if "BASE" in line), "nessuno")

    prompt = prompts.render(
        prompts.SUBSTITUTE_PROMPT,
        recipe=json.dumps(recipe_for_prompt(db, recipe), ensure_ascii=False, indent=2),
        ingredient=target_name,
        reason=body.reason or "non specificato",
        excluded=excluded_line,
        base=base_line,
    )

    client = get_client(db, user, "chat")
    data = client.generate_json(prompts.SUBSTITUTE_SYSTEM, prompt, max_tokens=4000)
    if not isinstance(data, dict) or not data.get("substitute"):
        raise AIError("Claude non ha proposto un sostituto valido.")

    substitute = data["substitute"]
    new_ingredient = get_or_create_ingredient(db, substitute.get("name") or "")
    match.ingredient_id = new_ingredient.id
    match.quantity = float(substitute.get("quantity") or match.quantity)
    match.unit = (substitute.get("unit") or match.unit)[:20]

    nutrition = data.get("updated_nutrition") or {}
    if nutrition:
        recipe.calories = int(nutrition.get("calories", recipe.calories))
        recipe.protein_g = float(nutrition.get("protein_g", recipe.protein_g))
        recipe.carbs_g = float(nutrition.get("carbs_g", recipe.carbs_g))
        recipe.fat_g = float(nutrition.get("fat_g", recipe.fat_g))

    db.commit()

    # La lista della spesa delle settimane non bloccate che usano questa ricetta
    # va riallineata: l'ingrediente comprato non è più quello.
    weeks = (
        db.query(WeekPlan)
        .join(DayPlan, DayPlan.week_plan_id == WeekPlan.id)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .filter(PlannedMeal.recipe_id == recipe.id, WeekPlan.is_locked.is_(False))
        .distinct()
        .all()
    )
    for week in weeks:
        rebuild_shopping_list(db, user.id, week)
    db.commit()

    return {
        "original": data.get("original") or {"name": target_name},
        "substitute": substitute,
        "updated_nutrition": {
            "calories": recipe.calories,
            "protein_g": recipe.protein_g,
            "carbs_g": recipe.carbs_g,
            "fat_g": recipe.fat_g,
        },
        "explanation": data.get("explanation"),
        "ingredients": ingredients_of(db, recipe.id),
    }
