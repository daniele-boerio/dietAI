"""Lista della spesa: lettura, spunte, completamento ed esportazione."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import Ingredient, ShoppingList, ShoppingListItem, WeekPlan
from ..schemas import BoughtQuantityRequest, CheckItemRequest
from ..services.planner import refresh_week_statuses
from ..utils.units import price_for
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


def _own_item(db: Session, user_id: int, item_id: int) -> tuple[ShoppingListItem, ShoppingList, WeekPlan]:
    """Un articolo con la sua lista e la sua settimana.

    Il join fino a WeekPlan non è per comodità, è il controllo di proprietà: senza,
    l'id di un articolo basterebbe a modificare la lista di un altro utente.
    """
    row = (
        db.query(ShoppingListItem, ShoppingList, WeekPlan)
        .join(ShoppingList, ShoppingList.id == ShoppingListItem.shopping_list_id)
        .join(WeekPlan, WeekPlan.id == ShoppingList.week_plan_id)
        .filter(ShoppingListItem.id == item_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Articolo non trovato")
    return row


@router.put("/items/{item_id}/check")
def check_item(
    item_id: int,
    body: CheckItemRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Spunta un articolo."""
    row, _lst, _week = _own_item(db, user_id, item_id)

    row.is_checked = body.is_checked
    # Togliere la spunta vuol dire "non l'ho preso": anche la quantità che avevo
    # segnato non vale più.
    if not body.is_checked:
        row.bought_quantity = None
    db.commit()
    return {"id": row.id, "is_checked": row.is_checked}


@router.put("/items/{item_id}/quantity")
def set_bought_quantity(
    item_id: int,
    body: BoughtQuantityRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Quanto se n'è preso davvero, nell'unità della riga.

    Le confezioni non si tagliano a misura: per 140 g di tacchino si porta a casa il
    pacco da 400. Segnarlo qui, mentre si è davanti allo scaffale, evita di dover
    correggere la dispensa a casa — ed è la dispensa a decidere cosa comprerà la
    lista successiva. `null` rimette il valore della lista: ho preso quanto serviva.

    Segnare una quantità significa averlo preso, quindi la riga si spunta da sé.
    """
    row, lst, week = _own_item(db, user_id, item_id)
    if lst.is_completed:
        raise HTTPException(409, "Questa spesa è già stata completata.")

    row.bought_quantity = body.quantity
    if body.quantity is not None:
        row.is_checked = True

    # Il prezzo della riga segue quello che si porta a casa, e con esso il totale.
    ingredient = db.get(Ingredient, row.ingredient_id)
    row.estimated_price = price_for(
        row.bought_quantity or row.total_quantity,
        row.unit,
        ingredient.avg_price_per_unit,
        ingredient.price_unit,
    )
    db.flush()
    totale = sum(
        i.estimated_price or 0
        for i in db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id)
    )
    lst.estimated_cost = round(totale, 2) if totale else None
    db.commit()

    return serialize_shopping_list(db, week, lst)


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
