"""I macro di una ricetta si calcolano dagli ingredienti, non si credono al modello.

Il modello scrive sotto ogni ricetta calorie e macro, e il prompt gli chiede di stare
nel ±10% del target. Ma quel numero è una somma fatta a memoria: "650 kcal" sotto una
ricetta che ne pesa 820 non è un caso raro, ed è il numero su cui si reggono totali del
giorno, aderenza e grafici. Qui la somma la fa Python, con la composizione per 100 g
che l'anagrafica porta per ogni ingrediente (`Ingredient.kcal_100g` e compagni).

Tre pezzi, usati in quest'ordine dalla generazione:

1. `ensure_composition` — i nomi che il catalogo non conosce ricevono una stima dal
   modello, **una chiamata per generazione** e poi restano in anagrafica per sempre.
2. `fit_to_target` — se la ricetta calcolata sta fuori dal ±10% che il prompt
   promette, si ritoccano le grammature degli ingredienti che portano ciascun macro.
   È lo stesso principio del sorteggio delle cucine: quello che si può calcolare lo
   calcola Python, invece di chiederlo a un modello e sperare.
3. `compute` — a ricetta fatta, i numeri da salvare. Se anche un solo ingrediente non
   ha composizione la somma non si fa e restano quelli dichiarati, segnati come tali
   (`Recipe.nutrition_source = "dichiarata"`): un totale che ne tiene fuori uno è
   peggio di un totale dichiarato, perché sembra vero.

Le ricette scritte a mano dall'utente non passano da qui: i numeri li ha scritti lui,
come nell'editor della dieta.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Ingredient
from ..utils.composition import COMPOSITION, DENSITY, GRAMS_PER_UNIT
from ..utils.units import normalize_unit, to_base

logger = logging.getLogger(__name__)

# I test lo spengono (vedi `conftest.py`): i modelli finti scrivono numeri tondi che
# non tornano con le grammature, e ricalcolarli cambierebbe ogni conto della suite.
# Chi prova il calcolo (`test_macro_calcolati.py`) lo riaccende.
ATTIVO = True

# Unità che non pesano niente per la dieta: un pizzico di sale, l'olio "q.b." per
# ungere la padella. Si contano come zero invece di far saltare il conto.
_SENZA_PESO = {"q.b.", "pizzichi"}

# Le unità che si leggono su una bilancia o un misurino. Le altre (cucchiai, tazze,
# bicchieri) si arrotondano nella loro unità: "1,47 cucchiai" non lo scrive nessuno.
_MISURE_DA_BILANCIA = {"g", "kg", "mg", "ml", "l", "cl", "dl"}

# La tolleranza che il prompt promette (regola MACRO). Dentro, la ricetta si lascia
# com'è: ritoccare un piatto che sta già nei numeri vorrebbe dire cambiargli le
# grammature per niente.
TOLLERANZA = 0.10
# Per le proteine sotto i 50 g il 10% sono 4-5 grammi: meno della differenza fra due
# uova. Sotto questa soglia lo scarto non è un errore.
TOLLERANZA_PROTEINE_G = 5.0

# Quanto si può allungare o accorciare un ingrediente. Oltre, il piatto non è più
# quello che il modello ha pensato (tre volte la pasta, un terzo del pollo) ed è
# meglio lasciarlo fuori target e dirlo, che servire un'altra ricetta.
_FATTORE_MIN = 0.4
_FATTORE_MAX = 2.5
# Le righe piccole si possono allungare di più: un cucchiaino d'olio che diventa un
# cucchiaio e mezzo è sempre lo stesso piatto, 100 g di pasta che diventano 400 no.
_FATTORE_MAX_PICCOLE = 4.0
_SOGLIA_PICCOLE_G = 20


def _limita(r: "_Riga", f: float) -> float:
    alto = _FATTORE_MAX_PICCOLE if r.grams < _SOGLIA_PICCOLE_G else _FATTORE_MAX
    return min(max(f, _FATTORE_MIN), alto)


# ── La composizione ────────────────────────────────────────────────────────────


def apply_catalog_composition(ingredient: Ingredient) -> bool:
    """Scrive sulla riga la composizione del catalogo, se il catalogo la conosce.

    Non tocca quella corretta a mano (`composition_source == "utente"`): il seed gira
    a ogni avvio del container e se la riprenderebbe, come farebbe col reparto.
    """
    if ingredient.composition_source == "utente":
        return False
    values = COMPOSITION.get(ingredient.name)
    if values is None:
        return False
    kcal, protein, carbs, fat = values
    ingredient.kcal_100g = kcal
    ingredient.protein_100g = protein
    ingredient.carbs_100g = carbs
    ingredient.fat_100g = fat
    ingredient.grams_per_unit = GRAMS_PER_UNIT.get(ingredient.name)
    ingredient.density = DENSITY.get(ingredient.name)
    ingredient.composition_source = "catalogo"
    return True


def has_composition(ingredient: Ingredient | None) -> bool:
    return ingredient is not None and None not in (
        ingredient.kcal_100g,
        ingredient.protein_100g,
        ingredient.carbs_100g,
        ingredient.fat_100g,
    )


def grams_of(ingredient: Ingredient, quantity: float, unit: str) -> float | None:
    """Quanti grammi sono `quantity` `unit` di quell'ingrediente. None = non si sa."""
    if normalize_unit(unit) in _SENZA_PESO:
        return 0.0
    base_qty, base = to_base(quantity or 0.0, unit)
    if base == "g":
        return base_qty
    if base == "ml":
        return base_qty * (ingredient.density or 1.0)
    if base == "unità" and ingredient.grams_per_unit:
        return base_qty * ingredient.grams_per_unit
    return None


