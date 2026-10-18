"""Gli alimenti esclusi, controllati dopo il modello e non solo chiesti nel prompt.

Fino a qui gli esclusi arrivavano al modello in ogni prompt e basta: nessun punto del
server guardava gli ingredienti delle ricette salvate. Un modello che ignora la regola,
o una chat che asseconda «mettici le arachidi», scriveva l'allergene in ricetta e in
lista della spesa senza un avviso. Ora ogni ricetta che nasce o cambia per mano del
modello passa da `check_recipe`, e chi la viola non entra nel piano.

Il confronto è volutamente largo: un escluso è un nome scritto dall'utente
("frutti di mare", "glutine"), non sempre un ingrediente dell'anagrafica, e scartare
un piatto innocente costa una rigenerazione, mentre farne passare uno sbagliato può
costare una reazione allergica.
"""

import re
from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    DayPlan,
    ExcludedIngredient,
    Ingredient,
    MealSlot,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    WeekPlan,
)
from .ai_client import AIError
from .ingredients import load_rules, normalize_name

# Le famiglie: un escluso che è una categoria si porta dietro gli alimenti che la
# contengono. Chiavi e termini sono già nella forma che esce da `normalize_name`.
FAMIGLIE: dict[str, tuple[str, ...]] = {
    "glutine": (
        "pasta", "pane", "farina", "frumento", "grano", "orzo", "farro", "segale",
        "couscous", "cous cous", "bulgur", "seitan", "cracker", "grissini",
        "fette biscottate", "pangrattato", "biscotti", "piadina", "gnocchi", "pizza",
        "semola", "kamut", "tortillas", "pan carrè", "friselle", "taralli",
    ),
    "lattosio": (
        "latte", "yogurt", "formaggio", "burro", "panna", "ricotta", "mozzarella",
        "parmigiano", "grana", "stracchino", "mascarpone", "scamorza", "provola",
        "fiocchi di latte", "besciamella", "pecorino", "feta", "gorgonzola",
        "fontina", "emmental", "asiago", "crescenza", "robiola", "skyr", "kefir",
    ),
    "frutta a guscio": (
        "noci", "nocciole", "mandorle", "pistacchi", "anacardi", "pinoli",
        "noci pecan", "macadamia", "noci brasiliane", "pesto", "granella",
    ),
    "frutti di mare": (
        "gamberi", "gamberetti", "cozze", "vongole", "calamari", "seppie", "polpo",
        "scampi", "aragosta", "astice", "granchio", "ostriche", "totani",
        "moscardini", "canocchie", "mazzancolle", "capesante", "lupini",
    ),
    "crostacei": (
        "gamberi", "gamberetti", "scampi", "aragosta", "astice", "granchio",
        "canocchie", "mazzancolle",
    ),
    "molluschi": (
        "cozze", "vongole", "calamari", "seppie", "polpo", "ostriche", "totani",
        "moscardini", "capesante", "lupini",
    ),
    "pesce": (
        "salmone", "tonno", "merluzzo", "orata", "branzino", "spigola", "sgombro",
        "alici", "acciughe", "sardine", "pesce spada", "trota", "nasello",
        "platessa", "baccalà", "stoccafisso", "sogliola", "halibut",
        "filetto di pesce magro", "bottarga", "colatura",
    ),
    "uova": ("uovo", "uova", "albume", "albumi", "tuorlo", "maionese", "pasta all'uovo"),
    "soia": ("soia", "tofu", "tempeh", "edamame", "miso", "salsa di soia"),
    "arachidi": ("arachidi", "burro di arachidi"),
    "sesamo": ("sesamo", "tahina", "tahini", "gomasio"),
    "sedano": ("sedano", "sedano rapa"),
    "senape": ("senape",),
    "piccante": (
        "peperoncino", "nduja", "tabasco", "harissa", "sriracha", "jalapeno",
        "paprika piccante", "chili",
    ),
}
# Le parole che dicono la stessa famiglia in un altro modo.
SINONIMI = {
    "latticini": "lattosio",
    "latte e derivati": "lattosio",
    "frutta secca": "frutta a guscio",
    "crostaceo": "crostacei",
    "mollusco": "molluschi",
    "uovo": "uova",
    "celiachia": "glutine",
    "noci": "frutta a guscio",
}

# Quello che toglie l'alimento invece di aggiungerlo: "pasta senza glutine" a un
# celiaco va bene, e il latte di soia non ha lattosio.
_SENZA = re.compile(r"\b(senza|gluten\s*free|delattosat\w*|zero\s+lattosio)\b")
_VEGETALE = re.compile(
    r"\b(latte|yogurt|burro|panna|formaggio)\s+(vegetale|di\s+(soia|riso|avena|mandorl\w*"
    r"|cocco|anacardi|nocciol\w*|arachidi))\b"
)


class ExcludedFoodError(AIError):
    """Una ricetta che contiene un alimento escluso: non entra nel piano."""

    def __init__(self, detail: str, hits: list[str]):
        super().__init__(detail, status_code=422)
        self.hits = hits


def _schema(termine: str) -> re.Pattern:
    """Il termine come parola intera, singolare o plurale ("noce" e "noci")."""
    parole = termine.split()
    ultima = parole[-1]
    radice = ultima[:-1] if len(ultima) > 4 else ultima
    coda = r"\w?" if radice != ultima else ""
    corpo = r"\s+".join([re.escape(p) for p in parole[:-1]] + [re.escape(radice) + coda])
    return re.compile(rf"\b{corpo}\b")


def _famiglia(nome: str) -> tuple[str, ...]:
    chiave = SINONIMI.get(nome, nome)
    return (nome, *FAMIGLIE.get(chiave, ()))


