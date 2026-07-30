"""Calorie e macro a partire da un questionario, per chi non ha una dieta scritta.

Serve a un caso preciso: l'utente non è mai stato da un nutrizionista e non ha nessun
PDF da caricare, ma i pasti vanno comunque targettati — senza i numeri della dieta il
resto dell'app non ha niente su cui lavorare.

Il conto lo fa una formula, non il modello. **Mifflin-St Jeor** è lo standard clinico
per il metabolismo basale, si scrive in dieci righe ed è gratis, istantaneo e
riproducibile: chiedere gli stessi numeri a un modello linguistico costerebbe una
chiamata, darebbe risposte diverse a parità di risposte e andrebbe comunque validato.
E soprattutto: i numeri che escono da qui **restano correggibili a mano** da "La mia
dieta", esattamente come quelli letti da un PDF. Questa non è una prescrizione medica,
è un punto di partenza ragionevole — la UI lo dice.

Il percorso: BMR (Mifflin-St Jeor) → × fattore di attività = fabbisogno giornaliero →
± obiettivo = calorie target → proteine sul peso, grassi in percentuale, carboidrati
per differenza → divisione tra i pasti.
"""

# Fattori LAF (livello di attività fisica) di uso corrente. Le etichette sono quelle
# che legge l'utente: la domanda "quanto ti muovi" va posta in italiano, non in numeri.
ACTIVITY_LEVELS = {
    "sedentario": (1.2, "Lavoro da seduto, niente sport"),
    "leggero": (1.375, "Sport leggero 1-3 volte a settimana"),
    "moderato": (1.55, "Sport 3-5 volte a settimana"),
    "intenso": (1.725, "Sport intenso 6-7 volte a settimana"),
    "atleta": (1.9, "Lavoro fisico o due allenamenti al giorno"),
}

# Scostamento dal fabbisogno. In percentuale e non in calorie fisse: -500 kcal su un
# fabbisogno di 3000 è un taglio ragionevole, sullo stesso numero a 1600 è fame.
GOALS = {
    "dimagrire": (-0.15, "Perdere peso gradualmente"),
    "mantenere": (0.0, "Restare come sono"),
    "aumentare": (0.10, "Mettere massa"),
}

SEXES = ("uomo", "donna")

# Proteine in grammi per chilo di peso: più alte quando si taglia (proteggono la massa
# magra mentre si è in deficit), medie in mantenimento.
_PROTEIN_PER_KG = {"dimagrire": 2.0, "mantenere": 1.6, "aumentare": 1.8}

# Quota di calorie dai grassi. Sotto il 20% si fa fatica con gli ormoni e coi cibi
# veri (un filo d'olio ci sta sempre): il resto va ai carboidrati.
_FAT_SHARE = 0.27

# Le proteine non possono prendersi mezza giornata: su calorie basse e peso alto il
# conto in g/kg sfonderebbe, lasciando carboidrati negativi.
_MAX_PROTEIN_SHARE = 0.40

# Pavimento di sicurezza. Sotto queste soglie non si scende comunque: una dieta la
# scrive un medico, questo è un calcolo automatico e deve restare prudente.
_MIN_CALORIES = {"uomo": 1500, "donna": 1200}

KCAL_PER_G = {"protein_g": 4.0, "carbs_g": 4.0, "fat_g": 9.0}

# Come si divide la giornata, per numero di pasti. I nomi sono quelli che l'utente si
# ritrova nella griglia della settimana, quindi vanno scritti come si dicono.
_MEAL_SPLITS = {
    3: [("Colazione", 0.25), ("Pranzo", 0.40), ("Cena", 0.35)],
    4: [
        ("Colazione", 0.22),
        ("Pranzo", 0.35),
        ("Spuntino pomeriggio", 0.13),
        ("Cena", 0.30),
    ],
    5: [
        ("Colazione", 0.20),
        ("Spuntino mattina", 0.10),
        ("Pranzo", 0.32),
        ("Spuntino pomeriggio", 0.10),
        ("Cena", 0.28),
    ],
    6: [
        ("Colazione", 0.18),
        ("Spuntino mattina", 0.08),
        ("Pranzo", 0.30),
        ("Spuntino pomeriggio", 0.09),
        ("Cena", 0.27),
        ("Spuntino sera", 0.08),
    ],
}

MEAL_COUNTS = tuple(sorted(_MEAL_SPLITS))


