"""Stagionalità dei prodotti ortofrutticoli italiani.

Serve a due cose: dare all'AI l'elenco di cosa è di stagione nel mese corrente
(così le ricette non chiedono pomodori a gennaio) e riempire `season_months`
quando un ingrediente nuovo entra in anagrafica.
"""

from datetime import date

# Mesi di disponibilità (1 = gennaio). Chiavi in minuscolo, come i nomi in anagrafica.
SEASONAL_PRODUCTS: dict[str, list[int]] = {
    # Frutta
    "fragole": [4, 5, 6],
    "ciliegie": [5, 6],
    "albicocche": [6, 7, 8],
    "pesche": [6, 7, 8],
    "susine": [7, 8, 9],
    "fichi": [7, 8, 9],
    "uva": [8, 9, 10],
    "melone": [6, 7, 8],
    "anguria": [6, 7, 8],
    "mele": [8, 9, 10, 11, 12, 1, 2, 3],
    "pere": [8, 9, 10, 11, 12, 1],
    "arance": [11, 12, 1, 2, 3, 4],
    "mandarini": [11, 12, 1, 2],
    "clementine": [11, 12, 1, 2],
    "limoni": [11, 12, 1, 2, 3, 4, 5],
    "pompelmo": [11, 12, 1, 2, 3],
    "kiwi": [10, 11, 12, 1, 2, 3, 4],
    "cachi": [10, 11],
    "castagne": [10, 11],
    "melagrana": [10, 11, 12],
    "lamponi": [6, 7, 8, 9],
    "mirtilli": [6, 7, 8, 9],
    # Verdura
    "asparagi": [3, 4, 5, 6],
    "carciofi": [1, 2, 3, 4, 11, 12],
    "fave": [3, 4, 5],
    "piselli": [4, 5, 6],
    "fagiolini": [6, 7, 8, 9],
    "zucchine": [5, 6, 7, 8, 9],
    "melanzane": [6, 7, 8, 9],
    "pomodori": [6, 7, 8, 9],
    "pomodorini": [6, 7, 8, 9],
    "peperoni": [6, 7, 8, 9],
    "cetrioli": [6, 7, 8],
    "basilico": [5, 6, 7, 8, 9],
    "zucca": [9, 10, 11, 12],
    "funghi porcini": [9, 10, 11],
    "funghi champignon": list(range(1, 13)),
    "radicchio": [10, 11, 12, 1, 2, 3],
    "broccoli": [10, 11, 12, 1, 2, 3],
    "cavolfiore": [10, 11, 12, 1, 2, 3],
    "cavolo nero": [10, 11, 12, 1, 2],
    "verza": [10, 11, 12, 1, 2, 3],
    "cavolini di bruxelles": [11, 12, 1, 2],
    "finocchi": [10, 11, 12, 1, 2, 3],
    "spinaci": [1, 2, 3, 4, 10, 11, 12],
    "bietola": [3, 4, 5, 6, 7, 8, 9, 10, 11],
    "cicoria": [10, 11, 12, 1, 2, 3, 4],
    "porri": [9, 10, 11, 12, 1, 2, 3],
    "sedano": [1, 2, 3, 9, 10, 11, 12],
    "rape": [10, 11, 12, 1, 2],
    "topinambur": [11, 12, 1, 2],
    "puntarelle": [12, 1, 2, 3],
    "agretti": [3, 4, 5],
    "rucola": list(range(1, 13)),
    "lattuga": list(range(1, 13)),
    "carote": list(range(1, 13)),
    "patate": list(range(1, 13)),
    "cipolle": list(range(1, 13)),
}

SEASON_BY_MONTH = {
    12: "inverno", 1: "inverno", 2: "inverno",
    3: "primavera", 4: "primavera", 5: "primavera",
    6: "estate", 7: "estate", 8: "estate",
    9: "autunno", 10: "autunno", 11: "autunno",
}

MONTH_NAMES = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


def season_months_for(name: str) -> list[int] | None:
    """Mesi di stagione per un ingrediente, o None se non è un prodotto stagionale."""
    return SEASONAL_PRODUCTS.get(name.strip().lower())


def in_season(month: int) -> list[str]:
    """Prodotti di stagione nel mese dato, esclusi quelli disponibili tutto l'anno
    (elencarli non aiuterebbe l'AI a scegliere)."""
    return [
        name
        for name, months in SEASONAL_PRODUCTS.items()
        if month in months and len(months) < 12
    ]


def current_month() -> int:
    return date.today().month


def current_month_name() -> str:
    return MONTH_NAMES[current_month() - 1]


def current_season() -> str:
    return SEASON_BY_MONTH[current_month()]
