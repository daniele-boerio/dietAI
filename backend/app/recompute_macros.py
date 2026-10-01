"""Ricalcola i macro delle ricette già in archivio: `python -m app.recompute_macros`.

Le ricette nate prima che i macro si calcolassero dagli ingredienti portano i numeri
che aveva dichiarato il modello (`nutrition_source` NULL). Questo comando li rifà con
la composizione dell'anagrafica, **senza toccare le grammature**: il ritocco verso il
target vale per le ricette che nascono, non per quelle già cucinate — cambierebbe a
posteriori quello che l'utente ha comprato e mangiato.

I numeri nuovi cambiano anche i totali delle settimane passate e l'aderenza: è voluto,
dicono il vero. Per questo non gira da solo all'avvio come il seed, e senza `--yes`
stampa soltanto quanto cambierebbe.
"""

import argparse
import logging

from .database import SessionLocal
from .models import Recipe, RecipeIngredient
from .services import macros
from .services.recipes import recompute_nutrition

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("macro")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ricalcola i macro delle ricette.")
    parser.add_argument(
        "--yes", action="store_true", help="salva davvero (senza, stampa solo cosa farebbe)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        cambiate, invariate, non_calcolabili = [], 0, 0
        for recipe in db.query(Recipe).filter(Recipe.is_custom.is_(False)).all():
            items = [
                {"ingredient_id": ri.ingredient_id, "quantity": ri.quantity, "unit": ri.unit}
                for ri in db.query(RecipeIngredient).filter_by(recipe_id=recipe.id)
            ]
            calcolati = macros.compute(db, items)
            if calcolati is None:
                non_calcolabili += 1
                continue
            nuove = calcolati.as_nutrition()["calories"]
            if nuove == recipe.calories:
                invariate += 1
            else:
                cambiate.append((recipe.title, recipe.calories, nuove))
            if args.yes:
                recompute_nutrition(db, recipe)

        logger.info(
            "%s ricette da ricalcolare, %s già giuste, %s con un ingrediente senza "
            "composizione (restano coi numeri dichiarati).",
            len(cambiate), invariate, non_calcolabili,
        )
        for titolo, prima, dopo in sorted(cambiate, key=lambda c: -abs(c[2] - c[1]))[:30]:
            logger.info("  · %s: %s → %s kcal", titolo, prima, dopo)

        if args.yes:
            db.commit()
            logger.info("Salvato.")
        else:
            logger.info("\nNiente è stato toccato. Rilancia con --yes per salvare.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
