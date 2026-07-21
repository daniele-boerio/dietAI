"""Configurazione dell'utente: ingredienti di base, esclusi, dispensa, preferenze.

Sono le quattro liste che vincolano ogni generazione: cosa c'è sempre in casa, cosa
non deve comparire mai, cosa c'è adesso in dispensa e come si vuole mangiare.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import (
    BaseIngredient,
    ExcludedIngredient,
    Ingredient,
    PantryItem,
    UserPreferences,
)
from ..schemas import (
    ExcludedCreate,
    IngredientNameRequest,
    PantryCreate,
    PantryUpdate,
    PreferencesUpdate,
)
from ..services.ingredients import get_or_create_ingredient, normalize_name
from ..utils.pricing import DEFAULT_BASE_INGREDIENTS
from ..utils.units import format_quantity, normalize_unit

router = APIRouter(prefix="/api/config", tags=["Configurazione"])

BUDGET_LEVELS = {"economico", "medio", "premium"}


# ── Ingredienti di base ────────────────────────────────────────────────────────


@router.get("/base-ingredients")
async def list_base(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    rows = (
        db.query(BaseIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == BaseIngredient.ingredient_id)
        .filter(BaseIngredient.user_id == user_id)
        .order_by(Ingredient.name)
        .all()
    )
    return [
        {"id": b.id, "ingredient_id": i.id, "name": i.name, "category": i.category}
        for b, i in rows
    ]


@router.post("/base-ingredients", status_code=201)
async def add_base(
    body: IngredientNameRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ingredient = get_or_create_ingredient(db, body.ingredient_name)
    row = BaseIngredient(user_id=user_id, ingredient_id=ingredient.id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"'{ingredient.name}' è già tra gli ingredienti di base.")
    return {
        "id": row.id,
        "ingredient_id": ingredient.id,
        "name": ingredient.name,
        "category": ingredient.category,
    }


@router.post("/base-ingredients/defaults")
async def add_default_base(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Riempie la lista con i soliti sospetti (sale, olio, pepe...) durante l'onboarding."""
    added = 0
    for name in DEFAULT_BASE_INGREDIENTS:
        ingredient = get_or_create_ingredient(db, name)
        exists = (
            db.query(BaseIngredient)
            .filter(
                BaseIngredient.user_id == user_id,
                BaseIngredient.ingredient_id == ingredient.id,
            )
            .first()
        )
        if not exists:
            db.add(BaseIngredient(user_id=user_id, ingredient_id=ingredient.id))
            added += 1
    db.commit()
    return {"added": added}


