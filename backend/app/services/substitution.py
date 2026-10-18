"""Sostituire un ingrediente in una ricetta: il modello propone, Python applica.

Sta qui e non in `recipes.py` perché vuole il contesto dell'utente (`build_context`),
e `planner` importa già `recipes`. Il router tiene la proprietà della ricetta e del
pasto e il client del modello, che i test sostituiscono lì.
"""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Ingredient, PlannedMeal, Recipe, RecipeIngredient, User
from . import macros, prompts
from .ai_client import AIError
from .exclusions import ExcludedFoodError, find_excluded
from .ingredients import get_or_create_ingredient, normalize_name
from .planner import build_context
from .recipes import (
    _num,
    fork_recipe_for_meal,
    ingredients_of,
    recipe_for_prompt,
    recompute_nutrition,
    set_declared_details,
    settle_recipe,
)
from .shopping import rebuild_shopping_list, rescale_pantry


def find_target(db: Session, recipe: Recipe, ingredient_name: str) -> tuple[RecipeIngredient, str]:
    """La riga della ricetta da sostituire, cercata col nome normalizzato; se no 404."""
    target_name = normalize_name(ingredient_name)
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe.id)
        .all()
    )
    match = next((ri for ri, ing in rows if ing.name == target_name), None)
    if not match:
        raise HTTPException(404, "Quell'ingrediente non è in questa ricetta.")
    return match, target_name


def substitute(
    db: Session,
    client,
    user: User,
    recipe: Recipe,
    meal: PlannedMeal | None,
    match: RecipeIngredient,
    target_name: str,
    reason: str | None,
) -> dict:
    """Chiede il sostituto al modello e lo scrive nella ricetta (o nella copia del pasto).

    Con un pasto la modifica vale per quella casella soltanto: lo stesso piatto in più
    giorni è una ricetta sola, e chi sta guardando il pasto di lunedì non si aspetta di
    cambiare anche giovedì. Senza, si sta modificando il piatto in sé (dal ricettario)
    e la modifica vale ovunque, che è quello che vuol dire modificare una ricetta.
    """
    context = build_context(db, user.id)
    excluded_line = next(
        (line for line in context.splitlines() if "ESCLUSI" in line), "nessuno"
    )
    base_line = next((line for line in context.splitlines() if "BASE" in line), "nessuno")
    # Le regole libere arrivavano a generazione e chat, non qui: «sono celiaco» scritto
    # nelle preferenze non impediva di proporre il farro come sostituto della pasta.
    rules_line = next(
        (line.strip(" -") for line in context.splitlines() if "REGOLE SCRITTE" in line),
        "REGOLE SCRITTE DALL'UTENTE: nessuna",
    )

    prompt = prompts.render(
        prompts.SUBSTITUTE_PROMPT,
        recipe=json.dumps(recipe_for_prompt(db, recipe), ensure_ascii=False, indent=2),
        ingredient=target_name,
        reason=reason or "non specificato",
        excluded=excluded_line,
        rules=rules_line,
        base=base_line,
    )

    data = client.generate_json(prompts.SUBSTITUTE_SYSTEM, prompt, max_tokens=4000)
    if not isinstance(data, dict) or not data.get("substitute"):
        raise AIError("Claude non ha proposto un sostituto valido.")

    substitute = data["substitute"]
    if not isinstance(substitute, dict) or not str(substitute.get("name") or "").strip():
        raise AIError("Claude non ha proposto un sostituto valido.")
    # Il sostituto non deve essere proprio quello che l'utente non può mangiare.
    trovati = find_excluded(db, user.id, [substitute["name"]])
    if trovati:
        raise ExcludedFoodError(
            f"Il sostituto proposto ({', '.join(trovati)}) è fra gli esclusi: "
            "non l'ho applicato.",
            trovati,
        )

    # Se la richiesta arriva da un pasto e quel piatto è in programma anche altrove, la
    # sostituzione se ne stacca una copia: da qui in poi sono due piatti diversi.
    if meal is not None:
        forked = fork_recipe_for_meal(db, meal)
        if forked is not None and forked.id != recipe.id:
            recipe = forked
            match = next(
                ri
                for ri in db.query(RecipeIngredient).filter(
                    RecipeIngredient.recipe_id == recipe.id
                )
                if ri.ingredient_id == match.ingredient_id
            )

    new_ingredient = get_or_create_ingredient(db, substitute.get("name") or "")
    match.ingredient_id = new_ingredient.id
    # I numeri del modello si leggono con `_num`, come quando una ricetta nasce: un
    # «q.b.» o un «circa 450» davano 500 dopo aver già pagato la chiamata.
    match.quantity = _num(substitute.get("quantity"), match.quantity) or match.quantity
    match.unit = str(substitute.get("unit") or match.unit)[:20]

    nutrition = data.get("updated_nutrition")
    if isinstance(nutrition, dict) and nutrition:
        recipe.calories = int(_num(nutrition.get("calories"), recipe.calories))
        recipe.protein_g = _num(nutrition.get("protein_g"), recipe.protein_g)
        recipe.carbs_g = _num(nutrition.get("carbs_g"), recipe.carbs_g)
        recipe.fat_g = _num(nutrition.get("fat_g"), recipe.fat_g)
        set_declared_details(recipe, nutrition)
    # I numeri del modello valgono solo se non si possono calcolare, come per una
    # ricetta che nasce: l'ingrediente nuovo cambia anche fibre, zuccheri e il resto.
    recompute_nutrition(db, recipe)

    # Se il piatto è appena diventato uguale a un altro che l'utente ha già, si torna a
    # una riga sola invece di lasciarne due identiche in ricettario.
    if meal is not None:
        db.flush()
        recipe = settle_recipe(db, meal) or recipe
        rescale_pantry(db, user.id, meal)

    db.commit()

    # La lista si riallinea: l'ingrediente da comprare non è più quello. Quello che
    # era già stato comprato resta in dispensa — se non serve più, lo si toglie a mano.
    rebuild_shopping_list(db, user.id)
    db.commit()

    return {
        "original": data.get("original") or {"name": target_name},
        "substitute": substitute,
        "updated_nutrition": {
            "calories": recipe.calories,
            "protein_g": recipe.protein_g,
            "carbs_g": recipe.carbs_g,
            "fat_g": recipe.fat_g,
            **{campo: getattr(recipe, campo) for campo in macros.CAMPI_DETTAGLIO},
        },
        "explanation": data.get("explanation"),
        "ingredients": ingredients_of(db, recipe.id),
    }
