"""Promuove un account ad amministratore, dalla riga di comando.

    python -m app.make_admin
    python -m app.make_admin --email io@esempio.it

Amministratore vuol dire: la schermata della API key, la scelta dei modelli AI e il
pannello degli utenti. La migrazione `0015` segna chi c'era già (l'utente più vecchio),
e il seed promuove l'utente di `SEED_USER_EMAIL` quando in tabella non c'è nessun
amministratore — ma se il database è nato in un altro modo, o se il flag si è perso per
strada, di qui non si esce dalla UI: le rotte che lo darebbero sono proprio quelle
riservate all'amministratore. Questo comando è la via di rientro, come
`reset_password` lo è per la password.

Non serve riavviare niente: il flag si legge a ogni richiesta. Basta ricaricare la
pagina, che rilegge il profilo da `/api/auth/me`.
"""

import argparse
import logging
import sys

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import User
from .reset_password import pick_user

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("make-admin")


def make_admin(db: Session, email: str | None = None) -> User:
    """Alza `is_admin` sull'utente indicato (o sull'unico che c'è)."""
    user = pick_user(db, email)
    if user.is_admin:
        logger.info("%s era già amministratore.", user.email)
        return user

    user.is_admin = True
    db.commit()
    return user


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.make_admin",
        description="Rende un account amministratore dell'app.",
    )
    parser.add_argument("--email", help="quale utente, se ce n'è più di uno")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # L'email si legge **dentro** la sessione. Dopo la commit gli attributi sono
        # scaduti e dopo la close l'istanza è staccata: leggerla più in basso
        # solleverebbe DetachedInstanceError a lavoro già fatto, cioè un traceback
        # che fa credere fallito un comando riuscito.
        email = make_admin(db, args.email).email
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    finally:
        db.close()

    logger.info("%s è amministratore.", email)
    logger.info("Ricarica la pagina: il profilo si rilegge a ogni caricamento.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
