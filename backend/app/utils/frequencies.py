"""Le frequenze settimanali della dieta: «pesce 2-3 volte, carne rossa al massimo una».

Le diete dei nutrizionisti italiani sono scritte quasi sempre così, per gruppi di
alimenti e volte a settimana, e fin qui potevano stare solo nelle regole libere —
cioè erano un auspicio, letto dal modello in fondo a venti righe di contesto. Qui
diventano dati: un catalogo chiuso di gruppi (`FOODS`), un minimo e un massimo per
gruppo, e due operazioni che fa Python e non il modello, come per le cucine.

- `assign` decide **prima** della chiamata quale proteina va in quale pasto principale
  (pranzi e cene), tenendo conto di quello che la settimana ha già, e lo scrive accanto
  alla casella in «DA GENERARE».
- `count`/`report` contano **dopo** cosa c'è davvero nel piano, e la settimana lo dice.

Il catalogo è chiuso per la stessa ragione delle cucine: la chiave finisce nel prompt e
nel conteggio, e "pesce", "pesce azzurro" e "prodotti ittici" scritti a mano sarebbero
tre gruppi per la stessa cosa.
"""

import random

# Chiave → (etichetta, come si riconosce). Il riconoscimento guarda il reparto
# dell'ingrediente e, dove il reparto non basta (la carne è una sola categoria in
# anagrafica), l'inizio del nome.
_CARNE_BIANCA = {"pollo", "tacchino", "coniglio", "faraona"}
_SALUMI = ("prosciutto", "bresaola", "speck", "salame", "mortadella", "pancetta",
           "guanciale", "coppa", "lardo", "wurstel")
_NON_FORMAGGI = ("latte", "yogurt", "burro", "panna", "kefir")

FOODS: dict[str, str] = {
    "pesce": "Pesce",
    "legumi": "Legumi",
    "carne_bianca": "Carne bianca",
    "carne_rossa": "Carne rossa",
    "salumi": "Salumi",
    "uova": "Uova",
    "formaggi": "Formaggi",
}

# Le frequenze delle «Linee guida per una sana alimentazione» (CREA, 2018), in porzioni
# a settimana. Sono indicative e valgono per un adulto sano: si propongono con un
# pulsante a chi non ha una dieta scritta, non si impongono a chi ce l'ha.
CONSIGLIATE: dict[str, tuple[int, int | None]] = {
    "pesce": (2, 3),
    "legumi": (3, 4),
    "carne_bianca": (2, 3),
    "carne_rossa": (0, 1),
    "salumi": (0, 1),
    "uova": (2, 4),
    "formaggi": (2, 3),
}

# Quanto deve pesarne un piatto perché conti come «quella volta». Un cucchiaio di
# parmigiano sulla pasta non è la porzione di formaggi della settimana, e un'acciuga
# nel sugo non è il pesce.
SOGLIA_G = {
    "pesce": 50, "legumi": 30, "carne_bianca": 50, "carne_rossa": 50,
    "salumi": 30, "uova": 50, "formaggi": 40,
}


def food_of(category: str | None, name: str | None) -> str | None:
    """A quale gruppo appartiene un ingrediente, o None."""
    n = (name or "").strip().lower()
    c = category or ""
    if c == "pesce":
        return "pesce"
    if c == "legumi":
        return "legumi"
    if c == "uova":
        return "uova"
    if c == "carne":
        if n.startswith(_SALUMI):
            return "salumi"
        if _CARNE_BIANCA & set(n.replace("'", " ").split()):
            return "carne_bianca"
        return "carne_rossa"
    if c == "latticini" and not n.startswith(_NON_FORMAGGI):
        return "formaggi"
    return None


def options() -> dict:
    return {
        "foods": [{"key": k, "label": v} for k, v in FOODS.items()],
        "recommended": [
            {"food": k, "min": lo, "max": hi} for k, (lo, hi) in CONSIGLIATE.items()
        ],
    }


def clean(value: object) -> list[dict]:
    """Le frequenze in forma canonica: una riga per gruppo, nell'ordine del catalogo.

    Righe di gruppi sconosciuti si scartano, minimi negativi diventano zero, un massimo
    sotto il minimo si porta al minimo. Due righe per lo stesso gruppo: vince l'ultima.
    """
    per_gruppo: dict[str, dict] = {}
    for riga in value if isinstance(value, list) else []:
        if not isinstance(riga, dict):
            continue
        food = str(riga.get("food") or "").strip().lower()
        if food not in FOODS:
            continue
        try:
            lo = max(0, int(riga.get("min") or 0))
        except (TypeError, ValueError):
            lo = 0
        hi = riga.get("max")
        try:
            hi = None if hi in (None, "") else max(lo, int(hi))
        except (TypeError, ValueError):
            hi = None
        if lo == 0 and hi is None:
            continue  # nessun vincolo: la riga non dice niente
        per_gruppo[food] = {"food": food, "min": lo, "max": hi}
    return [per_gruppo[k] for k in FOODS if k in per_gruppo]


