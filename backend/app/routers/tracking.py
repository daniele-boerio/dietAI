"""Tracking nutrizionale e riepilogo della dashboard."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import WeekPlan, WeightEntry
from ..schemas import WeightEntryIn
from ..services import planner, tracking, weight
from ..services.planner import (
    current_week_start,
    get_active_diet,
    get_or_create_week,
    monday_of,
    refresh_week_statuses,
)
from ..services.tracking import (
    diet_targets,
    weekly_tracking,
    year_adherence,
)

router = APIRouter(prefix="/api/tracking", tags=["Tracking"])


@router.get("/weight")
def get_weight(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Le pesate e, se la dieta viene dal questionario, se è ora di ricalcolarla."""
    return weight.history(db, user_id)


@router.put("/weight")
def put_weight(
    body: WeightEntryIn,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Segna il peso di un giorno (oggi, se non si dice quale). Ripesarsi corregge."""
    # `planner.today()` e non `date.today()`: è la data che i test possono fissare.
    giorno = body.day or planner.today()
    if giorno > planner.today():
        raise HTTPException(400, "Il peso di un giorno che non è ancora arrivato non si segna.")
    weight.upsert(db, user_id, giorno, body.weight_kg)
    db.commit()
    return weight.history(db, user_id)


@router.delete("/weight/{day}")
def delete_weight(
    day: date,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    db.query(WeightEntry).filter_by(user_id=user_id, day=day).delete()
    db.commit()
    return weight.history(db, user_id)


@router.get("/weekly")
def weekly(
    week_start_date: str | None = Query(None, description="AAAA-MM-GG, default: settimana corrente"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    refresh_week_statuses(db, user_id)

    if week_start_date:
        try:
            giorno = date.fromisoformat(week_start_date)
            if not 2000 <= giorno.year <= 2100:
                raise ValueError
            start = monday_of(giorno)
        except ValueError:
            raise HTTPException(400, "Data non valida: usa il formato AAAA-MM-GG.")
    else:
        start = current_week_start()

    if start < current_week_start():
        # Come in Pianificazione: il passato non si inventa. Creare qui una settimana
        # mai vissuta la riempiva di caselle e di pasti fissi ricopiati in giorni
        # già passati, a ogni data chiesta.
        week = (
            db.query(WeekPlan)
            .filter(WeekPlan.user_id == user_id, WeekPlan.week_start_date == start)
            .first()
        )
        if week is None:
            raise HTTPException(404, "In quella settimana non c'era nessun piano.")
    else:
        week = get_or_create_week(db, user_id, start)
    data = weekly_tracking(db, week)

    diet = get_active_diet(db, user_id)
    data["target"] = {
        "daily_calories": diet.total_daily_calories if diet else 0,
        "meals": diet_targets(db, diet.id) if diet else [],
    }
    return data


@router.get("/year")
def year(
    year: int | None = Query(
        None, ge=2000, le=2100, description="Anno solare, default: quello corrente"
    ),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Aderenza giorno per giorno nell'anno, per il calendario a colpo d'occhio."""
    refresh_week_statuses(db, user_id)
    return year_adherence(db, user_id, year or planner.today().year)


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
            "is_current": w.week_start_date == current_week_start(),
        }
        for w in rows
    ]


@router.get("/dashboard")
def dashboard(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Riepilogo della home: cosa si mangia oggi, a che punto è il piano e la spesa."""
    return tracking.dashboard(db, user_id)
