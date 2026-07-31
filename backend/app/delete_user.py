"""Cancella un account e tutto quello che contiene, dalla riga di comando.

    python -m app.delete_user --email tizio@esempio.it          # dice solo cosa sparirebbe
    python -m app.delete_user --email tizio@esempio.it --yes    # lo fa davvero

Serve per gli account che il pannello Utenti non tocca: gli **altri amministratori**.
Da lì non si possono cancellare di proposito — è la stessa mano che potrebbe chiudersi
fuori dalla propria app — quindi la porta è qui, dove per arrivarci bisogna già essere
dentro al container.

Senza `--yes` non scrive niente: stampa l'inventario di cosa verrebbe portato via e si
ferma. Le foreign key sono in CASCADE, quindi "cancellare l'utente" vuol dire
cancellare dieta, ricette, settimane, dispensa e liste della spesa, e non si torna
indietro. Se serve solo togliere l'accesso, la sospensione dal pannello Utenti lascia
tutto al suo posto.
"""

import argparse
import logging
import sys

from sqlalchemy.orm import Session

from .config import SEED_USER_EMAIL
from .database import SessionLocal
from .models import (
    BaseIngredient,
    DietPlan,
    ExcludedIngredient,
    PantryItem,
    Recipe,
    RefreshToken,
    User,
    WeekPlan,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("delete-user")


def inventory(db: Session, user: User) -> dict[str, int]:
    """Cosa se ne va insieme all'account. Si stampa prima, non dopo."""
    return {
        "diete": db.query(DietPlan).filter(DietPlan.user_id == user.id).count(),
        "ricette": db.query(Recipe).filter(Recipe.user_id == user.id).count(),
        "settimane pianificate": db.query(WeekPlan)
        .filter(WeekPlan.user_id == user.id)
        .count(),
        "voci in dispensa": db.query(PantryItem)
        .filter(PantryItem.user_id == user.id)
        .count(),
        "ingredienti di base": db.query(BaseIngredient)
        .filter(BaseIngredient.user_id == user.id)
        .count(),
        "alimenti esclusi": db.query(ExcludedIngredient)
        .filter(ExcludedIngredient.user_id == user.id)
        .count(),
        "sessioni aperte": db.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id)
        .count(),
    }


def pick_target(db: Session, email: str) -> User:
    """L'utente da cancellare, con i due rifiuti che valgono sempre."""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        esistenti = ", ".join(u.email for u in db.query(User).order_by(User.id))
        raise ValueError(f"Nessun utente con email {email}. Ci sono: {esistenti or '—'}.")

    if db.query(User).count() == 1:
        raise ValueError(
            "È l'unico account rimasto: cancellarlo lascerebbe l'app senza nessuno "
            "che possa entrarci."
        )

    if user.is_admin and db.query(User).filter(User.is_admin.is_(True)).count() == 1:
        raise ValueError(
            "È l'unico amministratore: senza, la API key e il pannello Utenti "
            "diventano irraggiungibili. Prima promuovi l'altro account con "
            "`python -m app.make_admin --email ...`."
        )

    return user


def delete_user(db: Session, email: str, force_seed: bool = False) -> str:
    """Cancella l'account. Restituisce l'email, letta finché la sessione è aperta."""
    user = pick_target(db, email)

    # Il seed gira a **ogni avvio del container**: se questa è l'email da cui nasce
    # l'utente dell'app, cancellarla adesso vuol dire ritrovarsela al prossimo deploy,
    # identica e di nuovo amministratrice. Il rimedio non è qui, è nelle variabili di
    # Coolify — e va fatto prima, o si ricomincia da capo.
    if user.email == SEED_USER_EMAIL.lower().strip() and not force_seed:
        raise ValueError(
            f"{user.email} è l'utente del seed (SEED_USER_EMAIL), che viene ricreato a "
            "ogni avvio del container. Cambia prima quella variabile su Coolify "
            "mettendoci l'account che vuoi tenere, poi rilancia. "
            "Se sai quello che fai, aggiungi --force-seed."
        )

    nome = user.email
    db.delete(user)
    db.commit()
    return nome


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.delete_user",
        description="Cancella un account e tutti i suoi dati.",
    )
    parser.add_argument("--email", required=True, help="quale account cancellare")
    parser.add_argument(
        "--yes", action="store_true", help="conferma: senza, mostra solo cosa sparirebbe"
    )
    parser.add_argument(
        "--force-seed",
        action="store_true",
        help="cancella anche se è l'utente di SEED_USER_EMAIL (tornerà al riavvio)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.yes:
            user = pick_target(db, args.email)
            logger.info("Cancellando %s spariscono per sempre:", user.email)
            for etichetta, quante in inventory(db, user).items():
                logger.info("  · %-22s %s", etichetta, quante)
            logger.info("")
            logger.info("Non si torna indietro. Per farlo davvero, rilancia con --yes.")
            logger.info(
                "Se ti basta togliere l'accesso, sospendilo da Impostazioni → Utenti: "
                "i dati restano."
            )
            return 0

        email = delete_user(db, args.email, args.force_seed)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    finally:
        db.close()

    logger.info("%s cancellato, con tutti i suoi dati.", email)
    return 0


if __name__ == "__main__":
    sys.exit(main())
