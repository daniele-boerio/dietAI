"""Normalizzazione dei nomi: due modi di scrivere la stessa cosa sono la stessa riga.

La linea di taglio: via tutto quello che dice **com'è messo** l'alimento
(conservazione, taglio, calibro), resta tutto quello che dice **cos'è**. Se salta,
saltano due cose insieme: la dispensa smette di coprire le ricette e la lista della
spesa fa due righe dello stesso alimento.
"""

import pytest

from app.models import Ingredient, PantryItem, RecipeIngredient
from app.services.ingredients import (
    _CATALOG_FORMS,
    get_or_create_ingredient,
    merge_duplicates,
    normalize_name,
)
from app.utils.pricing import DEFAULT_BASE_INGREDIENTS, INGREDIENT_CATALOG


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


# ── Apostrofi, spazi ed elisioni ───────────────────────────────────────────────
#
# Il doppione che non si vede: due righe di "tonno all'olio d'oliva" in dispensa,
# identiche a leggersi, una con l'apostrofo dritto e una con quello tipografico che il
# modello scrive da sé. Non c'è modo di accorgersene guardando, e nemmeno di
# correggerlo con una regola scritta a mano — anche quella andrebbe scritta con
# l'apostrofo giusto.


@pytest.mark.parametrize(
    "scritto",
    [
        "Tonno all'olio d'oliva",
        "tonno all’olio d’oliva",  # apostrofo tipografico
        "tonno all'olio di oliva",  # elisione sciolta
        "tonno all' olio d'oliva",  # spazio dopo l'apostrofo
        "tonno all’olio di oliva",  # spazio unificatore
        "Tonno all'olio d'oliva (sgocciolato)",
    ],
)
def test_un_solo_modo_di_scrivere_l_apostrofo(scritto):
    assert normalize_name(scritto) == "tonno all'olio d'oliva"


def test_i_due_apostrofi_finiscono_sulla_stessa_riga(client, db):
    """Il caso vero: la spesa mette in dispensa il tonno di una ricetta, e la ricetta
    dopo lo scrive con l'altro apostrofo. Se sono due righe, in dispensa se ne vedono
    due — e la lista della spesa lo richiede pur avendolo in casa."""
    prima = get_or_create_ingredient(db, "Tonno all'olio d'oliva")
    dopo = get_or_create_ingredient(db, "tonno all’olio d’oliva")

    assert prima.id == dopo.id
    assert db.query(Ingredient).filter(Ingredient.name.like("tonno%")).count() == 1


# ── Colore e numero ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scritto,atteso",
    [
        # Il colore del peperone è come il calibro: stesso banco, stesso prezzo, stessi
        # macro. Separati sono due righe in lista e una dispensa che non copre nessuna
        # delle due.
        ("peperoni rossi", "peperoni"),
        ("peperone rosso", "peperoni"),
        ("peperoni rossi e gialli", "peperoni"),
        ("peperoni gialli a listarelle", "peperoni"),
        # Singolare e plurale sono lo stesso alimento: si sceglie la forma del
        # catalogo, che è quella a cui sono attaccati reparto e prezzo.
        ("cetriolo", "cetrioli"),
        ("zucchina", "zucchine"),
        ("pomodoro", "pomodori"),
        ("cavolfiori", "cavolfiore"),
        ("uovo", "uova"),
        # La stessa parola scritta in due modi: non è un accorpamento, è la stessa
        # scatola. Vale sulla parola, o "couscous integrale" resterebbe una riga a sé.
        ("couscous", "cous cous"),
        ("couscous integrale", "cous cous integrale"),
        # Quello che fai in cucina prima di pesarlo non è come lo compri.
        ("tonno al naturale sgocciolato", "tonno al naturale"),
        ("ceci scolati", "ceci"),
    ],
)
def test_lo_stesso_alimento_scritto_in_due_modi(scritto, atteso):
    assert normalize_name(scritto) == atteso


def test_il_peperoncino_non_e_un_peperone():
    """La regola sul colore guarda «peperone/peperoni», non una parola che ci somiglia:
    il peperoncino è un'altra cosa, sta in un altro reparto e costa dieci volte tanto."""
    assert normalize_name("peperoncino") == "peperoncino"
    assert normalize_name("peperoncini") == "peperoncino"
    assert normalize_name("peperoncini rossi") != "peperoni"


@pytest.mark.parametrize(
    "coppia",
    [
        # Il gambo è lo stesso e cambia solo la vocale finale, ma sono due alimenti:
        # senza il vincolo sulle coppie del singolare/plurale (o↔i, a↔e, e↔i) la frutta
        # diventerebbe pesce, e sarebbe una fusione da disfare a mano.
        ("pesca", "pesce"),
        ("grano", "grana"),
    ],
)
def test_due_alimenti_diversi_non_si_toccano(coppia):
    uno, altro = coppia
    assert normalize_name(uno) != normalize_name(altro)


def test_la_mappa_del_singolare_non_scavalca_il_catalogo():
    """Un nome che il catalogo conosce è già un alimento suo: non lo si sposta altrove."""
    assert not set(_CATALOG_FORMS) & set(INGREDIENT_CATALOG)
    assert set(_CATALOG_FORMS.values()) <= set(INGREDIENT_CATALOG)


# ── Il catalogo dev'essere scritto come la normalizzazione scrive ──────────────


@pytest.mark.parametrize("name", sorted(set(INGREDIENT_CATALOG) | set(DEFAULT_BASE_INGREDIENTS)))
def test_i_nomi_del_catalogo_sopravvivono_alla_normalizzazione(name):
    """Il seed semina l'anagrafica con questi nomi così come sono scritti, a ogni avvio
    del container. Un nome che `normalize_name` riscrive è una riga che nessuna ricetta
    raggiungerà mai — e l'alimento vero resta senza prezzo, che è il modo in cui il
    totale della spesa perde le voci più care."""
    assert normalize_name(name) == name


def test_due_voci_di_catalogo_non_finiscono_sulla_stessa_riga():
    """Sarebbero due prezzi per lo stesso nome, e a vincere sarebbe l'ultimo seminato."""
    righe: dict[str, list[str]] = {}
    for name in INGREDIENT_CATALOG:
        righe.setdefault(normalize_name(name), []).append(name)
    assert {k: v for k, v in righe.items() if len(v) > 1} == {}


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


def test_le_due_scatolette_di_tonno_tornano_una(client, db):
    """Quello che c'è già in tabella: due righe identiche a vedersi, una per apostrofo,
    e in dispensa due voci di tonno. `python -m app.merge_ingredients` le rimette
    insieme sommando quello che c'è in casa — la lista della spesa smette di chiederlo."""
    from app.models import User

    user = db.query(User).first()
    dritto = Ingredient(name="tonno all'olio d'oliva", category="pesce")
    curvo = Ingredient(name="tonno all’olio d’oliva", category="pesce")
    db.add_all([dritto, curvo])
    db.flush()
    db.add_all([
        PantryItem(user_id=user.id, ingredient_id=dritto.id, quantity_available=160, unit="g"),
        PantryItem(user_id=user.id, ingredient_id=curvo.id, quantity_available=80, unit="g"),
    ])
    db.commit()

    merge_duplicates(db)

    assert [i.name for i in db.query(Ingredient).all()] == ["tonno all'olio d'oliva"]
    righe = db.query(PantryItem).all()
    assert len(righe) == 1
    assert righe[0].quantity_available == 240


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
