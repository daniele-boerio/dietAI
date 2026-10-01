"""Lo storico del peso e il momento in cui i target vanno ricalcolati.

I target di una dieta calcolata dal questionario dipendono dal peso (Mifflin-St Jeor,
proteine per chilo): sei chili dopo sono i target di un'altra persona. L'app non li
ricalcola da sola — cambierebbe la dieta sotto i piedi dell'utente, e la dieta di un
nutrizionista non si tocca proprio — ma quando il peso si è allontanato abbastanza lo
dice, con un pulsante che riapre il questionario già compilato col peso nuovo.
"""

from datetime import date

from sqlalchemy.orm import Session

from ..models import WeightEntry
from .planner import get_active_diet

# Quanto deve allontanarsi il peso perché valga la pena ricalcolare: 2 kg, o il 3%
# per chi ne pesa più di 67. Sotto, la differenza sui target è di poche decine di kcal
# — meno dello scarto fra due pesate a ore diverse.
SOGLIA_KG = 2.0
SOGLIA_PERC = 0.03


def upsert(db: Session, user_id: int, day: date, weight_kg: float) -> WeightEntry:
    entry = db.query(WeightEntry).filter_by(user_id=user_id, day=day).first()
    if entry:
        entry.weight_kg = weight_kg
    else:
        entry = WeightEntry(user_id=user_id, day=day, weight_kg=weight_kg)
        db.add(entry)
    db.flush()
    return entry


def history(db: Session, user_id: int) -> dict:
    """Le pesate in ordine di data, il peso dei target e se è ora di ricalcolarli."""
    entries = (
        db.query(WeightEntry)
        .filter(WeightEntry.user_id == user_id)
        .order_by(WeightEntry.day)
        .all()
    )
    diet = get_active_diet(db, user_id)
    data = diet.parsed_data if diet and isinstance(diet.parsed_data, dict) else {}
    profile = data.get("profile") if data.get("source") == "questionario" else None
    riferimento = float(profile["weight_kg"]) if profile and profile.get("weight_kg") else None

    suggerimento = None
    if riferimento and entries:
        ultimo = entries[-1].weight_kg
        delta = ultimo - riferimento
        if abs(delta) >= max(SOGLIA_KG, SOGLIA_PERC * riferimento):
            suggerimento = {
                "target_weight": riferimento,
                "latest_weight": ultimo,
                "delta": round(delta, 1),
            }

    return {
        "entries": [
            {"day": e.day.isoformat(), "weight_kg": e.weight_kg} for e in entries
        ],
        # Il peso con cui sono stati calcolati i target, se la dieta viene dal
        # questionario. Per la dieta di un nutrizionista non c'è: i suoi numeri non
        # dipendono da una formula che l'app conosce.
        "target_weight": riferimento,
        "recalc": suggerimento,
    }
