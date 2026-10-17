"""Le risorse di un utente, cercate passando sempre dal suo `user_id`.

Il filtro stava in due copie identiche di `_get_meal` e `_get_week`, private dei router
del piano e della chat: il prossimo router l'avrebbe riscritto — o dimenticato, che è
un bug di sicurezza (i piani di un altro account). Qui una volta sola; la guardia su
tutte le rotte è `tests/test_isolamento_rotte.py`.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import DayPlan, PlannedMeal, WeekPlan


def own_week(db: Session, user_id: int, week_id: int) -> WeekPlan:
    week = (
        db.query(WeekPlan)
        .filter(WeekPlan.id == week_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not week:
        raise HTTPException(404, "Settimana non trovata")
    return week


def own_meal(db: Session, user_id: int, meal_id: int) -> tuple[PlannedMeal, DayPlan, WeekPlan]:
    """Il pasto, se la catena pasto → giorno → settimana è dell'utente; se no 404."""
    row = (
        db.query(PlannedMeal, DayPlan, WeekPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(PlannedMeal.id == meal_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Pasto non trovato")
    return row
