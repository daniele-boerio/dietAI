"""Tracking nutrizionale: pianificato vs prescritto.

Confronta i macro delle ricette assegnate con i target della dieta, giorno per
giorno e pasto per pasto. Non è un diario alimentare: misura quanto il piano
generato aderisce alla dieta, più l'aderenza dichiarata dall'utente (`is_followed`).
"""

from sqlalchemy.orm import Session

from ..models import MealSlot, Recipe, WeekPlan
from .planner import DAY_NAMES, week_meals

# Sotto il 10% di scarto il piano è "in linea"; oltre il 20% è fuori bersaglio.
# Sono le stesse soglie che i prompt danno all'AI, così UI e generazione concordano.
GREEN_THRESHOLD = 0.10
YELLOW_THRESHOLD = 0.20


def compliance_color(planned: float, target: float) -> str:
    if not target:
        return "grey"
    delta = abs(planned - target) / target
    if delta <= GREEN_THRESHOLD:
        return "green"
    if delta <= YELLOW_THRESHOLD:
        return "yellow"
    return "red"


def _macros(recipe: Recipe | None) -> dict:
    if not recipe:
        return {"calories": 0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    return {
        "calories": recipe.calories,
        "protein_g": recipe.protein_g,
        "carbs_g": recipe.carbs_g,
        "fat_g": recipe.fat_g,
    }


def weekly_tracking(db: Session, week: WeekPlan) -> dict:
    rows = week_meals(db, week)
    days: dict[int, dict] = {}
    followed_days = 0

    for day, meal, slot in rows:
        recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
        self_managed = not slot.auto_generate

        if recipe:
            planned = _macros(recipe)
        elif self_managed:
            # L'utente ha detto di avere già il suo pasto con quei macro: darlo per
            # centrato è la lettura giusta. Contarlo zero mostrerebbe un buco di 400
            # kcal al giorno e farebbe crollare l'aderenza per un pasto che invece
            # rispetta la dieta alla lettera.
            planned = {
                "calories": slot.target_calories,
                "protein_g": slot.target_protein_g,
                "carbs_g": slot.target_carbs_g,
                "fat_g": slot.target_fat_g,
            }
        else:
            planned = _macros(None)

        entry = days.setdefault(
            day.day_of_week,
            {
                "date": day.date.isoformat(),
                "day_of_week": day.day_of_week,
                "day_name": DAY_NAMES[day.day_of_week],
                "meals": [],
                "totals": {
                    "planned_calories": 0,
                    "target_calories": 0,
                    "planned_protein_g": 0.0,
                    "planned_carbs_g": 0.0,
                    "planned_fat_g": 0.0,
                    "target_protein_g": 0.0,
                    "target_carbs_g": 0.0,
                    "target_fat_g": 0.0,
                },
            },
        )

        entry["meals"].append(
            {
                "meal_id": meal.id,
                "slot_name": slot.name,
                "recipe_title": recipe.title if recipe else None,
                "target": {
                    "calories": slot.target_calories,
                    "protein_g": slot.target_protein_g,
                    "carbs_g": slot.target_carbs_g,
                    "fat_g": slot.target_fat_g,
                },
                "planned": planned,
                "color": compliance_color(planned["calories"], slot.target_calories)
                if (recipe or self_managed)
                else "grey",
                "self_managed": self_managed,
                "is_followed": meal.is_followed,
                "deviation_notes": meal.deviation_notes,
            }
        )

        totals = entry["totals"]
        totals["planned_calories"] += planned["calories"]
        totals["planned_protein_g"] += planned["protein_g"]
        totals["planned_carbs_g"] += planned["carbs_g"]
        totals["planned_fat_g"] += planned["fat_g"]
        totals["target_calories"] += slot.target_calories
        totals["target_protein_g"] += slot.target_protein_g
        totals["target_carbs_g"] += slot.target_carbs_g
        totals["target_fat_g"] += slot.target_fat_g

    for entry in days.values():
        totals = entry["totals"]
        for key in ("planned_protein_g", "planned_carbs_g", "planned_fat_g",
                    "target_protein_g", "target_carbs_g", "target_fat_g"):
            totals[key] = round(totals[key], 1)
        totals["delta"] = totals["planned_calories"] - totals["target_calories"]
        totals["color"] = compliance_color(totals["planned_calories"], totals["target_calories"])

        tracked = [m["is_followed"] for m in entry["meals"] if m["is_followed"] is not None]
        # Un giorno conta come seguito se tutti i pasti tracciati lo sono: basta uno
        # "no" per dire che quel giorno il piano non è stato rispettato.
        entry["is_followed"] = bool(tracked) and all(tracked)
        if entry["is_followed"]:
            followed_days += 1

    ordered = [days[k] for k in sorted(days)]
    days_with_food = [d for d in ordered if d["totals"]["planned_calories"] > 0]
    n = len(days_with_food) or 1

    avg_planned = sum(d["totals"]["planned_calories"] for d in days_with_food) / n
    avg_target = sum(d["totals"]["target_calories"] for d in ordered) / (len(ordered) or 1)

    all_meals = [
        m for d in ordered for m in d["meals"] if m["recipe_title"] or m["self_managed"]
    ]
    in_range = sum(1 for m in all_meals if m["color"] == "green")

    return {
        "week_start_date": week.week_start_date.isoformat(),
        "status": week.status,
        "is_locked": week.is_locked,
        "days": ordered,
        "weekly_summary": {
            "avg_daily_calories_planned": round(avg_planned),
            "avg_daily_calories_target": round(avg_target),
            "compliance_pct": round(100 * in_range / len(all_meals), 1) if all_meals else 0.0,
            "meals_planned": len(all_meals),
            "meals_in_range": in_range,
            "days_followed": followed_days,
            "macro_averages": {
                "protein_g": round(
                    sum(d["totals"]["planned_protein_g"] for d in days_with_food) / n, 1
                ),
                "carbs_g": round(
                    sum(d["totals"]["planned_carbs_g"] for d in days_with_food) / n, 1
                ),
                "fat_g": round(sum(d["totals"]["planned_fat_g"] for d in days_with_food) / n, 1),
            },
            "macro_targets": {
                "protein_g": round(
                    sum(d["totals"]["target_protein_g"] for d in ordered) / (len(ordered) or 1), 1
                ),
                "carbs_g": round(
                    sum(d["totals"]["target_carbs_g"] for d in ordered) / (len(ordered) or 1), 1
                ),
                "fat_g": round(
                    sum(d["totals"]["target_fat_g"] for d in ordered) / (len(ordered) or 1), 1
                ),
            },
        },
    }


def diet_targets(db: Session, diet_plan_id: int) -> list[dict]:
    slots = (
        db.query(MealSlot)
        .filter(MealSlot.diet_plan_id == diet_plan_id)
        .order_by(MealSlot.order_index)
        .all()
    )
    return [
        {
            "id": s.id,
            "name": s.name,
            "order": s.order_index,
            "calories": s.target_calories,
            "protein_g": s.target_protein_g,
            "carbs_g": s.target_carbs_g,
            "fat_g": s.target_fat_g,
            "notes": s.notes,
        }
        for s in slots
    ]
