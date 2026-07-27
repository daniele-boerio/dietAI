"""Anagrafica ingredienti: normalizzazione dei nomi e creazione al volo.

L'AI genera nomi liberi ("Zucchine", "zucchine medie", "ZUCCHINE"). Se finissero in
tabella così come sono, la lista della spesa avrebbe tre righe di zucchine e la
dispensa non ne coprirebbe nessuna. Qui si normalizza e si riusa sempre la stessa riga.
"""

import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    BaseIngredient,
    ExcludedIngredient,
    Ingredient,
    PantryItem,
    PlannedMeal,
    RecipeIngredient,
    ShoppingListItem,
)
from ..utils.pricing import catalog_entry, guess_category
from ..utils.seasonality import season_months_for
from ..utils.units import to_base

# Qualificatori che si tolgono dal nome. La linea di taglio: via tutto ciò che dice
# **com'è messo** l'alimento — conservazione, taglio, calibro — e resta tutto ciò che
# dice **cos'è**. "Pesce spada surgelato" e "pesce spada fresco" sono lo stesso pesce
# comprato in due banchi diversi, e chi fa la spesa lo sa già; "mandorle a lamelle"
# sono mandorle.
#
# Restano fuori di proposito le parole che cambiano i numeri della dieta — integrale,
# magro, light, intero, al naturale, sott'olio, senza zuccheri — perché lì cambia
# l'alimento, non la sua confezione: uno yogurt magro e uno intero non sono la stessa
# riga della spesa nemmeno volendo. Fuori anche "pelati", che in italiano non è lo
# stato dei pomodori ma una conserva.
_NOISE = re.compile(
    r"\b("
    # marchi commerciali
    r"hero|barilla|de\s+cecco|rustichella|garofalo|buitoni|mutti|sa|valfrutta|unifruit|"
    # conservazione e stato
    r"fresc[ao]|fresch[ei]|secc[ao]|secch[ei]|surgelat[oaie]|congelat[oaie]|"
    r"sgusciat[oaie]|sbucciat[oaie]|maturo|matura|"
    # calibro e qualità
    r"medi[ao]|medie|grande|grandi|piccol[oaie]|bio|biologic[ao]|"
    # taglio e formato
    r"tritat[oaie]|macinat[oaie]|grattugiat[oaie]|affettat[oaie]|"
    r"a\s+cubetti|a\s+dadini|a\s+fette|a\s+fettine|a\s+rondelle|a\s+lamelle|"
    r"a\s+listarelle|a\s+striscioline|a\s+julienne|a\s+spicchi|a\s+pezzi|a\s+pezzetti|"
    r"in\s+scaglie|in\s+filetti|"
    # formato: "pasta corta" è pasta, come "pasta di semola di grano duro" — dicono
    # che taglio è, non che alimento è, e al supermercato si compra un pacco solo.
    # Restano fuori i formati con un'identità propria ("pasta all'uovo", "pasta
    # sfoglia") e "integrale", che sta più su fra le parole che cambiano i macro.
    r"cort[aeio]|lung[ao]|lungh[ei]|formato|"
    r"di\s+semola(\s+di\s+grano\s+duro)?|"
    r"q\.?b\.?"
    r")\b",
    re.IGNORECASE,
)

# Tipi di pasta da normalizzare a "pasta": spaghetti, penne, fusilli, ecc.
# Restano fuori i formati con un'identità propria ("pasta all'uovo", "pasta sfoglia").
_PASTA_TYPES = re.compile(
    r"\b(spaghetti|penne|fusilli|farfalle|rigatoni|sedani|bucatini|linguine|fettuccine|tagliatelle|"
    r"gnocchi|ravioli|tortellini|cappelletti|agnolotti|tortelli|bavette|trenette|vermicelli|"
    r"pennette|mezzemaniche|tortiglioni|cannelloni|lasagna|taglioni|pappardelle|maltagliati|"
    r"casarecce|orecchiette|rotelle|conchiglie|tubetti|ditalini|riso|orzo|farro|cous\s+cous)\b",
    re.IGNORECASE,
)

# Tipi di pesce magro da normalizzare a "filetto di pesce magro"
_PESCE_MAGRO = re.compile(
    r"\b(filetti?|filett[io])\s+di\s+(branzino|orata|sogliola|merluzzo|platessa)\b|\b(branzino|orata|sogliola|merluzzo|platessa)\b",
    re.IGNORECASE,
)

# Gamberi: togliere qualificatori geografici e conservare solo "gamberi"
_GAMBERI = re.compile(
    r"\bgamberi\s+(indopacifici?|rossi?|bianchi?|di\s+\w+)\b",
    re.IGNORECASE,
)

# Quello che sta fra parentesi è sempre una glossa, mai l'alimento: "pasta corta
# (penne)", "legumi (ceci o fagioli)". Si toglie prima dei qualificatori, o resterebbe
# attaccato al nome e farebbe una riga a sé nella lista della spesa.
_PARENTESI = re.compile(r"\([^)]*\)")