def label(food: str) -> str:
    return FOODS.get(food, food)


def describe(freq: dict) -> str:
    lo, hi = freq["min"], freq["max"]
    if hi is None:
        return f"almeno {lo}"
    if lo == 0:
        return f"al massimo {hi}"
    if lo == hi:
        return f"{lo}"
    return f"{lo}-{hi}"


def report(frequencies: list[dict], counts: dict[str, int]) -> list[dict]:
    """Per ogni vincolo: quante volte c'è, e se va bene."""
    out = []
    for f in clean(frequencies):
        n = counts.get(f["food"], 0)
        stato = "sotto" if n < f["min"] else "sopra" if f["max"] is not None and n > f["max"] else "ok"
        out.append({
            "food": f["food"], "label": label(f["food"]), "min": f["min"], "max": f["max"],
            "count": n, "status": stato,
        })
    return out


def assign(
    frequencies: list[dict],
    counts: dict[str, int],
    slots: list[tuple[int, int]],
    *,
    rng: random.Random | None = None,
) -> dict[int, dict]:
    """Quale proteina va in quale pasto principale da generare.

    `counts` è quello che la settimana ha già (i pasti che restano come sono), `slots`
    le caselle principali da riempire come (giorno, id). Restituisce per id
    `{"food": chiave}` dove un gruppo va messo, oppure `{"food": None, "avoid": [...]}`
    dove la scelta è libera ma qualche gruppo ha già raggiunto il massimo.

    Prima i minimi che mancano, poi il resto libero. Se i minimi chiedono più caselle
    di quante ce ne sono, passano quelli più lontani dall'obiettivo: il resoconto
    dopo dirà cosa è rimasto scoperto. Le caselle di uno stesso gruppo si sparpagliano:
    mai due nello stesso giorno se si può, e il più lontano possibile fra loro — è la
    stessa idea del sorteggio delle cucine, dove sette italiane di fila erano il guasto.
    """
    r = rng or random.Random()
    regole = clean(frequencies)
    if not regole or not slots:
        return {}

    mancano = {f["food"]: max(0, f["min"] - counts.get(f["food"], 0)) for f in regole}
    gettoni: list[str] = []
    while len(gettoni) < len(slots) and any(mancano.values()):
        # Il gruppo più lontano dal suo minimo; i pareggi a caso.
        candidati = [k for k, v in mancano.items() if v > 0]
        r.shuffle(candidati)
        k = max(candidati, key=lambda k: mancano[k])
        gettoni.append(k)
        mancano[k] -= 1

    usati = dict(counts)
    for k in gettoni:
        usati[k] = usati.get(k, 0) + 1
    pieni = [
        f["food"] for f in regole
        if f["max"] is not None and usati.get(f["food"], 0) >= f["max"]
    ]

    liberi = sorted(slots)
    posto: dict[int, dict] = {}
    giorni_di: dict[str, list[int]] = {}
    for k in gettoni:
        # La casella libera che sta più lontana dalle altre dello stesso gruppo.
        def distanza(slot, k=k):
            presi = giorni_di.get(k, [])
            return min((abs(slot[0] - g) for g in presi), default=99) + r.random() * 0.1
        scelta = max(liberi, key=distanza)
        liberi.remove(scelta)
        giorni_di.setdefault(k, []).append(scelta[0])
        posto[scelta[1]] = {"food": k}
    for _, meal_id in liberi:
        posto[meal_id] = {"food": None, "avoid": list(pieni)}
    return posto


def prompt_hint(assegnazione: dict | None) -> str:
    """Il pezzo da scrivere accanto alla casella in «DA GENERARE»."""
    if not assegnazione:
        return ""
    if assegnazione.get("food"):
        return f" — PROTEINA: {label(assegnazione['food'])}"
    if assegnazione.get("avoid"):
        return " — PROTEINA: libera, ma non " + ", ".join(
            label(k).lower() for k in assegnazione["avoid"]
        )
    return ""
