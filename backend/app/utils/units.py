"""Unità di misura: normalizzazione, somma e conversione per la stima di costo.

L'AI scrive le quantità in modo naturale ("200 g", "0.5 kg", "2 cucchiai"), ma la
lista della spesa deve sommare mele con mele. Qui si riporta tutto a tre unità
canoniche — g, ml, unità — e si tiene una tabella di conversione per le misure
"da cucina" che altrimenti non sarebbero sommabili.
"""

# Alias → unità canonica. Chiavi in minuscolo, senza punteggiatura.
_ALIASES = {
    "g": "g", "gr": "g", "grammi": "g", "grammo": "g",
    "kg": "kg", "chilo": "kg", "chili": "kg", "chilogrammi": "kg",
    "mg": "mg", "milligrammi": "mg",
    "ml": "ml", "millilitri": "ml", "cc": "ml",
    "l": "l", "lt": "l", "litri": "l", "litro": "l",
    "cl": "cl", "centilitri": "cl", "dl": "dl", "decilitri": "dl",
    "unità": "unità", "unita": "unità", "pz": "unità", "pezzi": "unità",
    "pezzo": "unità", "n": "unità", "": "unità",
    "cucchiaio": "cucchiai", "cucchiai": "cucchiai",
    "cucchiaino": "cucchiaini", "cucchiaini": "cucchiaini",
    "tazza": "tazze", "tazze": "tazze",
    "bicchiere": "bicchieri", "bicchieri": "bicchieri",
    "spicchio": "spicchi", "spicchi": "spicchi",
    "foglia": "foglie", "foglie": "foglie",
    "fetta": "fette", "fette": "fette",
    "mazzo": "mazzi", "mazzi": "mazzi",
    "pizzico": "pizzichi", "pizzichi": "pizzichi",
    "qb": "q.b.", "q.b.": "q.b.", "quanto basta": "q.b.",
}

# Fattori verso l'unità canonica di base. Le misure da cucina sono approssimazioni
# volutamente grossolane: servono a fare una lista della spesa, non a dosare farmaci.
_TO_BASE: dict[str, tuple[float, str]] = {
    "g": (1, "g"),
    "kg": (1000, "g"),
    "mg": (0.001, "g"),
    "ml": (1, "ml"),
    "l": (1000, "ml"),
    "cl": (10, "ml"),
    "dl": (100, "ml"),
    "cucchiai": (15, "ml"),
    "cucchiaini": (5, "ml"),
    "tazze": (240, "ml"),
    "bicchieri": (200, "ml"),
    "unità": (1, "unità"),
    "spicchi": (1, "unità"),
    "foglie": (1, "unità"),
    "fette": (1, "unità"),
    "mazzi": (1, "unità"),
    "pizzichi": (1, "unità"),
}


def normalize_unit(unit: str | None) -> str:
    u = (unit or "").strip().lower()
    if u in _ALIASES:
        return _ALIASES[u]
    # Solo se non ha già fatto match: togliere il punto finale aiuta con "gr." o "ml."
    # ma non deve rovinare "q.b.", che nell'elenco c'è già così com'è.
    return _ALIASES.get(u.rstrip("."), u or "unità")


def to_base(quantity: float, unit: str) -> tuple[float, str]:
    """Riporta (quantità, unità) all'unità di base sommabile: g, ml o unità.

    Le unità sconosciute ("q.b.", roba inventata dall'AI) restano com'erano: non
    sappiamo convertirle, e forzarle a grammi produrrebbe numeri falsi in lista.
    """
    unit = normalize_unit(unit)
    factor, base = _TO_BASE.get(unit, (None, None))
    if factor is None:
        return quantity, unit
    return quantity * factor, base


def format_quantity(quantity: float, unit: str) -> str:
    """Rende leggibile una quantità: 1500 g → "1,5 kg", 2.0 unità → "2 unità"."""
    if unit == "g" and quantity >= 1000:
        quantity, unit = quantity / 1000, "kg"
    elif unit == "ml" and quantity >= 1000:
        quantity, unit = quantity / 1000, "l"

    if abs(quantity - round(quantity)) < 0.05:
        num = str(int(round(quantity)))
    else:
        num = f"{quantity:.1f}".replace(".", ",")
    return f"{num} {unit}"


def price_for(quantity: float, unit: str, avg_price: float | None, price_unit: str | None):
    """Stima il costo di una quantità dato il prezzo medio per kg / l / unità.

    Restituisce None quando manca il prezzo o l'unità non è confrontabile (es. un
    prezzo al kg per un ingrediente contato a unità): meglio nessuna stima che una
    stima inventata.
    """
    if avg_price is None or not price_unit:
        return None

    base_qty, base_unit = to_base(quantity, unit)
    price_unit = normalize_unit(price_unit)

    if price_unit == "kg" and base_unit == "g":
        return round(base_qty / 1000 * avg_price, 2)
    if price_unit == "l" and base_unit == "ml":
        return round(base_qty / 1000 * avg_price, 2)
    if price_unit == "unità" and base_unit == "unità":
        return round(base_qty * avg_price, 2)
    if price_unit == base_unit:
        return round(base_qty * avg_price, 2)
    return None
