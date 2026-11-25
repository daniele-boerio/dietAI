"""SpassoSpesa: la lista della spesa condivisa di casa parla con DietAI da server a server.

Non c'è una sessione: SpassoSpesa si presenta col token condiviso (`SPASSOSPESA_TOKEN`)
e dice per conto di chi con la mail. È lì che sta il filtro per utente: ogni rotta
risale all'account da quella mail e tocca solo i suoi dati. Senza token configurato le
rotte rispondono 404, come se non esistessero.

- `GET /account` — c'è un account attivo con questa mail? SpassoSpesa chiede della
  dispensa solo a chi sta su tutte e due le app.
- `GET /lista` — la lista della spesa di quell'utente (la stessa di `/api/shopping/current`),
  per scegliere cosa portare nella lista di casa.
- `POST /dispensa` — la spesa fatta: quello che si riconosce va in dispensa
  (`store_in_pantry`, come «Ho fatto la spesa»), il resto torna indietro come scartato.
"""

import re
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import Ingredient, ShoppingListItem, User
from ..services.ingredients import load_rules, normalize_name
from ..services.planner import refresh_week_statuses
from ..services.shopping import rebuild_shopping_list, serialize_shopping_list, store_in_pantry
from ..utils.units import normalize_unit, to_base

router = APIRouter(prefix="/api/integrazioni/spassospesa", tags=["SpassoSpesa"])


def _servizio(authorization: str | None = Header(default=None)) -> None:
    token = config.SPASSOSPESA_TOKEN
    if not token:
        raise HTTPException(404, "Not Found")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(given.encode(), token.encode()):
        raise HTTPException(401, "Token non valido")


def _utente(db: Session, email: str) -> User | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    return (
        db.query(User)
        .filter(User.email.ilike(email), User.is_active.is_(True))
        .first()
    )


@router.get("/account", dependencies=[Depends(_servizio)])
def account(email: str, db: Session = Depends(get_db)):
    return {"exists": _utente(db, email) is not None}


@router.get("/lista", dependencies=[Depends(_servizio)])
def lista(email: str, db: Session = Depends(get_db)):
    user = _utente(db, email)
    if user is None:
        raise HTTPException(404, "Nessun account con questa mail")
    refresh_week_statuses(db, user.id)
    lst = rebuild_shopping_list(db, user.id)
    db.commit()
    data = serialize_shopping_list(db, user.id, lst)
    items = [
        {
            "ingredient_id": item["ingredient_id"],
            "name": item["name"][:1].upper() + item["name"][1:],
            "category": item["category"],
            "quantity": item["quantity"],
            "unit": item["unit"],
            "label": item["label"],
        }
        for cat in data["categories"]
        for item in cat["items"]
        if not item["is_checked"]
    ]
    return {"items": items, "covers_from": data["covers_from"], "covers_to": data["covers_to"]}


class Comprato(BaseModel):
    ingredient_id: int | None = None
    name: str = Field(default="", max_length=120)
    quantity: float | None = Field(default=None, gt=0, lt=100000)
    unit: str | None = Field(default=None, max_length=20)
    label: str | None = Field(default=None, max_length=40)  # "2 kg", "3" scritto a mano


class SpesaFatta(BaseModel):
    email: str
    items: list[Comprato] = Field(default_factory=list, max_length=300)


_QUANTITA = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Zàù.]*)\s*$")


def _da_etichetta(label: str | None) -> tuple[float, str] | None:
    """"2 kg" → (2000, "g"), "3" → (3, "unità"). Quello che non si capisce: None."""
    m = _QUANTITA.match(label or "")
    if not m:
        return None
    qty = float(m.group(1).replace(",", "."))
    unit = normalize_unit(m.group(2).rstrip(".") or "unità")
    qty, unit = to_base(qty, unit)
    return (qty, unit) if unit in ("g", "ml", "unità") and qty > 0 else None


@router.post("/dispensa", dependencies=[Depends(_servizio)])
def dispensa(body: SpesaFatta, db: Session = Depends(get_db)):
    user = _utente(db, body.email)
    if user is None:
        raise HTTPException(404, "Nessun account con questa mail")

    rules = load_rules(db)
    # Quanto ne chiedeva la lista: è la misura per chi in SpassoSpesa non l'ha scritta.
    # Chi non ha ancora un piano (né una dieta) non ha una lista: si va avanti senza.
    serve: dict[int, tuple[float, str]] = {}
    try:
        refresh_week_statuses(db, user.id)
        lst = rebuild_shopping_list(db, user.id)
        serve = {
            row.ingredient_id: (row.total_quantity, row.unit)
            for row in db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == lst.id)
        }
    except HTTPException:
        db.rollback()

    rows: list[tuple[int, float, str]] = []
    stored: list[str] = []
    skipped: list[str] = []
    for item in body.items:
        ingredient = db.get(Ingredient, item.ingredient_id) if item.ingredient_id else None
        if ingredient is None and item.name.strip():
            nome = normalize_name(item.name, rules)
            ingredient = db.query(Ingredient).filter(Ingredient.name == nome).first() if nome else None
        if ingredient is None:
            skipped.append(item.name or "?")
            continue
        misura = None
        if item.quantity and item.unit:
            misura = to_base(item.quantity, normalize_unit(item.unit))
        misura = misura or _da_etichetta(item.label) or serve.get(ingredient.id)
        if not misura:
            skipped.append(item.name or ingredient.name)
            continue
        rows.append((ingredient.id, misura[0], misura[1]))
        stored.append(ingredient.name)

    if rows:
        store_in_pantry(db, user.id, rows)
        db.commit()
        if serve:
            rebuild_shopping_list(db, user.id)
            db.commit()
    return {"stored": stored, "skipped": skipped}
