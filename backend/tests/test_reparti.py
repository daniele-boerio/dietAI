"""In che reparto sta un ingrediente lo decide chi fa la spesa, non il catalogo.

La categoria esiste per far girare il supermercato una volta sola: se il seitan
finisce in "altro" perché il catalogo non lo conosce, la lista fa fare un giro a
vuoto. Spostarlo è una correzione dell'anagrafica, quindi vale su tutte le liste da lì
in avanti — e deve sopravvivere al seed, che gira a ogni avvio del container.
"""

import pytest

from app.models import Ingredient
from app.seed import seed_ingredients


def reparto(lst: dict, nome: str) -> str | None:
    for categoria in lst["categories"]:
        for item in categoria["items"]:
            if item["name"] == nome:
                return categoria["key"]
    return None


@pytest.fixture()
def seitan(client, diet):
    """Un pranzo col seitan, ingrediente che il catalogo non conosce."""
    week = client.get("/api/planning/weeks/current").json()
    meal = next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Pranzo")
    res = client.put(
        f"/api/planning/meals/{meal['id']}/assign",
        json={
            "recipe": {
                "title": "Seitan al pomodoro",
                "instructions": "Rosola il seitan e condiscilo.",
                "calories": 700,
                "protein_g": 25,
                "carbs_g": 100,
                "fat_g": 15,
                "ingredients": [{"name": "seitan", "quantity": 100, "unit": "g"}],
            }
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def seitan_id(client, seitan, db):
    return db.query(Ingredient).filter(Ingredient.name == "seitan").first().id


def test_quello_che_il_catalogo_non_conosce_finisce_in_altro(client, seitan):
    """Il caso da cui nasce lo spostamento: nessuna parola chiave azzecca il reparto."""
    lst = client.get("/api/shopping/current").json()
    assert reparto(lst, "seitan") == "altro"


def test_spostare_un_ingrediente_lo_porta_nel_reparto_scelto(client, seitan_id):
    res = client.put(
        f"/api/config/ingredients/{seitan_id}/category", json={"category": "cereali"}
    )

    assert res.status_code == 200, res.text
    assert res.json()["label"] == "Pane e cereali"

    lst = client.get("/api/shopping/current").json()
    assert reparto(lst, "seitan") == "cereali"


def test_la_lista_porta_i_reparti_fra_cui_scegliere(client, seitan):
    """Servono tutti, non solo quelli che hanno qualcosa dentro: il reparto giusto
    per un ingrediente è quasi sempre uno di quelli ancora vuoti."""
    lst = client.get("/api/shopping/current").json()

    chiavi = [c["key"] for c in lst["all_categories"]]
    assert "cereali" in chiavi and "surgelati" in chiavi
    assert len(chiavi) == 12


def test_un_reparto_inventato_non_passa(client, seitan_id):
    res = client.put(
        f"/api/config/ingredients/{seitan_id}/category", json={"category": "scaffale 4"}
    )
    assert res.status_code == 400


def test_un_ingrediente_inesistente_da_404(client, diet):
    res = client.put("/api/config/ingredients/999999/category", json={"category": "cereali"})
    assert res.status_code == 404


# ── Il seed non se la riprende ─────────────────────────────────────────────────


def test_il_reparto_scelto_a_mano_sopravvive_al_seed(client, db):
    """Il seed riallinea l'anagrafica al catalogo a ogni avvio del container.

    Senza il flag si riprenderebbe anche i reparti spostati a mano: la scelta
    dell'utente durerebbe fino al primo deploy, e nessuno capirebbe perché.
    """
    seed_ingredients(db)
    pasta = db.query(Ingredient).filter(Ingredient.name == "pasta").first()
    assert pasta.category == "cereali"

    res = client.put(
        f"/api/config/ingredients/{pasta.id}/category", json={"category": "surgelati"}
    )
    assert res.status_code == 200, res.text

    seed_ingredients(db)
    db.refresh(pasta)
    assert pasta.category == "surgelati"


def test_il_seed_riallinea_quello_che_l_utente_non_ha_toccato(db):
    """L'altra metà della regola: il catalogo resta la fonte per tutto il resto."""
    seed_ingredients(db)
    pasta = db.query(Ingredient).filter(Ingredient.name == "pasta").first()
    pasta.category = "altro"  # sballata nell'anagrafica, non scelta dall'utente
    db.commit()

    seed_ingredients(db)
    db.refresh(pasta)
    assert pasta.category == "cereali"


# ── Il reparto indovinato ──────────────────────────────────────────────────────


def test_il_catalogo_si_indovina_da_solo():
    """`guess_category` è la riserva per i nomi che il catalogo non ha: misurarla sui
    nomi che il catalogo ha è il modo più onesto di sapere quanto sbaglia. Con la
    ricerca in mezzo alle parole ne sbagliava venti su centottanta — peperoni fra i
    condimenti, melanzane fra la frutta, melagrana fra i latticini."""
    from app.utils.pricing import INGREDIENT_CATALOG, guess_category

    sbagliati = {
        nome: (categoria, guess_category(nome))
        for nome, (categoria, _, _) in INGREDIENT_CATALOG.items()
        if guess_category(nome) != categoria
    }
    assert sbagliati == {}


@pytest.mark.parametrize(
    "nome, reparto",
    [
        ("peperoni friggitelli", "verdura"),  # "pepe" sta dentro, non all'inizio
        ("salsa di pesce", "condimenti"),  # conta il primo nome, non il secondo
        ("petto di pollo", "carne"),  # se il primo non dice niente, il successivo
        ("peperoncino", "condimenti"),  # la parola chiave più lunga vince
        ("gamberetti", "pesce"),
    ],
)
def test_il_reparto_lo_decide_l_inizio_del_nome(nome, reparto):
    from app.utils.pricing import guess_category

    assert guess_category(nome) == reparto


def test_il_seed_rifa_le_stime_vecchie_ma_non_le_scelte(db):
    """Le righe fuori catalogo tengono il reparto indovinato il primo giorno: quando
    la stima migliora il seed le riallinea, senza toccare quelle spostate a mano."""
    from app.seed import reguess_categories

    db.add_all(
        [
            Ingredient(name="peperoni friggitelli", category="condimenti"),
            Ingredient(name="melagrana sgranata", category="latticini",
                       category_by_user=True),
        ]
    )
    db.commit()

    assert reguess_categories(db) == 1
    reparti = {i.name: i.category for i in db.query(Ingredient).all()}
    assert reparti["peperoni friggitelli"] == "verdura"
    assert reparti["melagrana sgranata"] == "latticini"
