"""Le frequenze settimanali della dieta e i gruppi del batch cooking."""

import logging

from sqlalchemy.orm import Session

from ...models import (
    DayPlan,
    Ingredient,
    MealSlot,
    PlannedMeal,
    RecipeIngredient,
    WeekPlan,
)
from ...utils import frequencies as freq
from .settimane import DAY_NAMES, get_active_diet, week_meals
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


# ── Frequenze settimanali ──────────────────────────────────────────────────────


def is_main_slot(slot: MealSlot, daily_calories: int | None) -> bool:
    """Pranzo e cena, non colazione e spuntini: il pasto che porta la proteina.

    Lo si riconosce dal peso e non dal nome — «Pranzo», «Pasto 2», «Lunch» — perché i
    nomi li scrive il nutrizionista: un pasto principale porta almeno un quarto delle
    calorie del giorno.
    """
    if not daily_calories:
        return False
    return (slot.target_calories or 0) >= 0.25 * daily_calories


def diet_frequencies(db: Session, user_id: int) -> list[dict]:
    diet = get_active_diet(db, user_id)
    return freq.clean(diet.frequencies) if diet else []


def _foods_in_recipe(db: Session, recipe_id: int) -> set[str]:
    """I gruppi di cui un piatto contiene una porzione vera (`freq.SOGLIA_G`)."""
    from ..macros import grams_of

    gruppi = set()
    rows = (
        db.query(RecipeIngredient, Ingredient)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
        .all()
    )
    for ri, ing in rows:
        food = freq.food_of(ing.category, ing.name)
        if not food:
            continue
        grams = grams_of(ing, ri.quantity, ri.unit)
        # Contato a pezzi senza un peso noto: un pezzo intero (un uovo, una scatoletta)
        # è una porzione.
        if grams is None or grams >= freq.SOGLIA_G[food]:
            gruppi.add(food)
    return gruppi


def frequency_counts(
    db: Session, week: WeekPlan, *, exclude_meal_ids: set[int] | None = None
) -> dict[str, int]:
    """Quante volte ogni gruppo compare nella settimana, un pasto alla volta.

    Contano i pasti con una ricetta, non saltati, su giorni non saltati: le stesse
    caselle che contano nei totali del giorno.
    """
    escludi = exclude_meal_ids or set()
    counts: dict[str, int] = {}
    for day, meal, _slot in week_meals(db, week):
        if day.is_skipped or meal.is_skipped or not meal.recipe_id or meal.id in escludi:
            continue
        for food in _foods_in_recipe(db, meal.recipe_id):
            counts[food] = counts.get(food, 0) + 1
    return counts


def frequency_report(db: Session, week: WeekPlan) -> list[dict]:
    regole = diet_frequencies(db, week.user_id)
    if not regole:
        return []
    return freq.report(regole, frequency_counts(db, week))


def _batch_groups(
    to_fill: list[tuple[DayPlan, PlannedMeal, MealSlot]],
) -> tuple[list[tuple[DayPlan, PlannedMeal, MealSlot]], dict[int, list[int]], dict[int, str]]:
    """Raggruppa le caselle dei pasti «cucinati una volta per più giorni».

    Per ogni pasto con `batch_days` > 1, i giorni da riempire si mettono in fila e si
    tagliano in gruppi di **giorni consecutivi** lunghi al massimo `batch_days`: un
    buco (un giorno saltato, una casella già piena) chiude il gruppo, perché un piatto
    cucinato lunedì per mercoledì e venerdì non è un batch, è un avanzo dimenticato.

    Restituisce le caselle da chiedere al modello (la prima di ogni gruppo, e tutte
    quelle dei pasti normali), le caselle che riceveranno la stessa ricetta
    (`{prima: [seguenti]}`) e la nota da scrivere accanto alla prima.

    La decisione la prende Python e non il modello, come il sorteggio delle cucine:
    «ripeti lo stesso pranzo per tre giorni» scritto in un prompt è un invito a
    variare lo stesso piatto, e la regola VARIETÀ lo vieterebbe comunque.
    """
    per_pasto: dict[int, list[tuple[DayPlan, PlannedMeal, MealSlot]]] = {}
    for row in to_fill:
        if (row[2].batch_days or 1) > 1:
            per_pasto.setdefault(row[2].id, []).append(row)

    seguaci: dict[int, list[int]] = {}
    note: dict[int, str] = {}
    fuori: set[int] = set()
    for righe in per_pasto.values():
        righe.sort(key=lambda r: r[0].day_of_week)
        massimo = righe[0][2].batch_days
        gruppo: list = []
        gruppi = []
        for r in righe:
            if gruppo and (
                r[0].day_of_week != gruppo[-1][0].day_of_week + 1 or len(gruppo) >= massimo
            ):
                gruppi.append(gruppo)
                gruppo = []
            gruppo.append(r)
        if gruppo:
            gruppi.append(gruppo)
        for g in gruppi:
            if len(g) < 2:
                continue
            capo = g[0][1].id
            seguaci[capo] = [r[1].id for r in g[1:]]
            fuori.update(seguaci[capo])
            altri = [DAY_NAMES[r[0].day_of_week] for r in g[1:]]
            note[capo] = (
                f" — BATCH: si cucina una volta e si mangia anche {' e '.join(altri)} "
                f"(lo stesso piatto per {len(g)} giorni): scegli un piatto che regge "
                f"{len(g)} giorni in frigo e si riscalda bene; ingredienti per UNA "
                f"porzione come sempre, e nel procedimento scrivi di prepararne {len(g)}"
            )

    prompt_rows = [r for r in to_fill if r[1].id not in fuori]
    return prompt_rows, seguaci, note
