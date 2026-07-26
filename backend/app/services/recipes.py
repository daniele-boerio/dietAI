"""Creazione e serializzazione delle ricette.

Le ricette arrivano da tre strade — generate dall'AI, scritte a mano dall'utente,
modificate via chat — ma la forma in DB deve essere una sola. Tutte passano da qui.
"""

from sqlalchemy.orm import Session

from ..models import Ingredient, Recipe, RecipeIngredient
from .ingredients import get_or_create_ingredient

_DIFFICULTIES = {"easy", "medium", "hard"}


def _text(value) -> str:
    """Riduce a stringa quello che manda il modello.

    I prompt chiedono stringhe, ma un modello ogni tanto risponde con una lista o un
    numero: senza questa conversione il primo `.strip()` faceva 500 e la risposta —
    già pagata — andava persa.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(t for t in (_text(v) for v in value) if t)
    return str(value).strip()


def _instructions(value) -> str:
    """Il procedimento, che il prompt chiede numerato e un passo per riga.

    Quando arriva come lista di passi la si numera qui, così il risultato è lo stesso
    di quando arriva già come testo.
    """
    if isinstance(value, (list, tuple)):
        steps = [s for s in (_text(v) for v in value) if s]
        if not any(s[:1].isdigit() or s[:1] in "-•*" for s in steps):
            steps = [f"{i}. {s}" for i, s in enumerate(steps, 1)]
        return "\n".join(steps)
    return _text(value)


def _dict(value) -> dict:
    """Un sotto-oggetto del JSON dell'AI, o `{}` se il modello ha mandato altro."""
    return value if isinstance(value, dict) else {}


def _clamp_difficulty(value) -> str:
    v = _text(value).lower()
    return v if v in _DIFFICULTIES else "medium"


def _num(value, default=0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _clean_ingredients(items) -> list[dict]:
    """Normalizza gli ingredienti del JSON, scartando quelli senza un nome."""
    out = []
    for item in items if isinstance(items, (list, tuple)) else []:
        item = _dict(item)
        name = _text(item.get("name"))
        if not name:
            continue
        out.append(
            {
                "name": name,
                "quantity": _num(item.get("quantity")),
                "unit": _text(item.get("unit"))[:20] or "g",
                "notes": _text(item.get("notes")) or None,
            }
        )
    return out


def _add_ingredients(db: Session, recipe: Recipe, items: list[dict]) -> None:
    for item in items:
        ingredient = get_or_create_ingredient(db, item["name"])
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ingredient.id,
                quantity=item["quantity"],
                unit=item["unit"],
                notes=item["notes"],
            )
        )


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
    nutrition = _dict(data.get("nutrition"))

    recipe = Recipe(
        user_id=user_id,
        title=_text(data.get("title"))[:200] or "Ricetta senza nome",
        description=_text(data.get("description")) or None,
        prep_time_min=int(_num(data.get("prep_time_min"))),
        cook_time_min=int(_num(data.get("cook_time_min"))),
        difficulty=_clamp_difficulty(data.get("difficulty")),
        instructions=_instructions(data.get("instructions")) or "Nessun procedimento.",
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

    _add_ingredients(db, recipe, _clean_ingredients(data.get("ingredients")))

    db.flush()
    return recipe


def replace_ingredients(db: Session, recipe: Recipe, items: list[dict]) -> None:
    """Sostituisce in blocco gli ingredienti di una ricetta (modifica via chat).

    Se dal JSON non si salva un solo ingrediente valido non si cancella niente: una
    ricetta rimasta senza ingredienti uscirebbe dalla lista della spesa in silenzio.
    """
    cleaned = _clean_ingredients(items)
    if not cleaned:
        return
    db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).delete()
    _add_ingredients(db, recipe, cleaned)


def update_recipe_from_ai(db: Session, recipe: Recipe, data: dict) -> None:
    """Applica alla ricetta le modifiche proposte dalla chat.

    Aggiorna solo i campi presenti: se il modello rimanda solo titolo e ingredienti,
    il procedimento precedente non deve sparire.
    """
    nutrition = _dict(data.get("nutrition"))

    if data.get("title"):
        recipe.title = _text(data["title"])[:200] or recipe.title
    if data.get("description") is not None:
        recipe.description = _text(data["description"]) or None
    if data.get("instructions"):
        recipe.instructions = _instructions(data["instructions"]) or recipe.instructions
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