def basal_metabolic_rate(sex: str, age: int, height_cm: float, weight_kg: float) -> float:
    """Mifflin-St Jeor: le calorie che si bruciano stando fermi."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex == "uomo" else -161)


def _share_out(total: float, weights: list[float], decimals: int) -> list[float]:
    """Divide `total` secondo i pesi, e fa tornare la somma esatta.

    Arrotondando ogni quota per conto suo il totale finisce quasi sempre a ±1 da quello
    voluto, ed è proprio il numero che non deve muoversi: il resto va sulla quota più
    grande, dove si nota meno. Stessa regola di `lib/macros.js` lato frontend — chi
    aggiunge o toglie un pasto dall'editor si aspetta la stessa aritmetica.
    """
    weight_sum = sum(weights) or 1.0
    shares = [round(total * w / weight_sum, decimals) for w in weights]
    drift = round(total - sum(shares), decimals)
    if drift and shares:
        biggest = shares.index(max(shares))
        shares[biggest] = round(shares[biggest] + drift, decimals)
    return [int(v) if decimals == 0 else v for v in shares]


def compute_plan(
    *,
    sex: str,
    age: int,
    height_cm: float,
    weight_kg: float,
    activity: str,
    goal: str,
    meals_count: int = 4,
) -> dict:
    """Il piano completo: totali del giorno, come ci si è arrivati, e i pasti.

    Il "come ci si è arrivati" (bmr, tdee) non è decorazione: sono le due cifre che
    permettono all'utente di capire se il risultato ha senso prima di fidarsene.
    """
    if sex not in SEXES:
        raise ValueError(f"Sesso non valido: {sex!r}")
    if activity not in ACTIVITY_LEVELS:
        raise ValueError(f"Livello di attività non valido: {activity!r}")
    if goal not in GOALS:
        raise ValueError(f"Obiettivo non valido: {goal!r}")
    if meals_count not in _MEAL_SPLITS:
        raise ValueError(f"Numero di pasti non gestito: {meals_count!r}")

    bmr = basal_metabolic_rate(sex, age, height_cm, weight_kg)
    tdee = bmr * ACTIVITY_LEVELS[activity][0]
    target = tdee * (1 + GOALS[goal][0])

    # Il taglio non porta mai sotto il metabolismo basale né sotto il minimo di
    # sicurezza: sono i due modi in cui un calcolo automatico può fare danno.
    calories = int(round(max(target, bmr, _MIN_CALORIES[sex])))

    protein_g = round(min(
        _PROTEIN_PER_KG[goal] * weight_kg,
        calories * _MAX_PROTEIN_SHARE / KCAL_PER_G["protein_g"],
    ), 1)
    fat_g = round(calories * _FAT_SHARE / KCAL_PER_G["fat_g"], 1)
    carbs_kcal = calories - protein_g * KCAL_PER_G["protein_g"] - fat_g * KCAL_PER_G["fat_g"]
    carbs_g = round(max(carbs_kcal, 0) / KCAL_PER_G["carbs_g"], 1)

    split = _MEAL_SPLITS[meals_count]
    weights = [share for _, share in split]
    shares = {
        "calories": _share_out(calories, weights, 0),
        "protein_g": _share_out(protein_g, weights, 1),
        "carbs_g": _share_out(carbs_g, weights, 1),
        "fat_g": _share_out(fat_g, weights, 1),
    }

    meals = [
        {
            "name": name,
            "order": index,
            "calories": shares["calories"][index],
            "protein_g": shares["protein_g"][index],
            "carbs_g": shares["carbs_g"][index],
            "fat_g": shares["fat_g"][index],
            "notes": None,
            "auto_generate": True,
        }
        for index, (name, _) in enumerate(split)
    ]

    return {
        "bmr": int(round(bmr)),
        "tdee": int(round(tdee)),
        "daily_calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "meals": meals,
    }


def options() -> dict:
    """Le scelte possibili, con le etichette: la UI le disegna senza duplicarle."""
    return {
        "sexes": list(SEXES),
        "activity_levels": [
            {"key": key, "label": key.capitalize(), "hint": hint}
            for key, (_, hint) in ACTIVITY_LEVELS.items()
        ],
        "goals": [
            {"key": key, "label": key.capitalize(), "hint": hint}
            for key, (_, hint) in GOALS.items()
        ],
        "meal_counts": list(MEAL_COUNTS),
    }