# ── Il conto ───────────────────────────────────────────────────────────────────


@dataclass
class Totali:
    kcal: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0

    def as_nutrition(self) -> dict:
        return {
            "calories": int(round(self.kcal)),
            "protein_g": round(self.protein, 1),
            "carbs_g": round(self.carbs, 1),
            "fat_g": round(self.fat, 1),
        }


@dataclass
class _Riga:
    item: dict
    ingredient: Ingredient
    grams: float

    @property
    def kcal(self) -> float:
        return self.grams / 100 * self.ingredient.kcal_100g

    @property
    def macro(self) -> tuple[float, float, float]:
        f = self.grams / 100
        i = self.ingredient
        return (f * i.protein_100g, f * i.carbs_100g, f * i.fat_100g)


def _righe(db: Session, items: list[dict]) -> tuple[list[_Riga], list[str]]:
    """Le righe calcolabili e i nomi di quelle che non lo sono."""
    righe, mancanti = [], []
    for item in items:
        ingredient = db.get(Ingredient, item["ingredient_id"])
        grams = (
            grams_of(ingredient, item["quantity"], item["unit"])
            if has_composition(ingredient)
            else None
        )
        if grams is None:
            mancanti.append(ingredient.name if ingredient else item.get("name", "?"))
        else:
            righe.append(_Riga(item, ingredient, grams))
    return righe, mancanti


def _somma(righe: list[_Riga]) -> Totali:
    t = Totali()
    for r in righe:
        p, c, f = r.macro
        t.kcal += r.kcal
        t.protein += p
        t.carbs += c
        t.fat += f
    return t


def compute(db: Session, items: list[dict]) -> Totali | None:
    """Calorie e macro della ricetta, o None se un ingrediente non si sa contare.

    `items` sono gli ingredienti già risolti (`ingredient_id`, `quantity`, `unit`),
    cioè la stessa forma che `recipes._resolve` prepara per creare la ricetta.
    """
    if not ATTIVO:
        return None
    righe, mancanti = _righe(db, items)
    if mancanti:
        return None
    return _somma(righe)


# ── Il ritocco delle grammature ────────────────────────────────────────────────


@dataclass
class Target:
    kcal: float
    protein: float
    carbs: float
    fat: float


def _dentro(t: Totali, target: Target) -> bool:
    if target.kcal <= 0:
        return True
    if abs(t.kcal - target.kcal) > TOLLERANZA * target.kcal:
        return False
    margine_p = max(TOLLERANZA * target.protein, TOLLERANZA_PROTEINE_G)
    return abs(t.protein - target.protein) <= margine_p


