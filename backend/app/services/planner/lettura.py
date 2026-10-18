"""La settimana come la legge il frontend: pasti, ricette e target."""

import logging

from sqlalchemy.orm import Session

from ...models import (
    DayPlan,
    MealSlot,
    PlannedMeal,
    Recipe,
    WeekPlan,
)
from ..recipes import (
    serialize_recipe,
)
from .settimane import DAY_NAMES, current_week_start, week_meals
from .stato import generation_error, generation_outcome, is_generating
from .pasti import is_generable
from .frequenze import frequency_report
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


# ── Lettura della settimana ────────────────────────────────────────────────────


def serialize_meal(
    db: Session, day: DayPlan, meal: PlannedMeal, slot: MealSlot, *, full: bool = False
) -> dict:
    recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
    data = {
        "id": meal.id,
        "day_of_week": day.day_of_week,
        "day_name": DAY_NAMES[day.day_of_week],
        "date": day.date.isoformat(),
        # Il giorno è passato senza spesa: la casella è in sola lettura come quando
        # il piano è bloccato, ma per un motivo diverso.
        "day_is_skipped": day.is_skipped,
        "slot_id": slot.id,
        "slot_name": slot.name,
        "slot_order": slot.order_index,
        "target": {
            "calories": slot.target_calories,
            "protein_g": slot.target_protein_g,
            "carbs_g": slot.target_carbs_g,
            "fat_g": slot.target_fat_g,
            "notes": slot.notes,
        },
        # "lo gestisco io": niente da generare, ma i macro contano nella giornata
        "self_managed": not slot.auto_generate,
        "generable": is_generable(day, meal, slot),
        # Per quante persone si cucina: la ricetta è per una, e chi la cucina per due
        # deve leggerlo accanto agli ingredienti.
        "servings": slot.servings or 1,
        "source": meal.source,
        # "Ho mangiato altro": la ricetta qui sotto è quella che era in programma, ma
        # non è stata cucinata — si è accodata più avanti e qui non conta più.
        "is_skipped": meal.is_skipped,
        "is_recurring": meal.is_recurring,
        "recurring_rule": meal.recurring_rule,
        "is_followed": meal.is_followed,
        "deviation_notes": meal.deviation_notes,
        "eaten_nutrition": meal.eaten_nutrition,
        "recipe": serialize_recipe(db, recipe, full=full),
    }

    # Un pasto mostrato da solo (la pagina di dettaglio) ha bisogno di sapere in che
    # stato è la sua settimana: senza, non può nemmeno dire se è modificabile. Sta
    # qui e non nel router perché la pagina si ridisegna con la risposta del pulsante
    # appena premuto, non solo con la lettura iniziale: quando `week` c'era solo nella
    # GET, il primo clic su "L'ho seguito" restituiva un pasto senza settimana e la
    # schermata si spegneva con un TypeError.
    if full:
        week = db.get(WeekPlan, day.week_plan_id)
        data["week"] = {
            "id": week.id,
            "week_start_date": week.week_start_date.isoformat(),
            "status": week.status,
            "is_current": week.week_start_date == current_week_start(),
            # Solo per dire dove ci si trova: una settimana passata si modifica come
            # tutte le altre, semplicemente non è quella in corso.
            "is_past": week.week_start_date < current_week_start(),
        }
    return data


def serialize_week(db: Session, week: WeekPlan) -> dict:
    rows = week_meals(db, week)
    days: dict[int, dict] = {}

    for day, meal, slot in rows:
        entry = days.setdefault(
            day.day_of_week,
            {
                "id": day.id,
                "date": day.date.isoformat(),
                "day_of_week": day.day_of_week,
                "day_name": DAY_NAMES[day.day_of_week],
                # Giorno passato senza spesa: le ricette sono slittate via, la
                # griglia lo mostra spento e la lista della spesa lo ignora.
                "is_skipped": day.is_skipped,
                "meals": [],
            },
        )
        entry["meals"].append(serialize_meal(db, day, meal, slot))

    for entry in days.values():
        # I pasti gestiti dall'utente non hanno una ricetta, ma lui li mangia centrando
        # i target: contarli col loro target è l'unico modo perché il totale del giorno
        # rappresenti quello che si mangia davvero e non solo quello che ha scritto l'AI.
        def _macros(meal: dict) -> dict:
            # Un pasto saltato conserva la ricetta per memoria, ma non è stato
            # mangiato: conta quello che si è mangiato al suo posto, la stima di «ho
            # mangiato altro: cosa?» (zero se non si sa, o «non ho mangiato niente»).
            if meal["is_skipped"]:
                return meal["eaten_nutrition"] or {}
            if meal["recipe"]:
                return meal["recipe"]
            return meal["target"] if meal["self_managed"] else {}

        contributi = [_macros(m) for m in entry["meals"]]
        entry["totals"] = {
            "calories": sum(c.get("calories", 0) for c in contributi),
            "protein_g": round(sum(c.get("protein_g", 0) for c in contributi), 1),
            "carbs_g": round(sum(c.get("carbs_g", 0) for c in contributi), 1),
            "fat_g": round(sum(c.get("fat_g", 0) for c in contributi), 1),
            # Il target è quello pieno della giornata, come nella home (`lib/today.js`):
            # la dieta non cambia perché una cena è andata diversamente. Prima il pasto
            # saltato usciva da tutte e due le cifre, e una pizza al posto della cena
            # dava «1100 / 1100», come se la giornata fosse andata a puntino.
            "target_calories": sum(m["target"]["calories"] for m in entry["meals"]),
        }

    # "Da riempire" conta solo le caselle che l'AI deve generare: includere quelle
    # gestite dall'utente farebbe sembrare il piano perennemente incompleto. Stesso
    # motivo per i giorni saltati: sono passati, non c'è più niente da riempirci.
    da_vivere = [(d, m, s) for d, m, s in rows if not d.is_skipped and not m.is_skipped]
    generabili = [(d, m, s) for d, m, s in da_vivere if s.auto_generate]
    total_slots = len(generabili)
    filled = sum(1 for _, meal, _ in generabili if meal.recipe_id)
    self_managed = len(da_vivere) - total_slots

    return {
        "id": week.id,
        "week_start_date": week.week_start_date.isoformat(),
        "status": week.status,
        "is_current": week.week_start_date == current_week_start(),
        # Serve solo a dire dove ci si trova sfogliando: passata, corrente o futura si
        # modificano tutte allo stesso modo.
        "is_past": week.week_start_date < current_week_start(),
        # La UI ci si aggancia per rimettere il loader quando si torna sulla pagina
        # a generazione avviata.
        "is_generating": is_generating(week),
        # E qui trova com'è finita, se è finita male: la risposta alla POST che
        # l'avrebbe detto è quasi sempre già stata buttata via da un proxy.
        "generation_error": generation_error(week),
        "generation_outcome": generation_outcome(week),
        "frequencies": frequency_report(db, week) if week.id else [],
        "meals_total": total_slots,
        "meals_filled": filled,
        "meals_self_managed": self_managed,
        "days_skipped": sum(1 for d in days.values() if d["is_skipped"]),
        "days": [days[k] for k in sorted(days)],
    }
