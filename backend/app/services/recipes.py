"""Creazione e serializzazione delle ricette.

Le ricette arrivano da tre strade — generate dall'AI, scritte a mano dall'utente,
modificate via chat — ma la forma in DB deve essere una sola. Tutte passano da qui.
"""

from sqlalchemy.orm import Session

from ..models import Ingredient, Recipe, RecipeIngredient
from .ingredients import get_or_create_ingredient

_DIFFICULTIES = {"easy", "medium", "hard"}


def _clamp_difficulty(value: str | None) -> str:
    v = (value or "").strip().lower()
    return v if v in _DIFFICULTIES else "medium"


def _num(value, default=0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def create_recipe(
    db: Session,
    user_id: int,
    data: dict,
    *,
    is_custom: bool = False,
    generation_prompt: str | None = None,
) -> Recipe:
    """Crea una ricetta dal dizionario dell'AI o dal payload dell'utente.

    Il formato dei due è quasi lo stesso: i macro possono stare in `nutrition`
    (AI) o al primo livello (form utente), quindi si accettano entrambi invece di
    obbligare il router a rimappare.
    """
    nutrition = data.get("nutrition") or {}

    recipe = Recipe(
        user_id=user_id,
        title=(data.get("title") or "Ricetta senza nome").strip()[:200],
        description=(data.get("description") or None),
        prep_time_min=int(_num(data.get("prep_time_min"))),
        cook_time_min=int(_num(data.get("cook_time_min"))),
        difficulty=_clamp_difficulty(data.get("difficulty")),
        instructions=(data.get("instructions") or "").strip() or "Nessun procedimento.",
        calories=int(_num(nutrition.get("calories", data.get("calories")))),
        protein_g=_num(nutrition.get("protein_g", data.get("protein_g"))),
        carbs_g=_num(nutrition.get("carbs_g", data.get("carbs_g"))),
        fat_g=_num(nutrition.get("fat_g", data.get("fat_g"))),
        tags=data.get("tags"),
        is_custom=is_custom,
        generation_prompt=generation_prompt,
    )
    db.add(recipe)
    db.flush()

    for item in data.get("ingredients") or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        ingredient = get_or_create_ingredient(db, name)
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=_num(item.get("quantity")),
                unit=(item.get("unit") or "g").strip()[:20],
                notes=(item.get("notes") or None),
            )
        )

    db.flush()
    return recipe


def replace_ingredients(db: Session, recipe: Recipe, items: list[dict]) -> None:
    """Sostituisce in blocco gli ingredienti di una ricetta (modifica via chat)."""
    db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).delete()
    for item in items or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        ingredient = get_or_create_ingredient(db, name)
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=_num(item.get("quantity")),
                unit=(item.get("unit") or "g").strip()[:20],
                notes=(item.get("notes") or None),
            )
        )


def update_recipe_from_ai(db: Session, recipe: Recipe, data: dict) -> None:
    """Applica alla ricetta le modifiche proposte dalla chat.

    Aggiorna solo i campi presenti: se il modello rimanda solo titolo e ingredienti,
    il procedimento precedente non deve sparire.
    """
    nutrition = data.get("nutrition") or {}

    if data.get("title"):
        recipe.title = data["title"].strip()[:200]
    if data.get("description") is not None:
        recipe.description = data["description"] or None
    if data.get("instructions"):
        recipe.instructions = data["instructions"].strip()
    if data.get("prep_time_min") is not None:
        recipe.prep_time_min = int(_num(data["prep_time_min"]))
    if data.get("cook_time_min") is not None:
        recipe.cook_time_min = int(_num(data["cook_time_min"]))
    if data.get("difficulty"):
        recipe.difficulty = _clamp_difficulty(data["difficulty"])
    if data.get("tags"):
        recipe.tags = data["tags"]
    if nutrition:
        recipe.calories = int(_num(nutrition.get("calories"), recipe.calories))
        recipe.protein_g = _num(nutrition.get("protein_g"), recipe.protein_g)
        recipe.carbs_g = _num(nutrition.get("carbs_g"), recipe.carbs_g)
        recipe.fat_g = _num(nutrition.get("fat_g"), recipe.fat_g)
    if data.get("ingredients"):
        replace_ingredients(db, recipe, data["ingredients"])


def copy_recipe(db: Session, recipe: Recipe) -> Recipe:
    """Duplica una ricetta (serve ai pasti ricorrenti: ogni settimana la sua copia,
    così modificarla in una settimana non riscrive la storia delle precedenti)."""
    clone = Recipe(
        user_id=recipe.user_id,
        title=recipe.title,
        description=recipe.description,
        prep_time_min=recipe.prep_time_min,
        cook_time_min=recipe.cook_time_min,
        difficulty=recipe.difficulty,
        instructions=recipe.instructions,
        calories=recipe.calories,
        protein_g=recipe.protein_g,
        carbs_g=recipe.carbs_g,
        fat_g=recipe.fat_g,
        tags=recipe.tags,
        is_favorite=recipe.is_favorite,
        is_custom=recipe.is_custom,
    )
    db.add(clone)
    db.flush()

    for ri in (
        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).all()
    ):
        db.add(
            RecipeIngredient(
                recipe_id=clone.id,
                ingredient_id=ri.ingredient_id,
                quantity=ri.quantity,
                unit=ri.unit,
                notes=ri.notes,
            )
        )
    db.flush()
    return clone


# ── Serializzazione ────────────────────────────────────────────────────────────


def ingredients_of(db: Session, recipe_id: int) -> list[dict]:
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .order_by(RecipeIngredient.id)
        .all()
    )
    return [
        {
            "id": ri.id,
            "name": ing.name,
            "category": ing.category,
            "quantity": ri.quantity,
            "unit": ri.unit,
            "notes": ri.notes,
        }
        for ri, ing in rows
    ]


def serialize_recipe(db: Session, recipe: Recipe | None, *, full: bool = True) -> dict | None:
    if recipe is None:
        return None
    data = {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "prep_time_min": recipe.prep_time_min,
        "cook_time_min": recipe.cook_time_min,
        "difficulty": recipe.difficulty,
        "calories": recipe.calories,
        "protein_g": recipe.protein_g,
        "carbs_g": recipe.carbs_g,
        "fat_g": recipe.fat_g,
        "tags": recipe.tags,
        "rating": recipe.rating,
        "is_favorite": recipe.is_favorite,
        "is_custom": recipe.is_custom,
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
    }
    if full:
        data["instructions"] = recipe.instructions
        data["ingredients"] = ingredients_of(db, recipe.id)
    return data


def recipe_for_prompt(db: Session, recipe: Recipe) -> dict:
    """Versione compatta da infilare in un prompt: niente id, niente metadati."""
    return {
        "title": recipe.title,
        "description": recipe.description,
        "prep_time_min": recipe.prep_time_min,
        "cook_time_min": recipe.cook_time_min,
        "difficulty": recipe.difficulty,
        "ingredients": [
            {"name": i["name"], "quantity": i["quantity"], "unit": i["unit"], "notes": i["notes"]}
            for i in ingredients_of(db, recipe.id)
        ],
        "instructions": recipe.instructions,
        "nutrition": {
            "calories": recipe.calories,
            "protein_g": recipe.protein_g,
            "carbs_g": recipe.carbs_g,
            "fat_g": recipe.fat_g,
        },
        "tags": recipe.tags,
    }
