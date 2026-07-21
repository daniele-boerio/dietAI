"""Lista della spesa: lettura, spunte, completamento ed esportazione."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import ShoppingList, ShoppingListItem, WeekPlan
from ..schemas import CheckItemRequest
from ..services.planner import (
    current_week_start,
    get_or_create_week,
    next_week_start,
    refresh_week_statuses,
)
from ..services.shopping import (
    complete_shopping,
    export_text,
    get_or_create_list,
    rebuild_shopping_list,
    serialize_shopping_list,
)

router = APIRouter(prefix="/api/shopping", tags=["Spesa"])


def _week_and_list(db: Session, user_id: int, which: str) -> tuple[WeekPlan, ShoppingList]:
    refresh_week_statuses(db, user_id)
    start = current_week_start() if which == "current" else next_week_start()
    week = get_or_create_week(db, user_id, start)
    lst = rebuild_shopping_list(db, user_id, week)
    db.commit()
    return week, lst


@router.get("/current")
async def get_current_list(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    week, lst = _week_and_list(db, user_id, "current")
    return serialize_shopping_list(db, week, lst)


@router.get("/next")
async def get_next_list(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Anteprima della spesa della settimana prossima, sempre modificabile."""
    week, lst = _week_and_list(db, user_id, "next")
    return serialize_shopping_list(db, week, lst)


@router.put("/items/{item_id}/check")
async def check_item(
    item_id: int,
    body: CheckItemRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Spunta un articolo. Il join fino a WeekPlan serve a verificare la proprietà:
    senza, l'id di un item basterebbe a modificare la lista di un altro utente."""
    row = (
        db.query(ShoppingListItem)
        .join(ShoppingList, ShoppingList.id == ShoppingListItem.shopping_list_id)
        .join(WeekPlan, WeekPlan.id == ShoppingList.week_plan_id)
        .filter(ShoppingListItem.id == item_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Articolo non trovato")

    row.is_checked = body.is_checked
    db.commit()
    return {"id": row.id, "is_checked": row.is_checked}


@router.post("/{which}/complete")
async def complete(
    which: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """"Ho fatto la spesa": blocca il piano per 7 giorni e aggiorna la dispensa."""
    if which not in ("current", "next"):
        raise HTTPException(404, "Lista non trovata")

    refresh_week_statuses(db, user_id)
    start = current_week_start() if which == "current" else next_week_start()
    week = get_or_create_week(db, user_id, start)
    lst = get_or_create_list(db, week)
    return complete_shopping(db, user_id, week, lst)


@router.get("/export", response_class=PlainTextResponse)
async def export(
    which: str = Query("current", pattern="^(current|next)$"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Lista in testo semplice, da copiare o condividere."""
    week, lst = _week_and_list(db, user_id, which)
    return export_text(db, week, lst)
