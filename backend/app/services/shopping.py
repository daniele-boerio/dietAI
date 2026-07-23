"""Lista della spesa: aggregazione, stima costo, completamento e blocco.

La lista non è una cosa che l'utente compila: è una funzione del piano settimanale.
Ogni volta che il piano cambia viene ricalcolata da zero, sottraendo quello che in
casa c'è già (dispensa) e quello che c'è sempre (ingredienti di base).
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    BaseIngredient,
    DayPlan,
    Ingredient,
    PantryItem,
    PlannedMeal,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    WeekPlan,
)
from ..utils.units import format_quantity, price_for, to_base

LOCK_DAYS = 7

# Ordine dei reparti nella lista: è il giro che si fa al supermercato, non l'alfabeto.
CATEGORY_ORDER = [
    "verdura",
    "frutta",
    "carne",
    "pesce",
    "latticini",
    "uova",
    "cereali",
    "legumi",
    "surgelati",
    "condimenti",
    "bevande",
    "altro",
]

CATEGORY_LABELS = {
    "verdura": "Verdura",
    "frutta": "Frutta",
    "carne": "Carne",
    "pesce": "Pesce",
    "latticini": "Latticini",
    "uova": "Uova",
    "cereali": "Pane e cereali",
    "legumi": "Legumi",
    "surgelati": "Surgelati",
    "condimenti": "Dispensa e condimenti",
    "bevande": "Bevande",
    "altro": "Altro",
}


def get_or_create_list(db: Session, week: WeekPlan) -> ShoppingList:
    lst = db.query(ShoppingList).filter(ShoppingList.week_plan_id == week.id).first()
    if not lst:
        lst = ShoppingList(week_plan_id=week.id)
        db.add(lst)
        db.flush()
    return lst


def _aggregate_week_ingredients(db: Session, week: WeekPlan) -> dict[tuple[int, str], float]:
    """Somma le quantità di tutte le ricette della settimana, per (ingrediente, unità base).

    Giorni e pasti saltati restano fuori: i primi sono passati senza che si facesse la
    spesa (comprare oggi gli ingredienti di lunedì è esattamente lo spreco da
    evitare), i secondi hanno già la loro ricetta accodata su un altro giorno, e
    contarli qui vorrebbe dire comprare due volte lo stesso piatto.
    """
    rows = (
        db.query(RecipeIngredient)
        .join(PlannedMeal, PlannedMeal.recipe_id == RecipeIngredient.recipe_id)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .filter(
            DayPlan.week_plan_id == week.id,
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
        )
        .all()
    )

    totals: dict[tuple[int, str], float] = {}
    for ri in rows:
        quantity, unit = to_base(ri.quantity or 0, ri.unit)
        if quantity <= 0:
            continue
        key = (ri.ingredient_id, unit)
        totals[key] = totals.get(key, 0) + quantity
    return totals


def rebuild_shopping_list(db: Session, user_id: int, week: WeekPlan) -> ShoppingList:
    """Ricalcola la lista dal piano. Non tocca una lista già completata (spesa fatta)."""
    lst = get_or_create_list(db, week)
    if lst.is_completed:
        return lst

    totals = _aggregate_week_ingredients(db, week)

    base_ids = {
        r[0]
        for r in db.query(BaseIngredient.ingredient_id)
        .filter(BaseIngredient.user_id == user_id)
        .all()
    }

    pantry: dict[tuple[int, str], float] = {}
    for item in db.query(PantryItem).filter(PantryItem.user_id == user_id).all():
        if item.quantity_available:
            quantity, unit = to_base(item.quantity_available, item.unit or "unità")
            pantry[(item.ingredient_id, unit)] = pantry.get((item.ingredient_id, unit), 0) + quantity

    # Le spunte già messe si conservano tra un ricalcolo e l'altro: rigenerare una
    # ricetta non deve far ripartire da capo chi sta già girando per il supermercato.
    checked = {
        (i.ingredient_id, i.unit)
        for i in db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id)
        if i.is_checked
    }
    db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id).delete()

    estimated_total = 0.0
    for (ingredient_id, unit), quantity in totals.items():
        if ingredient_id in base_ids:
            continue  # sempre in casa, non si compra
        net = quantity - pantry.get((ingredient_id, unit), 0)
        if net <= 0:
            continue  # la dispensa copre tutto

        ingredient = db.get(Ingredient, ingredient_id)
        price = price_for(net, unit, ingredient.avg_price_per_unit, ingredient.price_unit)
        if price:
            estimated_total += price

        db.add(
            ShoppingListItem(
                shopping_list_id=lst.id,
                ingredient_id=ingredient_id,
                total_quantity=round(net, 2),
                unit=unit,
                is_checked=(ingredient_id, unit) in checked,
                estimated_price=price,
            )
        )

    lst.estimated_cost = round(estimated_total, 2) if estimated_total else None
    db.flush()
    return lst


def serialize_shopping_list(db: Session, week: WeekPlan, lst: ShoppingList) -> dict:
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )

    groups: dict[str, list[dict]] = {}
    summary: dict[str, float] = {}

    for item, ingredient in rows:
        category = ingredient.category or "altro"
        groups.setdefault(category, []).append(
            {
                "id": item.id,
                "ingredient_id": ingredient.id,
                "name": ingredient.name,
                "category": category,
                "quantity": item.total_quantity,
                "unit": item.unit,
                "label": format_quantity(item.total_quantity, item.unit),
                "is_checked": item.is_checked,
                "estimated_price": item.estimated_price,
            }
        )
        if item.estimated_price:
            summary[category] = round(summary.get(category, 0) + item.estimated_price, 2)

    categories = [
        {
            "key": key,
            "label": CATEGORY_LABELS.get(key, key.capitalize()),
            "items": sorted(groups[key], key=lambda i: i["name"]),
            "estimated_price": summary.get(key),
        }
        for key in CATEGORY_ORDER
        if key in groups
    ]

    total_items = sum(len(c["items"]) for c in categories)
    checked_items = sum(1 for c in categories for i in c["items"] if i["is_checked"])

    # L'avviso "la lista è più corta" parla di spesa mancata, quindi conta solo i
    # giorni saltati perché ormai passati: una giornata saltata a mano più avanti
    # (weekend fuori) accorcia la lista pure lei, ma è una scelta esplicita e non ha
    # bisogno di essere spiegata come un ammanco.
    from .planner import today

    days = (
        db.query(DayPlan)
        .filter(DayPlan.week_plan_id == week.id)
        .order_by(DayPlan.day_of_week)
        .all()
    )
    covered = [d for d in days if not d.is_skipped]
    past_skipped = [d for d in days if d.is_skipped and d.date < today()]

    return {
        "id": lst.id,
        "week_plan_id": week.id,
        "week_start_date": week.week_start_date.isoformat(),
        "is_completed": lst.is_completed,
        "completed_at": lst.completed_at.isoformat() if lst.completed_at else None,
        "estimated_cost": lst.estimated_cost,
        "is_locked": week.is_locked,
        "days_skipped": len(past_skipped),
        "covers_from": covered[0].date.isoformat() if covered else None,
        "total_items": total_items,
        "checked_items": checked_items,
        "categories": categories,
        "categories_summary": summary,
    }


def shopping_list_summary(db: Session, lst: ShoppingList) -> str:
    """Gli articoli in lista come stringa piatta, per infilarli nel prompt della chat."""
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )
    names = [
        f"{ing.name} ({format_quantity(item.total_quantity, item.unit)})"
        for item, ing in rows
    ]
    return ", ".join(sorted(names)) if names else "(lista vuota)"


def complete_shopping(db: Session, user_id: int, week: WeekPlan, lst: ShoppingList) -> dict:
    """Segna la spesa come fatta: blocca il piano per 7 giorni e riempie la dispensa.

    Il blocco è il punto del progetto: una volta comprato il cibo, cambiare le
    ricette significa buttarlo. Da qui in poi la settimana è in sola lettura e le
    modifiche si fanno sulla settimana successiva.
    """
    if lst.is_completed:
        raise HTTPException(409, "Questa spesa risulta già completata.")

    now = datetime.now(timezone.utc)

    lst.is_completed = True
    lst.completed_at = now

    week.is_locked = True
    week.locked_at = now
    week.lock_expires_at = now + timedelta(days=LOCK_DAYS)
    week.status = "locked"

    # Quello che è stato spuntato è finito nel carrello, quindi ora è in dispensa.
    for item in db.query(ShoppingListItem).filter(
        ShoppingListItem.shopping_list_id == lst.id, ShoppingListItem.is_checked.is_(True)
    ):
        pantry = (
            db.query(PantryItem)
            .filter(PantryItem.user_id == user_id, PantryItem.ingredient_id == item.ingredient_id)
            .first()
        )
        if pantry and pantry.unit == item.unit and pantry.quantity_available:
            pantry.quantity_available += item.total_quantity
        elif pantry:
            pantry.quantity_available = item.total_quantity
            pantry.unit = item.unit
        else:
            db.add(
                PantryItem(
                    user_id=user_id,
                    ingredient_id=item.ingredient_id,
                    quantity_available=item.total_quantity,
                    unit=item.unit,
                )
            )

    db.commit()
    return {
        "detail": "Spesa completata: il piano è bloccato per 7 giorni.",
        "week_locked_until": week.lock_expires_at.isoformat(),
    }


def export_text(db: Session, week: WeekPlan, lst: ShoppingList) -> str:
    """Lista in testo semplice, da incollare in un messaggio o in una nota."""
    data = serialize_shopping_list(db, week, lst)
    lines = [f"Lista della spesa — settimana del {week.week_start_date.strftime('%d/%m/%Y')}", ""]

    for category in data["categories"]:
        lines.append(f"{category['label'].upper()}")
        for item in category["items"]:
            mark = "x" if item["is_checked"] else " "
            lines.append(f"  [{mark}] {item['name']} — {item['label']}")
        lines.append("")

    if data["estimated_cost"]:
        lines.append(f"Totale stimato: € {data['estimated_cost']:.2f}".replace(".", ","))
    return "\n".join(lines)
