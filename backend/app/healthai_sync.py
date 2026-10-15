"""Rimanda a healthAI i pasti consumati di un periodo: `python -m app.healthai_sync`.

Il giro di ogni minuto manda solo quello che è cambiato. Questo comando serve al primo
collegamento, o dopo un periodo in cui healthAI ha perso i dati: rimanda tutto quello
che c'è da mandare negli ultimi `--days` giorni (90 di default), anche quello che
risulterebbe già inviato, e toglie quello che non dovrebbe esserci. L'upsert di
healthAI su `external_meal_id` fa sì che non nascano doppioni.

Senza `--yes` dice soltanto quanti pasti manderebbe.
"""

import argparse
import logging
from datetime import datetime, timezone

from . import config
from .database import SessionLocal
from .services import healthai
from .services.accounts import admin_user

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("healthai")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rimanda i pasti consumati a healthAI.")
    parser.add_argument("--days", type=int, default=config.HEALTHAI_DAYS, help="quanti giorni indietro")
    parser.add_argument("--yes", action="store_true", help="manda davvero (senza, conta soltanto)")
    args = parser.parse_args()

    if not healthai.enabled():
        logger.info("HEALTHAI_URL o HEALTHAI_TOKEN mancano: l'integrazione è spenta.")
        return

    db = SessionLocal()
    try:
        admin = admin_user(db)
        if admin is None:
            logger.info("Nessun amministratore: non c'è niente da mandare.")
            return
        ora = datetime.now(timezone.utc)
        desiderati = healthai.desired_payloads(
            db, admin.id, healthai._oggi_italiano(ora), args.days
        )
        consumati = sum(1 for p in desiderati.values() if p is not None)
        logger.info("%s pasti consumati negli ultimi %s giorni.", consumati, args.days)
        if not args.yes:
            logger.info("Niente è stato mandato. Rilancia con --yes per mandarli.")
            return
        giro = healthai.sync(db, ora=ora, giorni=args.days, force=True)
        logger.info(
            "Inviati %s, tolti %s, falliti %s.%s",
            giro.inviati, giro.cancellati, giro.falliti,
            f" Fermato: {giro.fermato}." if giro.fermato else "",
        )
        for errore in giro.errori[:20]:
            logger.info("  · %s", errore)
    finally:
        db.close()


if __name__ == "__main__":
    main()
