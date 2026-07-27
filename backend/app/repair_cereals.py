"""Rimette a posto i cereali finiti dentro "pasta": `python -m app.repair_cereals`.

Serve a riparare un `merge_ingredients` girato con una normalizzazione troppo larga,
quella che faceva diventare "pasta" anche il riso, il cous cous, il farro e l'orzo. La
fusione cancella la riga di anagrafica e sposta le ricette su quella tenuta, quindi il
nome originale dell'ingrediente non c'è più da nessuna parte — ma **il testo della
ricetta sì**: il titolo e il procedimento continuano a dire "cous cous", perché nessuno
li ha riscritti.

Da lì si torna indietro: per ogni ricetta che punta a "pasta" ma parla di un altro
cereale, l'ingrediente viene ripuntato su quello giusto (ricreandone la riga di
anagrafica se serve). Dove il testo non basta a decidere — nessun cereale nominato,
oppure due — non si tira a indovinare: la ricetta finisce nell'elenco di quelle da
guardare a mano.

Quello che questo script **non** può ricostruire è la dispensa: se una scorta di riso
è stata sommata a una di pasta, quel numero è uno solo e non si sa più com'era diviso.
La lista della spesa invece si rifà da sé alla prima lettura, perché nasce dalle
ricette.
"""

import logging
import re

from .database import SessionLocal
from .models import Ingredient, Recipe, RecipeIngredient
from .services.ingredients import get_or_create_ingredient

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("repair")

# Cosa cercare nel testo della ricetta → come si chiama l'ingrediente da rimettere.
# "risotto" vale come "riso": è il piatto, ma l'ingrediente comprato è quello.
CEREALI: dict[str, str] = {
    r"cous\s*cous": "cous cous",
    r"risott[oi]|\briso\b": "riso",
    r"\bfarro\b": "farro",
    r"\borzo\b": "orzo",
    r"\bquinoa\b": "quinoa",
    r"\bmiglio\b": "miglio",
    r"\bgnocchi\b": "gnocchi",
    r"\bravioli\b": "ravioli",
    r"\btortellini\b": "tortellini",
    r"\bpolenta\b": "polenta",
}


def _cereale_citato(recipe: Recipe) -> list[str]:
    """I cereali nominati nel testo della ricetta, senza ripetizioni."""
    testo = " ".join(
        filter(None, [recipe.title, recipe.description, recipe.instructions])
    ).lower()
    trovati = []
    for pattern, nome in CEREALI.items():
        if re.search(pattern, testo) and nome not in trovati:
            trovati.append(nome)
    return trovati


def main() -> None:
    db = SessionLocal()
    try:
        pasta = db.query(Ingredient).filter(Ingredient.name == "pasta").first()
        if not pasta:
            logger.info('Nessuna riga "pasta" in anagrafica: niente da riparare.')
            return

        righe = (
            db.query(RecipeIngredient, Recipe)
            .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
            .filter(RecipeIngredient.ingredient_id == pasta.id)
            .all()
        )
        if not righe:
            logger.info('Nessuna ricetta punta a "pasta": niente da riparare.')
            return

        riparate: list[tuple[str, str]] = []
        da_guardare: list[tuple[str, list[str]]] = []

        for riga, recipe in righe:
            citati = _cereale_citato(recipe)
            if len(citati) == 1:
                riga.ingredient_id = get_or_create_ingredient(db, citati[0]).id
                riparate.append((recipe.title, citati[0]))
            elif citati:
                # Due cereali nel testo: potrebbe essere "riso o cous cous" come
                # alternativa, o una ricetta che li usa davvero entrambi. Sceglierne
                # uno a caso sarebbe peggio che lasciarlo decidere a chi cucina.
                da_guardare.append((recipe.title, citati))

        db.commit()

        if riparate:
            logger.info("Rimesse a posto %s ricette:", len(riparate))
            for titolo, cereale in riparate:
                logger.info("  · %s → %s", titolo, cereale)
        else:
            logger.info("Nessuna ricetta da rimettere a posto.")

        if da_guardare:
            logger.info("")
            logger.info("Da guardare a mano (più di un cereale nel testo):")
            for titolo, citati in da_guardare:
                logger.info("  · %s → %s", titolo, " / ".join(citati))

        rimaste = (
            db.query(RecipeIngredient)
            .filter(RecipeIngredient.ingredient_id == pasta.id)
            .count()
        )
        logger.info("")
        logger.info('Ricette che restano su "pasta": %s', rimaste)
        logger.info("La dispensa va ricontrollata a mano: le scorte fuse non si dividono.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
