"""Riporta nel target le ricette in programma: `python -m app.refit_macros`.

Ritocca le grammature delle ricette da oggi in avanti (non segnate, non saltate) che
stanno fuori dal ±10% del loro pasto, con lo stesso calcolo della generazione e senza
chiamare il modello. Vedi `services/refit.py` per i confini. Senza `--yes` stampa solo
cosa farebbe; `--email` lo limita a un account.
"""

import argparse
import logging

from .database import SessionLocal
from .models import Ingredient, User
from .services import planner
from .services.refit import refit_future_meals

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("refit")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ritocca le ricette fuori target.")
    parser.add_argument("--yes", action="store_true", help="salva davvero")
    parser.add_argument("--email", help="solo questo account")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user_id = None
        if args.email:
            user = db.query(User).filter(User.email == args.email.lower().strip()).first()
            if not user:
                logger.error("Nessun account con email %s", args.email)
                return
            user_id = user.id

        esito = refit_future_meals(db, planner.today(), user_id=user_id, apply=args.yes)
        logger.info(
            "%s %s ricette fuori target, %s già nel target.",
            "Ritoccate" if args.yes else "Da ritoccare:",
            len(esito.ritoccate),
            esito.gia_dentro,
        )
        for r in esito.ritoccate:
            logger.info(
                "  · %s (%s caselle): %s → %s kcal, target %s",
                r["title"], r["caselle"], r["kcal_prima"], r["kcal_dopo"], r["target"],
            )
            for ing_id, prima, dopo, unit in r["modifiche"]:
                nome = db.get(Ingredient, ing_id).name
                logger.info("      %s: %g → %g %s", nome, prima, dopo, unit)
        if esito.fuori_portata:
            logger.info(
                "Fuori portata anche ritoccando (vanno rigenerate): %s",
                ", ".join(esito.fuori_portata),
            )
        if esito.non_calcolabili:
            logger.info(
                "Con un ingrediente senza valori nutrizionali (saltate): %s",
                ", ".join(esito.non_calcolabili),
            )
        if not args.yes:
            logger.info("\nNiente è stato toccato. Rilancia con --yes per salvare.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
