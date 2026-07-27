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
        ("peperoni a listarelle", "peperoni"),
        ("petto di pollo a fettine", "petto di pollo"),
        ("aglio a spicchi", "aglio"),
        # Calibro e qualità.
        ("zucchine medie", "zucchine"),
        ("pomodori bio", "pomodori"),
        # Formato della pasta: penne o fusilli sono lo stesso pacco e lo stesso piatto.
        ("pasta corta", "pasta"),
        ("pasta corta (penne)", "pasta"),
        ("pasta lunga", "pasta"),
        ("pasta di semola di grano duro", "pasta"),
        ("spaghetti", "pasta"),
        ("fusilli", "pasta"),
        # La pasta è pasta, comunque la si scriva: una riga sola nella spesa.
        ("fusilli integrali", "pasta"),
        ("pasta integrale", "pasta"),
        # Sulla pasta ci va il formaggio che c'è: parmigiano e grana sono una riga sola.
        ("parmigiano grattugiato", "formaggio"),
        ("grana padano", "formaggio"),
        ("formaggio grattugiato", "formaggio"),
    ],
)
def test_i_qualificatori_spariscono(scritto, atteso):
    assert normalize_name(scritto) == atteso


@pytest.mark.parametrize(
    "cereale",
    [
        # Il formato della pasta si può unificare, un altro cereale no: sono altri
        # macro e un altro scaffale. È costato una fusione da disfare a mano.
        "cous cous",
        "riso",
        "riso integrale",
        "orzo",
        "farro",
        "quinoa",
        # Ripiena e gnocchi: dentro c'è altro (carne, formaggio, patate).
        "ravioli",
        "tortellini",
        "gnocchi",
    ],
)
def test_un_cereale_non_diventa_pasta(cereale):
    assert normalize_name(cereale) == cereale


@pytest.mark.parametrize(
    "scritto",
    [
        # Queste parole cambiano i numeri della dieta: togliendole si farebbe passare
        # uno yogurt intero per uno magro, e i macro sono il vincolo più duro dell'app.
        "yogurt greco magro",
        "latte intero",
        # "Integrale" resta dove è un altro alimento sullo scaffale. L'eccezione è la
        # pasta, che sta tutta sulla stessa riga: vedi il test qui sopra.
        "pane integrale",
        "riso integrale",
        "tonno al naturale",
        "cioccolato fondente",
        # "Pelati" non è lo stato dei pomodori: è una conserva, un altro prodotto.
        "pomodori pelati",
        # Il formaggio da grattugia si unifica, gli altri no: qui dentro c'è di tutto.
        "formaggio spalmabile",
        "mozzarella",
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


# ── Riparazione dei cereali fusi per sbaglio ──────────────────────────────────


def _ricetta(db, user_id, titolo, istruzioni, ingredient_id):
    from app.models import Recipe

    ricetta = Recipe(
        user_id=user_id,
        title=titolo,
        instructions=istruzioni,
        calories=500,
        protein_g=20,
        carbs_g=70,
        fat_g=10,
    )
    db.add(ricetta)
    db.flush()
    db.add(
        RecipeIngredient(
            recipe_id=ricetta.id, ingredient_id=ingredient_id, quantity=80, unit="g"
        )
    )
    return ricetta


def test_i_cereali_fusi_tornano_al_loro_nome(client, db, monkeypatch):
    """Il danno da disfare: una fusione troppo larga aveva reso "pasta" anche il
    cous cous. Il nome originale non è più in anagrafica, ma la ricetta lo dice ancora."""
    from app.models import User
    from app import repair_cereals

    monkeypatch.setattr(repair_cereals, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    user = db.query(User).first()
    pasta = Ingredient(name="pasta", category="cereali")
    db.add(pasta)
    db.flush()
    couscous = _ricetta(db, user.id, "Cous cous di verdure", "Sgrana il cous cous.", pasta.id)
    vera = _ricetta(db, user.id, "Pasta al pomodoro", "Cuoci la pasta.", pasta.id)
    db.commit()

    repair_cereals.main()

    riga = db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == couscous.id).one()
    assert db.get(Ingredient, riga.ingredient_id).name == "cous cous"
    # Quella che la pasta la usava davvero resta dov'è.
    riga = db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == vera.id).one()
    assert db.get(Ingredient, riga.ingredient_id).name == "pasta"


def test_dove_il_testo_non_decide_non_si_indovina(client, db, monkeypatch):
    """Due cereali nel testo: sceglierne uno a caso sarebbe peggio che lasciar decidere."""
    from app.models import User
    from app import repair_cereals

    monkeypatch.setattr(repair_cereals, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    user = db.query(User).first()
    pasta = Ingredient(name="pasta", category="cereali")
    db.add(pasta)
    db.flush()
    dubbia = _ricetta(db, user.id, "Insalata di cereali", "Riso o farro, a piacere.", pasta.id)
    db.commit()

    repair_cereals.main()

    riga = db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == dubbia.id).one()
    assert db.get(Ingredient, riga.ingredient_id).name == "pasta"
