"""Lista della spesa: lettura, spunte, quantità e prezzi, completamento, esportazione."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import Ingredient, ShoppingList, ShoppingListItem, WeekPlan
from ..schemas import BoughtQuantityRequest, CheckItemRequest, PaidPriceRequest
from ..services.planner import refresh_week_statuses
from ..utils.pricing import catalog_entry
from ..utils.units import price_for, unit_price_from
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

    # Il costo della riga segue quello che si porta a casa, e con esso il totale.
    _refresh_prices(db, lst)
    db.commit()

    return serialize_shopping_list(db, week, lst)


def _refresh_prices(db: Session, lst: ShoppingList) -> None:
    """Ricalcola il costo di ogni riga e il totale della lista.

    Il prezzo di una riga dipende da due cose che cambiano mentre si fa la spesa: la
    quantità che si è presa e il prezzo che si è pagato. Rifarli tutti costa una query
    e toglie il dubbio su quale riga fosse rimasta indietro.
    """
    totale = 0.0
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )
    for item, ingredient in rows:
        item.estimated_price = price_for(
            item.bought_quantity or item.total_quantity,
            item.unit,
            ingredient.avg_price_per_unit,
            ingredient.price_unit,
        )
        totale += item.estimated_price or 0
    lst.estimated_cost = round(totale, 2) if totale else None


@router.put("/items/{item_id}/price")
def set_paid_price(
    item_id: int,
    body: PaidPriceRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Quanto è costato davvero, per la quantità presa.

    Il prezzo del catalogo è una media italiana e al negozio dove fa la spesa l'utente
    vale poco: è per questo che il totale stimato non dice quasi niente. Segnando la
    cifra dello scaffale — quella che si ha sotto gli occhi, non un prezzo al chilo da
    ricavare a mente — l'app impara il prezzo unitario e da lì in poi tutte le liste
    contano con quello.

    Si può fare anche a spesa fatta: lo scontrino si guarda a casa. `null` cancella il
    prezzo tuo e rimette quello del catalogo, se l'ingrediente ci sta dentro.
    """
    row, lst, week = _own_item(db, user_id, item_id)
    ingredient = db.get(Ingredient, row.ingredient_id)

    if body.paid is None:
        entry = catalog_entry(ingredient.name)
        ingredient.avg_price_per_unit = entry[1] if entry else None
        ingredient.price_unit = entry[2] if entry else None
        ingredient.price_by_user = False
        ingredient.last_paid_at = None
    else:
        learned = unit_price_from(
            body.paid, row.bought_quantity or row.total_quantity, row.unit
        )
        if not learned:
            raise HTTPException(400, "Non riesco a ricavare un prezzo da questa quantità.")
        ingredient.avg_price_per_unit, ingredient.price_unit = learned
        ingredient.price_by_user = True
        ingredient.last_paid_at = datetime.now(timezone.utc)

    _refresh_prices(db, lst)
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
