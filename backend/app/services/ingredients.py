"""Anagrafica ingredienti: normalizzazione dei nomi e creazione al volo.

L'AI genera nomi liberi ("Zucchine", "zucchine medie", "ZUCCHINE"). Se finissero in
tabella così come sono, la lista della spesa avrebbe tre righe di zucchine e la
dispensa non ne coprirebbe nessuna. Qui si normalizza e si riusa sempre la stessa riga.
"""

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Ingredient
from ..utils.pricing import catalog_entry, guess_category
from ..utils.seasonality import season_months_for

# Qualificatori che l'AI attacca ai nomi e che non cambiano l'ingrediente da comprare.
_NOISE = re.compile(
    r"\b(fresc[ao]|fresch[ei]|secc[ao]|secch[ei]|maturo|matura|medi[ao]|medie|grande|"
    r"grandi|piccol[oaie]|bio|biologic[ao]|tritat[ao]|a\s+cubetti|a\s+dadini|a\s+fette|"
    r"a\s+rondelle|in\s+scaglie|q\.?b\.?)\b",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Minuscolo, senza qualificatori e senza spazi doppi."""
    n = _NOISE.sub(" ", (name or "").strip().lower())
    n = re.sub(r"[\s,;]+", " ", n).strip(" -,")
    return n[:120]


def get_or_create_ingredient(db: Session, name: str) -> Ingredient:
    """Restituisce la riga di anagrafica per un nome, creandola se serve.

    Categoria, prezzo e stagionalità vengono dal catalogo quando l'ingrediente è
    noto; altrimenti la categoria si indovina dalle parole chiave (serve a
    raggruppare la lista della spesa per reparto) e il prezzo resta NULL — meglio
    "costo non stimabile" che un numero inventato.
    """
    clean = normalize_name(name)
    if not clean:
        raise ValueError("Nome ingrediente vuoto")

    existing = db.query(Ingredient).filter(Ingredient.name == clean).first()
    if existing:
        return existing

    entry = catalog_entry(clean)
    if entry:
        category, price, price_unit = entry
    else:
        category, price, price_unit = guess_category(clean), None, None

    ingredient = Ingredient(
        name=clean,
        category=category,
        season_months=season_months_for(clean),
        avg_price_per_unit=price,
        price_unit=price_unit,
    )
    db.add(ingredient)
    try:
        db.flush()
    except IntegrityError:
        # Race con un'altra richiesta che ha creato lo stesso ingrediente: il vincolo
        # UNIQUE sul nome è l'arbitro, noi ci riprendiamo la riga sua.
        db.rollback()
        return db.query(Ingredient).filter(Ingredient.name == clean).one()
    return ingredient
