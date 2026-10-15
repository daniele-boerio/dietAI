"""Ricalcola i macro delle ricette già in archivio: `python -m app.recompute_macros`.

Le ricette nate prima che i macro si calcolassero dagli ingredienti portano i numeri
che aveva dichiarato il modello (`nutrition_source` NULL). Questo comando li rifà con
la composizione dell'anagrafica, **senza toccare le grammature**: il ritocco verso il
target vale per le ricette che nascono, non per quelle già cucinate — cambierebbe a
posteriori quello che l'utente ha comprato e mangiato.

Rifà anche gli altri valori (fibre, zuccheri, saturi, alcol, caffeina), che le ricette
di prima non hanno affatto. Il catalogo li porta già (li scrive il seed); i nomi che il
modello aveva imparato prima che glieli si chiedesse no: con `--ai` il modello li
completa, una chiamata ogni 40 nomi, con la chiave e il modello dell'amministratore.

I numeri nuovi cambiano anche i totali delle settimane passate e l'aderenza: è voluto,
dicono il vero. Per questo non gira da solo all'avvio come il seed, e senza `--yes`
stampa soltanto quanto cambierebbe.
"""

import argparse
import logging

from .database import SessionLocal
from .models import Recipe, RecipeIngredient
from .services import macros
from .services.accounts import admin_user
from .services.ai_client import get_client
from .services.recipes import recompute_nutrition

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("macro")

_NOMI_PER_CHIAMATA = 40


def _impara(db, recipes: list[Recipe]) -> int:
    """Il modello completa la composizione dei nomi che non ce l'hanno intera."""
    ids = sorted({
        ri.ingredient_id
        for r in recipes
        for ri in db.query(RecipeIngredient).filter_by(recipe_id=r.id)
    })
    mancanti = [i.id for i in macros.missing_composition(db, ids)]
    if not mancanti:
        logger.info("Ogni ingrediente in archivio ha già tutti i valori.")
        return 0
    admin = admin_user(db)
    if admin is None:
        logger.info("Nessun amministratore: senza la sua chiave non si chiede niente al modello.")
        return 0
    client = get_client(db, admin, "planning")
    imparati = 0
    for i in range(0, len(mancanti), _NOMI_PER_CHIAMATA):
        imparati += macros.ensure_composition(db, client, mancanti[i : i + _NOMI_PER_CHIAMATA])
        db.commit()  # quello che ha imparato resta, anche se la chiamata dopo fallisce
    logger.info("Il modello ha completato %s ingredienti su %s.", imparati, len(mancanti))
    return imparati


def main() -> None:
    parser = argparse.ArgumentParser(description="Ricalcola i macro delle ricette.")
    parser.add_argument(
        "--yes", action="store_true", help="salva davvero (senza, stampa solo cosa farebbe)"
    )
    parser.add_argument(
        "--ai", action="store_true",
        help="chiedi al modello i valori che mancano all'anagrafica (con --yes)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        ricette = db.query(Recipe).filter(Recipe.is_custom.is_(False)).all()
        if args.ai and args.yes:
            _impara(db, ricette)

        cambiate, invariate, non_calcolabili, senza_dettagli = [], 0, 0, 0
        for recipe in ricette:
            items = [
                {"ingredient_id": ri.ingredient_id, "quantity": ri.quantity, "unit": ri.unit}
                for ri in db.query(RecipeIngredient).filter_by(recipe_id=recipe.id)
            ]
            calcolati = macros.compute(db, items)
            if calcolati is None:
                non_calcolabili += 1
                continue
            n = calcolati.as_nutrition()
            if any(n[c] is None for c in macros.CAMPI_DETTAGLIO):
                senza_dettagli += 1
            nuovi_dettagli = any(
                n[c] is not None and n[c] != getattr(recipe, c) for c in macros.CAMPI_DETTAGLIO
            )
            if n["calories"] == recipe.calories and not nuovi_dettagli:
                invariate += 1
            else:
                cambiate.append((recipe.title, recipe.calories, n["calories"]))
            if args.yes:
                recompute_nutrition(db, recipe)

        logger.info(
            "%s ricette da ricalcolare, %s già giuste, %s con un ingrediente senza "
            "composizione (restano coi numeri dichiarati).",
            len(cambiate), invariate, non_calcolabili,
        )
        if senza_dettagli:
            logger.info(
                "%s ricette hanno un ingrediente senza fibre, zuccheri o il resto: quei "
                "valori restano aperti.%s",
                senza_dettagli,
                "" if args.ai else " Con --ai --yes il modello li completa.",
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
