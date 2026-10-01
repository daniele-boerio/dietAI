"""Popolamento iniziale: utente, anagrafica ingredienti, preferenze e ingredienti base.

Si lancia una volta dopo le migrazioni:

    python -m app.seed

È idempotente: rilanciarlo aggiorna l'anagrafica senza toccare l'utente esistente.
"""

import logging
import sys

from .config import SEED_USER_EMAIL, SEED_USER_PASSWORD
from .database import SessionLocal
from .models import Ingredient, User
from .services.macros import apply_catalog_composition
from .services.accounts import admin_user, create_user
from .utils.pricing import INGREDIENT_CATALOG, guess_category
from .utils.seasonality import season_months_for

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")


def seed_ingredients(db) -> tuple[int, int]:
    """Inserisce (o aggiorna) l'anagrafica dal catalogo."""
    created = updated = 0
    for name, (category, price, price_unit) in INGREDIENT_CATALOG.items():
        ingredient = db.query(Ingredient).filter(Ingredient.name == name).first()
        if ingredient:
            # Il reparto spostato a mano dalla lista della spesa vince sul catalogo:
            # il seed gira a ogni avvio del container, e senza questo controllo gli
            # spaghetti tornerebbero in "altro" al primo deploy.
            if not ingredient.category_by_user:
                ingredient.category = category
            # Stessa cosa per il prezzo: quello segnato allo scaffale è vero, quello
            # del catalogo è una media nazionale. Vince il primo.
            if not ingredient.price_by_user:
                ingredient.avg_price_per_unit = price
                ingredient.price_unit = price_unit
            ingredient.season_months = season_months_for(name)
            # La composizione corretta a mano non si tocca, come il reparto e il prezzo.
            apply_catalog_composition(ingredient)
            updated += 1
        else:
            ingredient = Ingredient(
                name=name,
                category=category,
                avg_price_per_unit=price,
                price_unit=price_unit,
                season_months=season_months_for(name),
            )
            apply_catalog_composition(ingredient)
            db.add(ingredient)
            created += 1
    db.commit()
    return created, updated


def reguess_categories(db) -> int:
    """Rifà il reparto indovinato delle righe che il catalogo non conosce.

    Quelle righe hanno il reparto che `guess_category` ha dato loro il giorno in cui
    il modello ha scritto il nome per la prima volta, e quando la stima migliora (la
    ricerca in mezzo alle parole metteva i "peperoni friggitelli" fra i condimenti)
    le righe vecchie restano sbagliate per sempre. Il reparto spostato a mano non si
    tocca: quello non è una stima.
    """
    changed = 0
    rows = (
        db.query(Ingredient)
        .filter(Ingredient.name.notin_(list(INGREDIENT_CATALOG)))
        .filter(Ingredient.category_by_user.is_(False))
        .all()
    )
    for ingredient in rows:
        guess = guess_category(ingredient.name)
        if ingredient.category != guess:
            ingredient.category = guess
            changed += 1
    db.commit()
    return changed


def seed_user(db) -> User | None:
    """Crea l'amministratore dell'app, se non esiste già.

    Gli altri account non nascono da qui: li crea l'amministratore da Impostazioni →
    Utenti. Il seed gira a ogni avvio del container e ricreerebbe ogni volta chi è
    stato cancellato apposta.
    """
    email = SEED_USER_EMAIL.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        # Un database nato prima dei due account non ha nessun amministratore (la
        # migrazione lo segna, ma le tabelle create da SQLAlchemy — i test, uno
        # sviluppo locale ripartito da zero — no): senza questa riga sparirebbero la
        # schermata della API key e la scelta dei modelli, a chi la chiave la paga.
        if not admin_user(db):
            existing.is_admin = True
            db.commit()
            logger.info("Utente %s promosso ad amministratore.", email)
        logger.info("Utente %s già presente (id %s).", email, existing.id)
        return existing

    if not SEED_USER_PASSWORD:
        logger.error(
            "SEED_USER_PASSWORD non impostata: non creo l'utente. "
            "Aggiungila in backend/.env e rilancia."
        )
        return None

    user = create_user(db, email, SEED_USER_PASSWORD, is_admin=True)
    db.commit()
    logger.info("Amministratore %s creato (id %s).", email, user.id)
    return user


def main() -> int:
    db = SessionLocal()
    try:
        created, updated = seed_ingredients(db)
        logger.info("Ingredienti: %s creati, %s aggiornati.", created, updated)
        logger.info("Reparti indovinati di nuovo: %s.", reguess_categories(db))
        user = seed_user(db)
        if not user:
            return 1
        logger.info("Seed completato. Ora puoi fare il login con %s.", user.email)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
