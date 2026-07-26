"""Normalizzazione dei nomi: due modi di scrivere la stessa cosa sono la stessa riga.

La linea di taglio: via tutto quello che dice **com'è messo** l'alimento
(conservazione, taglio, calibro), resta tutto quello che dice **cos'è**. Se salta,
saltano due cose insieme: la dispensa smette di coprire le ricette e la lista della
spesa fa due righe dello stesso alimento.
"""

import pytest

from app.models import Ingredient, PantryItem, RecipeIngredient
from app.services.ingredients import merge_duplicates, normalize_name


@pytest.mark.parametrize(
    "scritto,atteso",
    [
        # Conservazione: lo stesso pesce, comprato in due banchi diversi.
        ("pesce spada surgelato", "pesce spada"),
        ("pesce spada fresco", "pesce spada"),
        ("Pesce Spada", "pesce spada"),
        ("piselli surgelati", "piselli"),
        ("mandorle sgusciate", "mandorle"),
        # Taglio e formato: cambia come te lo danno, non cosa compri.
        ("mandorle a lamelle", "mandorle"),
        ("parmigiano grattugiato", "parmigiano"),
        ("peperoni a listarelle", "peperoni"),
        ("petto di pollo a fettine", "petto di pollo"),
        ("aglio a spicchi", "aglio"),
        # Calibro e qualità.
        ("zucchine medie", "zucchine"),
        ("pomodori bio", "pomodori"),
    ],
)
def test_i_qualificatori_spariscono(scritto, atteso):
    assert normalize_name(scritto) == atteso


@pytest.mark.parametrize(
    "scritto",
    [
        # Queste parole cambiano i numeri della dieta: togliendole si farebbe passare
        # uno yogurt intero per uno magro, e i macro sono il vincolo più duro dell'app.
        "yogurt greco magro",
        "latte intero",
        "pasta integrale",
        "tonno al naturale",
        "cioccolato fondente",
        # "Pelati" non è lo stato dei pomodori: è una conserva, un altro prodotto.
        "pomodori pelati",
    ],
)
def test_quello_che_cambia_l_alimento_resta(scritto):
    assert normalize_name(scritto) == scritto


def test_un_nome_fatto_solo_di_rumore_non_resta_in_piedi():
    """Meglio niente che una riga chiamata "a fette": chi la chiama solleva ValueError."""
    assert normalize_name("q.b.") == ""
    assert normalize_name("a fette") == ""


# ── Riallineamento delle righe già in tabella ──────────────────────────────────


def test_le_righe_vecchie_si_fondono_su_quella_giusta(client, db):
    """Il caso vero: in dispensa c'è "pesce spada surgelato" da prima che la
    normalizzazione lo riconoscesse, e le ricette nuove dicono "pesce spada"."""
    vecchia = Ingredient(name="pesce spada surgelato", category="surgelati")
    nuova = Ingredient(name="pesce spada", category="pesce")
    db.add_all([vecchia, nuova])
    db.commit()

    fusi = merge_duplicates(db)

    assert fusi == [("pesce spada", ["pesce spada surgelato"])]
    rimaste = [i.name for i in db.query(Ingredient).all()]
    assert rimaste == ["pesce spada"]


def test_la_dispensa_si_somma_invece_di_perdersi(client, db):
    from app.models import User

    user = db.query(User).first()
    vecchia = Ingredient(name="mandorle a lamelle", category="frutta")
    nuova = Ingredient(name="mandorle", category="frutta")
    db.add_all([vecchia, nuova])
    db.flush()
    db.add_all([
        PantryItem(user_id=user.id, ingredient_id=vecchia.id, quantity_available=100, unit="g"),
        PantryItem(user_id=user.id, ingredient_id=nuova.id, quantity_available=250, unit="g"),
    ])
    db.commit()

    merge_duplicates(db)

    righe = db.query(PantryItem).all()
    assert len(righe) == 1
    assert righe[0].quantity_available == 350


def test_le_ricette_seguono_l_ingrediente(client, db):
    """Una ricetta scritta prima che la regola cambiasse punta ancora alla riga vecchia:
    se non la si sposta, quella ricetta resta l'unica a usare un ingrediente fantasma."""
    from app.models import Recipe, User

    user = db.query(User).first()
    vecchia = Ingredient(name="mandorle a lamelle", category="frutta")
    nuova = Ingredient(name="mandorle", category="frutta")
    ricetta = Recipe(
        user_id=user.id,
        title="Insalata",
        instructions="Mescola.",
        calories=200,
        protein_g=6,
        carbs_g=8,
        fat_g=16,
    )
    db.add_all([vecchia, nuova, ricetta])
    db.flush()
    db.add(
        RecipeIngredient(
            recipe_id=ricetta.id, ingredient_id=vecchia.id, quantity=30, unit="g"
        )
    )
    db.commit()

    merge_duplicates(db)

    riga = db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == ricetta.id).one()
    assert db.get(Ingredient, riga.ingredient_id).name == "mandorle"


def test_rilanciarlo_non_fa_niente(client, db):
    db.add_all([
        Ingredient(name="pesce spada surgelato", category="surgelati"),
        Ingredient(name="pesce spada", category="pesce"),
    ])
    db.commit()

    merge_duplicates(db)
    assert merge_duplicates(db) == []