# Preposizioni rimaste appese dopo aver tolto un qualificatore ("mandorle a" → "mandorle").
_DANGLING = re.compile(r"\s+(a|di|in|al|alla|con|da)\s*$", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """Minuscolo, senza glosse fra parentesi, senza qualificatori e senza spazi doppi.
    
    I tipi di pasta (spaghetti, penne, ecc.) vengono normalizzati a "pasta".
    I filetti di pesce magro (branzino, orata, sogliola, merluzzo) diventano "filetto di pesce magro".
    I gamberi con qualificatori geografici (indopacifici, rossi, bianchi) diventano "gamberi".
    """
    n = _PARENTESI.sub(" ", (name or "").strip().lower())
    # Normalizza i tipi di pasta a "pasta"
    n = _PASTA_TYPES.sub("pasta", n)
    # Normalizza i filetti di pesce magro a "filetto di pesce magro"
    n = _PESCE_MAGRO.sub("filetto di pesce magro", n)
    # Normalizza gamberi con qualificatori a "gamberi"
    n = _GAMBERI.sub("gamberi", n)
    n = _NOISE.sub(" ", n)
    n = re.sub(r"[\s,;]+", " ", n).strip(" -,.")
    n = _DANGLING.sub("", n).strip(" -,.")
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


# ── Riallineamento dell'anagrafica ─────────────────────────────────────────────


def _merge_rows(db: Session, canonical: Ingredient, doppione: Ingredient) -> None:
    """Sposta sulla riga buona tutto ciò che puntava al doppione, poi lo cancella."""
    # Le ricette non hanno vincoli di unicità: si ripuntano e basta.
    db.query(RecipeIngredient).filter(
        RecipeIngredient.ingredient_id == doppione.id
    ).update({RecipeIngredient.ingredient_id: canonical.id}, synchronize_session=False)

    # La dispensa ne ha una riga per utente: dove ci sono entrambe si sommano, ma solo
    # se le unità si parlano — sommare grammi e unità darebbe un numero inventato.
    for item in (
        db.query(PantryItem).filter(PantryItem.ingredient_id == doppione.id).all()
    ):
        gemella = (
            db.query(PantryItem)
            .filter(
                PantryItem.user_id == item.user_id,
                PantryItem.ingredient_id == canonical.id,
            )
            .first()
        )
        if not gemella:
            item.ingredient_id = canonical.id
            continue
        if item.quantity_available and gemella.quantity_available:
            somma, unit = to_base(item.quantity_available, item.unit or "unità")
            base, unit_gemella = to_base(
                gemella.quantity_available, gemella.unit or "unità"
            )
            if unit == unit_gemella:
                gemella.quantity_available = round(base + somma, 2)
                gemella.unit = unit
        elif item.quantity_available:
            gemella.quantity_available = item.quantity_available
            gemella.unit = item.unit
        db.delete(item)

    # Liste, ingredienti di base ed esclusi: dove il posto è già occupato la riga in
    # più si butta, perché è esattamente lo stesso alimento.
    for model, chiave in (
        (BaseIngredient, ("user_id",)),
        (ExcludedIngredient, ("user_id",)),
        (ShoppingListItem, ("shopping_list_id", "unit")),
    ):
        for row in db.query(model).filter(model.ingredient_id == doppione.id).all():
            filtri = [getattr(model, campo) == getattr(row, campo) for campo in chiave]
            occupato = (
                db.query(model)
                .filter(model.ingredient_id == canonical.id, *filtri)
                .first()
            )
            if occupato:
                db.delete(row)
            else:
                row.ingredient_id = canonical.id

    db.flush()
    db.delete(doppione)


def merge_duplicates(db: Session) -> list[tuple[str, list[str]]]:
    """Riporta l'anagrafica alla normalizzazione di oggi e fonde i doppioni.

    Serve dopo aver allargato l'elenco dei qualificatori: le righe già in tabella
    restano scritte come erano ("pesce spada surgelato"), e finché restano la dispensa
    non copre la ricetta che dice "pesce spada" — è lo stesso alimento per chi cucina,
    ma sono due righe diverse per il database.

    Tiene la riga più vecchia di ogni gruppo, le sposta addosso ricette, dispensa,
    liste e preferenze, e restituisce cosa ha fuso perché lo si possa leggere prima di
    fidarsi. Rieseguirla non fa niente: dopo la prima volta non ci sono più doppioni.
    """
    gruppi: dict[str, list[Ingredient]] = {}
    for ingredient in db.query(Ingredient).order_by(Ingredient.id).all():
        gruppi.setdefault(normalize_name(ingredient.name), []).append(ingredient)

    fusi: list[tuple[str, list[str]]] = []
    rimappati: dict[int, int] = {}

    for clean, rows in gruppi.items():
        if not clean:
            continue
        if len(rows) == 1 and rows[0].name == clean:
            continue

        # La riga da tenere è quella che ha già il nome giusto; altrimenti la più
        # vecchia, che è quella con più storia attaccata.
        canonical = next((r for r in rows if r.name == clean), rows[0])
        doppioni = [r for r in rows if r.id != canonical.id]

        for doppione in doppioni:
            rimappati[doppione.id] = canonical.id
            _merge_rows(db, canonical, doppione)

        canonical.name = clean
        if doppioni:
            fusi.append((clean, [d.name for d in doppioni]))

    # Il promemoria di cosa è stato scalato dalla dispensa cita gli ingredienti per id:
    # senza rimapparlo, annullare un "l'ho seguito" cercherebbe una riga cancellata.
    if rimappati:
        for meal in (
            db.query(PlannedMeal).filter(PlannedMeal.pantry_used.isnot(None)).all()
        ):
            meal.pantry_used = [
                {
                    **voce,
                    "ingredient_id": rimappati.get(
                        voce.get("ingredient_id"), voce.get("ingredient_id")
                    ),
                }
                for voce in (meal.pantry_used or [])
            ]

    db.commit()
    return fusi
