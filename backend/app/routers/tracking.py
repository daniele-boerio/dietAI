"""Tracking nutrizionale e riepilogo della dashboard."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import Recipe, ShoppingList, ShoppingListItem, WeekPlan
from ..services.planner import (
    DAY_NAMES,
    current_week_start,
    get_active_diet,
    get_or_create_week,
    monday_of,
    next_week_start,
    refresh_week_statuses,
    serialize_week,
    week_meals,
)
from ..services.shopping import get_or_create_list
from ..services.tracking import diet_targets, weekly_tracking

router = APIRouter(prefix="/api/tracking", tags=["Tracking"])


@router.get("/weekly")
def weekly(
    week_start_date: str | None = Query(None, description="AAAA-MM-GG, default: settimana corrente"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    refresh_week_statuses(db, user_id)

    if week_start_date:
        try:
            start = monday_of(date.fromisoformat(week_start_date))
        except ValueError:
            raise HTTPException(400, "Data non valida: usa il formato AAAA-MM-GG.")
    else:
        start = current_week_start()

    week = get_or_create_week(db, user_id, start)
    data = weekly_tracking(db, week)

    diet = get_active_diet(db, user_id)
    data["target"] = {
        "daily_calories": diet.total_daily_calories if diet else 0,
        "meals": diet_targets(db, diet.id) if diet else [],
    }
    return data


@router.get("/weeks")
def list_weeks(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Elenco delle settimane esistenti, per il selettore dello storico."""
    refresh_week_statuses(db, user_id)
    rows = (
        db.query(WeekPlan)
        .filter(WeekPlan.user_id == user_id)
        .order_by(WeekPlan.week_start_date.desc())
        .limit(52)
        .all()
    )
    return [
        {
            "id": w.id,
            "week_start_date": w.week_start_date.isoformat(),
            "status": w.status,
            "is_locked": w.is_locked,
            "is_current": w.week_start_date == current_week_start(),
        }
        for w in rows
    ]


@router.get("/dashboard")
def dashboard(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Riepilogo della home: cosa si mangia oggi, a che punto è il piano e la spesa."""
    refresh_week_statuses(db, user_id)

    diet = get_active_diet(db, user_id)
    if not diet:
        return {"has_diet": False}

    week = get_or_create_week(db, user_id, current_week_start())
    week_data = serialize_week(db, week)

    today = date.today()
    today_meals = []
    for day, meal, slot in week_meals(db, week):
        if day.date != today:
            continue
        recipe = db.get(Recipe, meal.recipe_id) if meal.recipe_id else None
        today_meals.append(
            {
                "meal_id": meal.id,
                "slot_name": slot.name,
                "slot_order": slot.order_index,
                "target_calories": slot.target_calories,
                "is_followed": meal.is_followed,
                # "Ho mangiato altro": la ricetta è scritta ma è stata rimandata. La
                # home la mostra spenta, non tra i piatti di oggi da preparare.
                "is_skipped": meal.is_skipped,
                "recipe": (
                    {
                        "id": recipe.id,
                        "title": recipe.title,
                        "calories": recipe.calories,
                        "protein_g": recipe.protein_g,
                        "carbs_g": recipe.carbs_g,
                        "fat_g": recipe.fat_g,
                        "prep_time_min": recipe.prep_time_min,
                        "cook_time_min": recipe.cook_time_min,
                    }
                    if recipe
                    else None
                ),
            }
        )

    lst = get_or_create_list(db, week)
    db.commit()
    items = (
        db.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )

    next_week = (
        db.query(WeekPlan)
        .filter(WeekPlan.user_id == user_id, WeekPlan.week_start_date == next_week_start())
        .first()
    )

    return {
        "has_diet": True,
        "today": {
            "date": today.isoformat(),
            "day_name": DAY_NAMES[today.weekday()],
            "meals": sorted(today_meals, key=lambda m: m["slot_order"]),
        },
        "week": {
            "id": week.id,
            "week_start_date": week.week_start_date.isoformat(),
            "status": week.status,
            "is_locked": week.is_locked,
            "lock_expires_at": week.lock_expires_at.isoformat() if week.lock_expires_at else None,
            "meals_total": week_data["meals_total"],
            "meals_filled": week_data["meals_filled"],
        },
        "shopping": {
            "is_completed": lst.is_completed,
            "estimated_cost": lst.estimated_cost,
            "total_items": len(items),
            "checked_items": sum(1 for i in items if i.is_checked),
        },
        "next_week": (
            {
                "id": next_week.id,
                "week_start_date": next_week.week_start_date.isoformat(),
                "status": next_week.status,
            }
            if next_week
            else None
        ),
        "diet": {
            "daily_calories": diet.total_daily_calories,
            "meals_count": len(diet_targets(db, diet.id)),
        },
        "recipes_count": db.query(Recipe).filter(Recipe.user_id == user_id).count(),
        "favorites_count": db.query(Recipe)
        .filter(Recipe.user_id == user_id, Recipe.is_favorite.is_(True))
        .count(),
    }
