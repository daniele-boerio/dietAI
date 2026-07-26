"""Riallinea l'anagrafica alla normalizzazione di oggi: `python -m app.merge_ingredients`.

Da lanciare quando cambia l'elenco dei qualificatori in `services/ingredients.py`. Le
righe già in tabella restano scritte come erano — "pesce spada surgelato" accanto a
"pesce spada" — e finché restano sono due alimenti diversi per il database: la
dispensa non copre la ricetta, la lista della spesa fa due righe.

Non gira da solo all'avvio come il seed: fonde righe e ne cancella, quindi è giusto
che lo lanci una persona che poi ne legge il resoconto.
"""

import logging

from .database import SessionLocal
from .services.ingredients import merge_duplicates

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("merge")


def main() -> None:
    db = SessionLocal()
    try:
        fusi = merge_duplicates(db)
    finally:
        db.close()

    if not fusi:
        logger.info("Anagrafica già allineata: niente da fondere.")
        return

    logger.info("Fusi %s gruppi di doppioni:", len(fusi))
    for nome, doppioni in fusi:
        logger.info("  · %s ← %s", nome, ", ".join(doppioni))


if __name__ == "__main__":
    main()