def exclusion_rules(db: Session, user_id: int) -> list[tuple[str, list[re.Pattern]]]:
    """Per ogni escluso dell'utente, il suo nome e gli schemi che lo riconoscono."""
    rows = (
        db.query(ExcludedIngredient, Ingredient)
        .outerjoin(Ingredient, Ingredient.id == ExcludedIngredient.ingredient_id)
        .filter(ExcludedIngredient.user_id == user_id)
        .all()
    )
    regole = []
    for escluso, ingrediente in rows:
        nome = (ingrediente.name if ingrediente else escluso.custom_name or "").strip().lower()
        if nome:
            regole.append((nome, [_schema(t) for t in _famiglia(nome)]))
    return regole


def _contiene(nome: str, schemi: list[re.Pattern]) -> bool:
    if not any(s.search(nome) for s in schemi):
        return False
    return not (_SENZA.search(nome) or _VEGETALE.search(nome))


def find_excluded(
    db: Session, user_id: int, names: Iterable[str], regole=None
) -> list[str]:
    """Gli ingredienti (fra quelli dati) che urtano un escluso: «nome (escluso: X)»."""
    regole = exclusion_rules(db, user_id) if regole is None else regole
    if not regole:
        return []
    norm = load_rules(db)
    trovati = []
    for nome in names:
        crudo = " ".join(str(nome or "").lower().split())
        if not crudo:
            continue
        forme = {crudo, normalize_name(crudo, norm)}
        for escluso, schemi in regole:
            if any(_contiene(f, schemi) for f in forme):
                trovati.append(f"{crudo} (escluso: {escluso})")
                break
    return trovati


def ingredient_names(data: dict) -> list[str]:
    ingredienti = data.get("ingredients") if isinstance(data, dict) else None
    return [
        i.get("name") for i in (ingredienti or []) if isinstance(i, dict) and i.get("name")
    ]


def recipe_violations(db: Session, user_id: int, recipe_id: int, regole=None) -> list[str]:
    """Gli esclusi che una ricetta già salvata contiene."""
    nomi = [
        name
        for (name,) in db.query(Ingredient.name)
        .join(RecipeIngredient, RecipeIngredient.ingredient_id == Ingredient.id)
        .filter(RecipeIngredient.recipe_id == recipe_id)
    ]
    return find_excluded(db, user_id, nomi, regole)


def planned_conflicts(db: Session, user_id: int, regole) -> list[str]:
    """I pasti da oggi in avanti la cui ricetta urta gli esclusi dati.

    Serve quando l'utente aggiunge un escluso: la settimana già generata e i pasti
    fissi non cambiano da soli, e chi ha appena scoperto un'allergia deve sapere dove
    quell'alimento è ancora in programma.
    """
    from .planner import DAY_NAMES, today

    righe = (
        db.query(DayPlan, PlannedMeal, MealSlot, Recipe)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .join(PlannedMeal, PlannedMeal.day_plan_id == DayPlan.id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .join(Recipe, Recipe.id == PlannedMeal.recipe_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date >= today(),
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
        )
        .order_by(DayPlan.date, MealSlot.order_index)
        .all()
    )
    esito: dict[int, bool] = {}
    conflitti = []
    for day, _meal, slot, recipe in righe:
        if recipe.id not in esito:
            esito[recipe.id] = bool(recipe_violations(db, user_id, recipe.id, regole))
        if esito[recipe.id]:
            conflitti.append(
                f"{DAY_NAMES[day.day_of_week]} {day.date.day} · {slot.name}: {recipe.title}"
            )
    return conflitti


def check_recipe(db: Session, user_id: int, data: dict) -> None:
    """Solleva `ExcludedFoodError` se la ricetta proposta contiene un escluso."""
    trovati = find_excluded(db, user_id, ingredient_names(data))
    if trovati:
        titolo = (data.get("title") or "La ricetta").strip()
        raise ExcludedFoodError(
            f"«{titolo}» contiene {', '.join(trovati)}, che hai escluso: non l'ho usata.",
            trovati,
        )


def add_excluded(db: Session, user_id: int, name: str, reason: str | None) -> dict:
    """Aggiunge un alimento da non usare mai, e dice quali pasti in programma lo usano.

    Se il nome corrisponde a un ingrediente noto lo si aggancia all'anagrafica (così
    la lista della spesa e la dispensa parlano la stessa lingua); altrimenti si
    conserva il testo libero — "frutti di mare" non è un ingrediente, è una famiglia.
    """
    clean = normalize_name(name, load_rules(db))
    if not clean:
        raise HTTPException(400, "Nome non valido")

    known = db.query(Ingredient).filter(Ingredient.name == clean).first()
    already = (
        db.query(ExcludedIngredient)
        .filter(
            ExcludedIngredient.user_id == user_id,
            (ExcludedIngredient.ingredient_id == known.id)
            if known
            else (ExcludedIngredient.custom_name == clean),
        )
        .first()
    )
    if already:
        raise HTTPException(409, f"'{clean}' è già nella lista degli esclusi.")

    row = ExcludedIngredient(
        user_id=user_id,
        ingredient_id=known.id if known else None,
        custom_name=None if known else clean,
        reason=reason,
    )
    db.add(row)
    db.commit()
    nome = known.name if known else clean
    # Quello che è già in programma non cambia da solo: lo si dice, così chi ha appena
    # scoperto un'allergia sa quali pasti rigenerare.
    regole = [r for r in exclusion_rules(db, user_id) if r[0] == nome]
    return {
        "id": row.id,
        "ingredient_id": row.ingredient_id,
        "name": nome,
        "category": known.category if known else None,
        "reason": row.reason,
        "conflicts": planned_conflicts(db, user_id, regole),
    }
