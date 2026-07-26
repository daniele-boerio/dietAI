"""Lista della spesa: lettura, spunte, completamento ed esportazione."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import ShoppingList, ShoppingListItem, WeekPlan
from ..schemas import CheckItemRequest
from ..services.planner import refresh_week_statuses
from ..services.shopping import (
    active_shopping_week,
    complete_shopping,
    export_text,
    get_or_create_list,
    rebuild_shopping_list,
    serialize_shopping_list,
)

router = APIRouter(prefix="/api/shopping", tags=["Spesa"])


def _open_list(db: Session, user_id: int) -> tuple[WeekPlan, ShoppingList]:
    """La spesa aperta: una sola, sulla prima settimana che ha ancora qualcosa da comprare."""
    refresh_week_statuses(db, user_id)
    week = active_shopping_week(db, user_id)
    lst = rebuild_shopping_list(db, user_id, week)
    db.commit()
    return week, lst


@router.get("/current")
def get_current_list(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """La spesa da fare — "corrente" nel senso di aperta, non di questa settimana.

    Una lista comprende tutte le settimane generate e non ancora comprate, quindi ce
    n'è sempre e solo una: quando la spesa è fatta, la successiva parte da sé dalla
    prima settimana rimasta scoperta.
    """
    week, lst = _open_list(db, user_id)
    return serialize_shopping_list(db, week, lst)


@router.put("/items/{item_id}/check")
def check_item(
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


@router.post("/current/complete")
def complete(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """"Ho fatto la spesa": blocca le settimane comprate e aggiorna la dispensa."""
    refresh_week_statuses(db, user_id)
    week = active_shopping_week(db, user_id)
    lst = get_or_create_list(db, week)
    return complete_shopping(db, user_id, week, lst)


@router.get("/export", response_class=PlainTextResponse)
def export(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Lista in testo semplice, da copiare o condividere."""
    week, lst = _open_list(db, user_id)
    return export_text(db, week, lst)