def _det3(m: list[list[float]]) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _risolvi3(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Cramer su un 3×3: tre leve, tre macro. None se il sistema è degenere."""
    d = _det3(a)
    if abs(d) < 1e-9:
        return None
    out = []
    for col in range(3):
        m = [row[:] for row in a]
        for r in range(3):
            m[r][col] = b[r]
        out.append(_det3(m) / d)
    return out


def _minimi_quadrati(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Le k leve (k ≤ 3) che avvicinano di più i tre macro al target.

    Con tre leve diverse è il sistema esatto; con meno, le equazioni normali
    (AᵀA)x = Aᵀb. None se il sistema è degenere (due leve con la stessa composizione).
    """
    k = len(a[0]) if a else 0
    if k == 0:
        return None
    if k == 3:
        return _risolvi3(a, b)
    ata = [[sum(a[r][i] * a[r][j] for r in range(3)) for j in range(k)] for i in range(k)]
    atb = [sum(a[r][i] * b[r] for r in range(3)) for i in range(k)]
    if k == 1:
        return [atb[0] / ata[0][0]] if abs(ata[0][0]) > 1e-9 else None
    det = ata[0][0] * ata[1][1] - ata[0][1] * ata[1][0]
    if abs(det) < 1e-9:
        return None
    return [
        (atb[0] * ata[1][1] - ata[0][1] * atb[1]) / det,
        (ata[0][0] * atb[1] - atb[0] * ata[1][0]) / det,
    ]


def _arrotonda(item: dict, fattore: float) -> float:
    """La quantità nuova, arrotondata come la scriverebbe una persona.

    Grammi e millilitri a 5 sopra i 100, all'unità sopra i 20, al mezzo sotto; le
    misure da cucina (cucchiai, tazze) al mezzo cucchiaio, mai sotto il mezzo.
    """
    unit = normalize_unit(item["unit"])
    qty = item["quantity"] * fattore
    base_qty, base = to_base(qty, unit)
    if unit in _MISURE_DA_BILANCIA:
        passo = 5 if base_qty >= 100 else 1 if base_qty >= 20 else 0.5
        arrotondata = max(passo, round(base_qty / passo) * passo)
        per_unita = to_base(1, unit)[0] or 1
        return round(arrotondata / per_unita, 3)
    return max(0.5, round(qty * 2) / 2)


def fit_to_target(db: Session, items: list[dict], target: Target) -> list[dict]:
    """Le stesse righe, con le grammature ritoccate perché la ricetta torni nei numeri.

    Si muovono solo le **leve**: l'ingrediente che porta più proteine, quello che porta
    più carboidrati e quello che porta più grassi (il pollo, la pasta, l'olio). Tre
    leve per tre macro: è un sistema 3×3, e lo si risolve — le calorie tornano da sé,
    perché sono fatte dei tre macro. Se due macro hanno la stessa leva (la pasta in un
    piatto senza carne) le leve sono meno dei macro e si risolve ai minimi quadrati.
    Le altre righe restano come le ha scritte il modello: le verdure, le spezie, il
    limone non sono lì per i numeri.

    Nessun ingrediente si allunga o si accorcia oltre i limiti (`_limita`):
    se dentro quei limiti il target non si raggiunge, il piatto resta quello che è,
    un po' fuori target, e i numeri salvati diranno quanto.

    Le righe contate a pezzi non si toccano (2 uova non diventano 2,7 uova), né quelle
    che non si sanno pesare: per loro il conto non si fa e la ricetta resta com'era.
    """
    if not ATTIVO:
        return items
    righe, mancanti = _righe(db, items)
    if mancanti or not righe:
        return items
    totali = _somma(righe)
    if _dentro(totali, target):
        return items

    # Una leva è una riga pesata (non a pezzi) che porta qualcosa: anche un cucchiaino
    # d'olio — 5 ml sono 40 kcal, ed è proprio la riga che regola i grassi.
    leve_possibili = [
        r for r in righe
        if r.kcal >= 10
        and to_base(1, normalize_unit(r.item["unit"]))[1] in ("g", "ml")
    ]
    if not leve_possibili:
        return items

    # Per ogni macro, la riga che ne porta di più. Possono coincidere (la pasta porta
    # sia proteine che carboidrati in un piatto senza carne): allora le leve sono due,
    # o una, e il sistema si risolve ai minimi quadrati invece che esatto.
    leve: list[_Riga] = []
    for m in range(3):
        r = max(leve_possibili, key=lambda r, m=m: r.macro[m])
        if r.macro[m] > 0 and all(r is not l for l in leve):
            leve.append(r)

    fattori: dict[int, float] = {}
    fisse = [r for r in righe if all(r is not l for l in leve)]
    resto = _somma(fisse)
    a = [[l.macro[m] for l in leve] for m in range(3)]
    b = [target.protein - resto.protein, target.carbs - resto.carbs, target.fat - resto.fat]
    soluzione = _minimi_quadrati(a, b)
    # Una soluzione negativa vuol dire che con quelle leve il target non si raggiunge
    # (togliere grassi che non ci sono): si lascia perdere. Una troppo grande o troppo
    # piccola si porta al limite — il macro che la chiedeva resta un po' corto, e ci
    # pensa il passo successivo sulle calorie.
    if soluzione and all(f > 0 for f in soluzione):
        fattori = {
            id(l): _limita(l, f) for l, f in zip(leve, soluzione)
        }

    # Le calorie, alla fine, devono tornare: se le leve da sole non ci arrivano (un
    # fattore portato al limite, una soluzione scartata) si allungano o si accorciano
    # insieme le stesse leve di quello che manca. Le altre righe restano come sono.
    def kcal_con(f: dict[int, float]) -> float:
        return sum(r.kcal * f.get(id(r), 1.0) for r in righe)

    if abs(kcal_con(fattori) - target.kcal) > TOLLERANZA * target.kcal:
        mobili = {id(l) for l in leve}
        fisse_kcal = sum(r.kcal * fattori.get(id(r), 1.0) for r in righe if id(r) not in mobili)
        mobili_kcal = sum(l.kcal * fattori.get(id(l), 1.0) for l in leve)
        s = (target.kcal - fisse_kcal) / mobili_kcal if mobili_kcal > 0 else 1.0
        if s > 0:
            fattori = {
                id(l): _limita(l, fattori.get(id(l), 1.0) * s) for l in leve
            }

    per_item = {id(r.item): fattori.get(id(r)) for r in righe}
    out = []
    for item in items:
        f = per_item.get(id(item))
        out.append({**item, "quantity": _arrotonda(item, f)} if f else item)
    return out


# ── La stima del modello per i nomi che il catalogo non ha ─────────────────────


def missing_composition(db: Session, ingredient_ids: list[int]) -> list[Ingredient]:
    if not ATTIVO or not ingredient_ids:
        return []
    rows = db.query(Ingredient).filter(Ingredient.id.in_(set(ingredient_ids))).all()
    return [i for i in rows if not has_composition(i)]


def ensure_composition(db: Session, client, ingredient_ids: list[int]) -> int:
    """Chiede al modello la composizione dei nomi che non ce l'hanno. Una chiamata.

    Restituisce quanti ne ha imparati. Non solleva mai: è un di più su una
    generazione già pagata, e perderla per una stima mancata sarebbe assurdo — le
    ricette con quei nomi terranno i macro dichiarati, come prima.
    """
    from . import prompts  # import tardivo: prompts non deve dipendere da qui

    mancanti = missing_composition(db, ingredient_ids)
    if not mancanti:
        return 0
    try:
        data = client.generate_json(
            prompts.COMPOSITION_SYSTEM,
            prompts.render(
                prompts.COMPOSITION_PROMPT,
                names="\n".join(f"- {i.name}" for i in mancanti),
            ),
            max_tokens=200 + 120 * len(mancanti),
            thinking=False,
        )
    except Exception:  # noqa: BLE001 — vedi docstring
        logger.warning("Stima della composizione non riuscita", exc_info=True)
        return 0

    per_nome = {i.name: i for i in mancanti}
    imparati = 0
    for voce in (data or {}).get("items", []) if isinstance(data, dict) else []:
        if not isinstance(voce, dict):
            continue
        ingredient = per_nome.get(str(voce.get("name", "")).strip().lower())
        if ingredient is None:
            continue
        try:
            valori = [float(voce[k]) for k in ("kcal", "protein_g", "carbs_g", "fat_g")]
        except (KeyError, TypeError, ValueError):
            continue
        if any(v < 0 for v in valori) or valori[0] > 900:
            continue
        (
            ingredient.kcal_100g,
            ingredient.protein_100g,
            ingredient.carbs_100g,
            ingredient.fat_100g,
        ) = valori
        for campo in ("grams_per_unit", "density"):
            try:
                valore = float(voce.get(campo)) if voce.get(campo) else None
            except (TypeError, ValueError):
                valore = None
            setattr(ingredient, campo, valore if valore and valore > 0 else None)
        ingredient.composition_source = "ai"
        imparati += 1
    db.flush()
    return imparati
