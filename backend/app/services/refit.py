"""Riportare nel target le ricette già in programma: il ritocco a posteriori.

`fit_to_target` lavora sulle ricette che nascono. Quelle generate prima che i macro si
calcolassero dagli ingredienti — o ricalcolate con `recompute_macros`, che dice il vero
ma non ritocca niente — possono essere fuori dal ±10% che la dieta chiede. Qui si
ritoccano le loro grammature con lo stesso calcolo della generazione, senza chiamare
il modello.

Tre confini, e vengono tutti da «quello che è già stato non si riscrive»:

- **Solo da oggi in avanti**, e solo le caselle non ancora segnate né saltate: una
  ricetta mangiata ieri è stata comprata e cucinata con quelle grammature, e la
  dispensa si è scalata su quelle (`pantry_used`).
- **Una ricetta condivisa non si tocca sotto i piedi degli altri.** Se la usano anche
  caselle fuori dal gruppo da ritoccare — il passato, un pasto con un altro target —
  se ne stacca una copia per le caselle del gruppo, come fa la chat (`copy_recipe`).
- **Le ricette scritte a mano no**: i numeri li ha scritti l'utente.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import DayPlan, MealSlot, PlannedMeal, Recipe, RecipeIngredient, WeekPlan
from . import macros
from .recipes import copy_recipe, recompute_nutrition


@dataclass
class Esito:
    ritoccate: list[dict] = field(default_factory=list)
    gia_dentro: int = 0
    non_calcolabili: list[str] = field(default_factory=list)
    fuori_portata: list[str] = field(default_factory=list)  # nemmeno coi limiti
    utenti: set[int] = field(default_factory=set)


def _items(db: Session, recipe_id: int) -> list[dict]:
    return [
        {
            "ri_id": ri.id,
            "ingredient_id": ri.ingredient_id,
            "quantity": ri.quantity,
            "unit": ri.unit,
            "name": "",
            "notes": ri.notes,
        }
        for ri in db.query(RecipeIngredient).filter_by(recipe_id=recipe_id).all()
    ]


def _target(slot: MealSlot) -> macros.Target:
    return macros.Target(
        kcal=slot.target_calories or 0,
        protein=slot.target_protein_g or 0,
        carbs=slot.target_carbs_g or 0,
        fat=slot.target_fat_g or 0,
    )


def refit_future_meals(
    db: Session, oggi, *, user_id: int | None = None, apply: bool = False
) -> Esito:
    """Ritocca le ricette in programma da `oggi` in avanti che stanno fuori target.

    Con `apply=False` non scrive niente: calcola e racconta.
    """
    esito = Esito()
    q = (
        db.query(PlannedMeal, DayPlan, MealSlot, WeekPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .filter(
            DayPlan.date >= oggi,
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
            PlannedMeal.is_followed.is_(None),
            PlannedMeal.recipe_id.isnot(None),
            MealSlot.auto_generate.is_(True),
        )
    )
    if user_id is not None:
        q = q.filter(WeekPlan.user_id == user_id)

    # Gruppi: la stessa ricetta sotto lo stesso target. Una colazione ripetuta sette
    # giorni è un gruppo solo, e si ritocca una volta.
    gruppi: dict[tuple, list] = {}
    for meal, day, slot, week in q.all():
        chiave = (
            meal.recipe_id,
            slot.target_calories,
            slot.target_protein_g,
            slot.target_carbs_g,
            slot.target_fat_g,
        )
        gruppi.setdefault(chiave, []).append((meal, day, slot, week))

    for (recipe_id, *_), caselle in gruppi.items():
        recipe = db.get(Recipe, recipe_id)
        if recipe is None or recipe.is_custom:
            continue
        slot = caselle[0][2]
        target = _target(slot)
        items = _items(db, recipe_id)
        prima = macros.compute(db, items)
        if prima is None:
            esito.non_calcolabili.append(recipe.title)
            continue
        if macros._dentro(prima, target):
            esito.gia_dentro += 1
            continue

        ritoccati = macros.fit_to_target(db, items, target)
        dopo = macros.compute(db, ritoccati)
        if dopo is None or not macros._dentro(dopo, target):
            # Dentro i limiti del ritocco il target non si raggiunge: il piatto è un
            # altro, e ci vuole il modello. Si dice, invece di peggiorarlo a metà.
            esito.fuori_portata.append(recipe.title)
            if dopo is None or abs(dopo.kcal - target.kcal) >= abs(prima.kcal - target.kcal):
                continue

        esito.ritoccate.append({
            "title": recipe.title,
            "caselle": len(caselle),
            "kcal_prima": round(prima.kcal),
            "kcal_dopo": round(dopo.kcal),
            "target": round(target.kcal),
            "modifiche": [
                (i["ingredient_id"], i["quantity"], j["quantity"], i["unit"])
                for i, j in zip(items, ritoccati)
                if i["quantity"] != j["quantity"]
            ],
        })
        esito.utenti.add(caselle[0][3].user_id)
        if not apply:
            continue

        # Se la ricetta la usa anche qualcuno fuori dal gruppo, il gruppo ne prende
        # una copia sua: il passato e gli altri target non si toccano.
        ids_gruppo = {m.id for m, *_ in caselle}
        altrove = (
            db.query(PlannedMeal)
            .filter(PlannedMeal.recipe_id == recipe_id, PlannedMeal.id.notin_(ids_gruppo))
            .first()
        )
        bersaglio = recipe
        if altrove is not None:
            bersaglio = copy_recipe(db, recipe)
            for meal, *_ in caselle:
                meal.recipe_id = bersaglio.id
            db.flush()

        nuove = {i["ingredient_id"]: j["quantity"] for i, j in zip(items, ritoccati)}
        for ri in db.query(RecipeIngredient).filter_by(recipe_id=bersaglio.id).all():
            if ri.ingredient_id in nuove:
                ri.quantity = nuove[ri.ingredient_id]
        recompute_nutrition(db, bersaglio)

    if apply:
        from .shopping import rebuild_shopping_list

        db.flush()
        for uid in esito.utenti:
            rebuild_shopping_list(db, uid)
        db.commit()
    return esito