@router.delete("/base-ingredients/{item_id}", status_code=204)
async def remove_base(
    item_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    deleted = (
        db.query(BaseIngredient)
        .filter(BaseIngredient.id == item_id, BaseIngredient.user_id == user_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Non trovato")
    return Response(status_code=204)


# ── Ingredienti esclusi ────────────────────────────────────────────────────────


@router.get("/excluded")
async def list_excluded(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    rows = (
        db.query(ExcludedIngredient, Ingredient)
        .outerjoin(Ingredient, Ingredient.id == ExcludedIngredient.ingredient_id)
        .filter(ExcludedIngredient.user_id == user_id)
        .all()
    )
    items = [
        {
            "id": e.id,
            "ingredient_id": e.ingredient_id,
            "name": i.name if i else e.custom_name,
            "category": i.category if i else None,
            "reason": e.reason,
        }
        for e, i in rows
    ]
    return sorted(items, key=lambda x: x["name"] or "")


@router.post("/excluded", status_code=201)
async def add_excluded(
    body: ExcludedCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Aggiunge un alimento da non usare mai.

    Se il nome corrisponde a un ingrediente noto lo si aggancia all'anagrafica (così
    la lista della spesa e la dispensa parlano la stessa lingua); altrimenti si
    conserva il testo libero — "frutti di mare" non è un ingrediente, è una famiglia.
    """
    clean = normalize_name(body.ingredient_name)
    if not clean:
        raise HTTPException(400, "Nome non valido")

    known = db.query(Ingredient).filter(Ingredient.name == clean).first()
    already = (
        db.query(ExcludedIngredient)
        .filter(
            ExcludedIngredient.user_id == user_id,
            (ExcludedIngredient.ingredient_id == known.id)
            if known
            else (ExcludedIngredient.custom_name == clean),
        )
        .first()
    )
    if already:
        raise HTTPException(409, f"'{clean}' è già nella lista degli esclusi.")

    row = ExcludedIngredient(
        user_id=user_id,
        ingredient_id=known.id if known else None,
        custom_name=None if known else clean,
        reason=body.reason,
    )
    db.add(row)
    db.commit()
    return {
        "id": row.id,
        "ingredient_id": row.ingredient_id,
        "name": known.name if known else clean,
        "category": known.category if known else None,
        "reason": row.reason,
    }


@router.delete("/excluded/{item_id}", status_code=204)
async def remove_excluded(
    item_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    deleted = (
        db.query(ExcludedIngredient)
        .filter(ExcludedIngredient.id == item_id, ExcludedIngredient.user_id == user_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Non trovato")
    return Response(status_code=204)


# ── Dispensa ───────────────────────────────────────────────────────────────────


def _serialize_pantry(item: PantryItem, ingredient: Ingredient) -> dict:
    return {
        "id": item.id,
        "ingredient_id": ingredient.id,
        "name": ingredient.name,
        "category": ingredient.category,
        "quantity": item.quantity_available,
        "unit": item.unit,
        "label": (
            format_quantity(item.quantity_available, item.unit or "unità")
            if item.quantity_available
            else None
        ),
    }


@router.get("/pantry")
async def list_pantry(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    rows = (
        db.query(PantryItem, Ingredient)
        .join(Ingredient, Ingredient.id == PantryItem.ingredient_id)
        .filter(PantryItem.user_id == user_id)
        .order_by(Ingredient.category, Ingredient.name)
        .all()
    )
    return [_serialize_pantry(p, i) for p, i in rows]


@router.post("/pantry", status_code=201)
async def add_pantry(
    body: PantryCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ingredient = get_or_create_ingredient(db, body.ingredient_name)
    existing = (
        db.query(PantryItem)
        .filter(PantryItem.user_id == user_id, PantryItem.ingredient_id == ingredient.id)
        .first()
    )
    if existing:
        raise HTTPException(409, f"'{ingredient.name}' è già in dispensa.")

    item = PantryItem(
        user_id=user_id,
        ingredient_id=ingredient.id,
        quantity_available=body.quantity,
        unit=normalize_unit(body.unit) if body.unit else None,
    )
    db.add(item)
    db.commit()
    return _serialize_pantry(item, ingredient)


@router.put("/pantry/{item_id}")
async def update_pantry(
    item_id: int,
    body: PantryUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    item = (
        db.query(PantryItem)
        .filter(PantryItem.id == item_id, PantryItem.user_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Non trovato")

    if "quantity" in body.model_fields_set:
        item.quantity_available = body.quantity
    if "unit" in body.model_fields_set:
        item.unit = normalize_unit(body.unit) if body.unit else None
    db.commit()
    return _serialize_pantry(item, db.get(Ingredient, item.ingredient_id))


@router.delete("/pantry/{item_id}", status_code=204)
async def remove_pantry(
    item_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    deleted = (
        db.query(PantryItem)
        .filter(PantryItem.id == item_id, PantryItem.user_id == user_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Non trovato")
    return Response(status_code=204)


# ── Preferenze ─────────────────────────────────────────────────────────────────


def _serialize_prefs(prefs: UserPreferences) -> dict:
    return {
        "prefer_seasonal": prefs.prefer_seasonal,
        "prefer_italian": prefs.prefer_italian,
        "max_prep_time_min": prefs.max_prep_time_min,
        "budget_level": prefs.budget_level,
    }


@router.get("/preferences")
async def get_preferences(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        # Default impliciti: la spec dice cucina italiana e stagionalità attive.
        prefs = UserPreferences(user_id=user_id, prefer_seasonal=True, prefer_italian=True)
        db.add(prefs)
        db.commit()
    return _serialize_prefs(prefs)


@router.put("/preferences")
async def update_preferences(
    body: PreferencesUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.budget_level and body.budget_level not in BUDGET_LEVELS:
        raise HTTPException(400, "Livello di budget non valido")

    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user_id)
        db.add(prefs)

    prefs.prefer_seasonal = body.prefer_seasonal
    prefs.prefer_italian = body.prefer_italian
    prefs.max_prep_time_min = body.max_prep_time_min
    prefs.budget_level = body.budget_level
    db.commit()
    return _serialize_prefs(prefs)


# ── Ricerca ingredienti (autocomplete) ─────────────────────────────────────────


@router.get("/ingredients/search")
async def search_ingredients(
    q: str = "", _user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Suggerimenti per i campi "aggiungi ingrediente"."""
    term = normalize_name(q)
    if len(term) < 2:
        return []
    rows = (
        db.query(Ingredient)
        .filter(Ingredient.name.ilike(f"%{term}%"))
        .order_by(Ingredient.name)
        .limit(10)
        .all()
    )
    return [{"id": i.id, "name": i.name, "category": i.category} for i in rows]
