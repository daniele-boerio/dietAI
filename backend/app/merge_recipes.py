"""Fonde le ricette doppie del ricettario: `python -m app.merge_recipes`.

Da lanciare una volta, sull'archivio che si è gonfiato prima che `create_recipe`
imparasse a riconoscere un gemello: allora ogni casella del piano si portava dietro la
sua riga di ricetta, quindi lo stesso piatto aveva una riga per giorno in cui era in
programma — e i pasti ricorrenti una per settimana.

Non gira da solo all'avvio come il seed: cancella righe, quindi è giusto che lo lanci
una persona che poi ne legge il resoconto. Senza `--yes` non tocca niente e si limita a
dire cosa fonderebbe.
"""

import argparse
import logging

from .database import SessionLocal
from .services.recipes import duplicate_groups, merge_duplicate_recipes

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("merge")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fonde le ricette identiche.")
    parser.add_argument(
        "--yes", action="store_true", help="fondi davvero (senza, stampa solo cosa farebbe)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.yes:
            gruppi = merge_duplicate_recipes(db)
        else:
            gruppi = [(rows[0].title, len(rows) - 1) for rows in duplicate_groups(db)]

        if not gruppi:
            logger.info("Nessuna ricetta doppia: il ricettario è già pulito.")
            return

        totale = sum(quante for _, quante in gruppi)
        logger.info(
            "%s %s righe in %s piatti:",
            "Fuse" if args.yes else "Da fondere:",
            totale,
            len(gruppi),
        )
        for titolo, quante in sorted(gruppi, key=lambda g: -g[1]):
            logger.info("  · %s ← %s doppioni", titolo, quante)

        if not args.yes:
            logger.info("\nNiente è stato toccato. Rilancia con --yes per fondere davvero.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
