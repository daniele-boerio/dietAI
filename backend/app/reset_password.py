"""Reset della password dalla riga di comando.

    python -m app.reset_password 'nuova-password-lunga'
    python -m app.reset_password 'nuova-password' --email altro@utente.it

Serve quando la password si è persa: l'app non ha recupero via email (niente SMTP,
niente endpoint pubblici non autenticati), e in un'app self-hosted da un utente solo
poter entrare nel container È già la prova d'identità.

Non cancellare mai la riga dell'utente per farla ricreare dal seed: le foreign key
sono in CASCADE e si porterebbero via dieta, ricette, settimane e lista della spesa.
"""

import argparse
import logging
import sys

from sqlalchemy.orm import Session

from .auth import get_password_hash, revoke_all_sessions
from .config import SEED_USER_EMAIL
from .database import SessionLocal
from .models import User

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reset-password")

MIN_LENGTH = 8


def pick_user(db: Session, email: str | None) -> User:
    """Trova l'utente da modificare.

    Con un solo utente in tabella non serve specificare niente: è il caso normale.
    """
    if email:
        user = db.query(User).filter(User.email == email.lower().strip()).first()
        if not user:
            raise ValueError(f"Nessun utente con email {email}.")
        return user

    users = db.query(User).order_by(User.id).all()
    if not users:
        raise ValueError("Nessun utente nel database: lancia prima `python -m app.seed`.")
    if len(users) == 1:
        return users[0]

    seeded = next((u for u in users if u.email == SEED_USER_EMAIL.lower().strip()), None)
    if seeded:
        return seeded
    raise ValueError(
        "Ci sono più utenti: indica quale con --email ("
        + ", ".join(u.email for u in users)
        + ")."
    )


def reset_password(db: Session, new_password: str, email: str | None = None) -> User:
    if len(new_password) < MIN_LENGTH:
        raise ValueError(f"La password deve essere di almeno {MIN_LENGTH} caratteri.")

    user = pick_user(db, email)
    user.password_hash = get_password_hash(new_password)
    # Come nel cambio password dalla UI: chi aveva una sessione aperta con la vecchia
    # password viene buttato fuori subito, non alla scadenza del token.
    user.token_version += 1
    revoke_all_sessions(db, user.id)
    db.commit()
    return user


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.reset_password",
        description="Imposta una nuova password per l'utente dell'app.",
    )
    parser.add_argument("password", help="la nuova password (almeno 8 caratteri)")
    parser.add_argument("--email", help="quale utente, se ce n'è più di uno")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = reset_password(db, args.password, args.email)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    finally:
        db.close()

    logger.info("Password di %s aggiornata.", user.email)
    logger.info("Tutte le sessioni aperte sono state revocate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
