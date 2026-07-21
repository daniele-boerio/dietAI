"""Popolamento iniziale: utente, anagrafica ingredienti, preferenze e ingredienti base.

Si lancia una volta dopo le migrazioni:

    python -m app.seed

È idempotente: rilanciarlo aggiorna l'anagrafica senza toccare l'utente esistente.
"""

import logging
import sys

from .auth import get_password_hash
from .config import SEED_USER_EMAIL, SEED_USER_PASSWORD
from .database import SessionLocal
from .models import BaseIngredient, Ingredient, User, UserPreferences
from .utils.pricing import DEFAULT_BASE_INGREDIENTS, INGREDIENT_CATALOG
from .utils.seasonality import season_months_for

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")


def seed_ingredients(db) -> tuple[int, int]:
    """Inserisce (o aggiorna) l'anagrafica dal catalogo."""
    created = updated = 0
    for name, (category, price, price_unit) in INGREDIENT_CATALOG.items():
        ingredient = db.query(Ingredient).filter(Ingredient.name == name).first()
        if ingredient:
            ingredient.category = category
            ingredient.avg_price_per_unit = price
            ingredient.price_unit = price_unit
            ingredient.season_months = season_months_for(name)
            updated += 1
        else:
            db.add(
                Ingredient(
                    name=name,
                    category=category,
                    avg_price_per_unit=price,
                    price_unit=price_unit,
                    season_months=season_months_for(name),
                )
            )
            created += 1
    db.commit()
    return created, updated


def seed_user(db) -> User | None:
    """Crea l'utente unico dell'app, se non esiste già."""
    email = SEED_USER_EMAIL.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        logger.info("Utente %s già presente (id %s).", email, existing.id)
        return existing

    if not SEED_USER_PASSWORD:
        logger.error(
            "SEED_USER_PASSWORD non impostata: non creo l'utente. "
            "Aggiungila in backend/.env e rilancia."
        )
        return None

    user = User(email=email, password_hash=get_password_hash(SEED_USER_PASSWORD))
    db.add(user)
    db.flush()

    db.add(UserPreferences(user_id=user.id, prefer_seasonal=True, prefer_italian=True))

    for name in DEFAULT_BASE_INGREDIENTS:
        ingredient = db.query(Ingredient).filter(Ingredient.name == name).first()
        if ingredient:
            db.add(BaseIngredient(user_id=user.id, ingredient_id=ingredient.id))

    db.commit()
    logger.info("Utente %s creato (id %s).", email, user.id)
    return user


def main() -> int:
    db = SessionLocal()
    try:
        created, updated = seed_ingredients(db)
        logger.info("Ingredienti: %s creati, %s aggiornati.", created, updated)
        user = seed_user(db)
        if not user:
            return 1
        logger.info("Seed completato. Ora puoi fare il login con %s.", user.email)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
