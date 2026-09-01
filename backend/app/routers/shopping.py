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
    complete_shopping,
    current_list,
    export_text,
    rebuild_shopping_list,
    serialize_shopping_list,
)

router = APIRouter(prefix="/api/shopping", tags=["Spesa"])


def _open_list(db: Session, user_id: int) -> ShoppingList:
    """La lista, ricalcolata: quello che il piano chiede da oggi e la dispensa non copre."""
    refresh_week_statuses(db, user_id)
    lst = rebuild_shopping_list(db, user_id)
    db.commit()
    return lst


@router.get("/current")
def get_current_list(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """La spesa da fare: quello che le ricette da oggi in avanti chiedono e in casa non c'è.

    Non ci sono liste "di questa settimana" o "della prossima": ce n'è una sola, che
    comprende tutto il piano generato da oggi in poi. A spesa fatta si accorcia da sé,
    perché quello che hai comprato è passato in dispensa.
    """
    return serialize_shopping_list(db, user_id, _open_list(db, user_id))


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
    row, lst, _week = _own_item(db, user_id, item_id)

    row.is_checked = body.is_checked
    # Togliere la spunta vuol dire "non l'ho preso": la quantità che avevo segnato non
    # vale più, e nemmeno la cifra che avevo scritto di averci speso. Il prezzo al
    # chilo imparato resta sull'ingrediente: quello lo si è visto davvero.
    if not body.is_checked:
        row.bought_quantity = None
        row.paid_price = None
        _refresh_prices(db, lst)
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
    row, lst, _week = _own_item(db, user_id, item_id)
    row.bought_quantity = body.quantity
    if body.quantity is not None:
        row.is_checked = True

    # La cifra pagata resta quella: è uno scontrino, non una stima. Al chilo però vuol
    # dire un'altra cosa — se il pacco era da 400 g e non da 140, l'app deve impararlo
    # giusto — quindi il prezzo unitario si rifà sulla quantità nuova.
    if row.paid_price is not None:
        _impara_prezzo_unitario(db, row)

    # Il costo delle righe *senza* un prezzo scritto segue quello che si porta a casa.
    _refresh_prices(db, lst)
    db.commit()

    return serialize_shopping_list(db, user_id, lst)


def _impara_prezzo_unitario(db: Session, row: ShoppingListItem) -> bool:
    """Dal prezzo scritto sulla riga ricava il prezzo al chilo dell'ingrediente.

    È l'unica cosa che la cifra pagata insegna al resto dell'app: da lì in poi tutte
    le liste stimano con quella invece che con la media nazionale del catalogo.
    Restituisce False quando dalla quantità non si ricava niente (un'unità che non si
    converte): chi scrive il prezzo lo dice all'utente, chi corregge la quantità si
    tiene il prezzo di prima — meglio uno vecchio che uno inventato.
    """
    ingredient = db.get(Ingredient, row.ingredient_id)
    learned = unit_price_from(
        row.paid_price, row.bought_quantity or row.total_quantity, row.unit
    )
    if not learned:
        return False
    ingredient.avg_price_per_unit, ingredient.price_unit = learned
    ingredient.price_by_user = True
    ingredient.last_paid_at = datetime.now(timezone.utc)
    return True


def _refresh_prices(db: Session, lst: ShoppingList) -> None:
    """Ricalcola il costo delle righe che un prezzo scritto non ce l'hanno, e il totale.

    Quello che l'utente ha battuto sulla riga non si tocca mai: è la cifra che ha sotto
    gli occhi, e ricalcolarla dal prezzo al chilo per la quantità del momento voleva
    dire riscrivergliela addosso ogni volta che la quantità cambiava — correggendo il
    pacco preso, o semplicemente rigenerando una ricetta che di quell'ingrediente ne
    chiede di più. Al supermercato sembrava che l'app cambiasse i prezzi da sé.
    """
    totale = 0.0
    rows = (
        db.query(ShoppingListItem, Ingredient)
        .join(Ingredient, Ingredient.id == ShoppingListItem.ingredient_id)
        .filter(ShoppingListItem.shopping_list_id == lst.id)
        .all()
    )
    for item, ingredient in rows:
        item.estimated_price = (
            item.paid_price
            if item.paid_price is not None
            else price_for(
                item.bought_quantity or item.total_quantity,
                item.unit,
                ingredient.avg_price_per_unit,
                ingredient.price_unit,
            )
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
    row, lst, _week = _own_item(db, user_id, item_id)
    ingredient = db.get(Ingredient, row.ingredient_id)

    if body.paid is None:
        row.paid_price = None
        entry = catalog_entry(ingredient.name)
        ingredient.avg_price_per_unit = entry[1] if entry else None
        ingredient.price_unit = entry[2] if entry else None
        ingredient.price_by_user = False
        ingredient.last_paid_at = None
    else:
        # La cifra si salva sulla riga così com'è, e resta quella: il prezzo al chilo
        # che se ne ricava serve a stimare le altre liste, non a riscrivere questa.
        row.paid_price = body.paid
        if not _impara_prezzo_unitario(db, row):
            raise HTTPException(400, "Non riesco a ricavare un prezzo da questa quantità.")

    _refresh_prices(db, lst)
    db.commit()
    return serialize_shopping_list(db, user_id, lst)


@router.post("/current/complete")
def complete(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """"Ho fatto la spesa": gli articoli spuntati passano in dispensa e la lista si svuota.

    Non si blocca niente e non si chiude niente: la lista è quello che il piano chiede
    e la dispensa non copre, quindi appena la roba è in dispensa la lista si accorcia
    da sé. Quello che non hai spuntato resta, perché non l'hai comprato.
    """
    refresh_week_statuses(db, user_id)
    _, lst = current_list(db, user_id)
    return complete_shopping(db, user_id, lst)


@router.delete("/current/items")
def clear_shopping_list(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Cancella tutti gli articoli dalla lista della spesa corrente.
    
    La lista si ripopolerà automaticamente con gli ingredienti delle ricette
    da generare, escludendo ciò che è già in dispensa.
    """
    _, lst = current_list(db, user_id)
    db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id).delete()
    lst.estimated_cost = None
    db.commit()
    return serialize_shopping_list(db, user_id, lst)


@router.get("/export", response_class=PlainTextResponse)
def export(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Lista in testo semplice, da copiare o condividere."""
    return export_text(db, user_id, _open_list(db, user_id))
