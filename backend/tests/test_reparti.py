"""In che reparto sta un ingrediente lo decide chi fa la spesa, non il catalogo.

La categoria esiste per far girare il supermercato una volta sola: se gli spaghetti
finiscono in "altro" perché il catalogo non li conosce, la lista fa fare un giro a
vuoto. Spostarli è una correzione dell'anagrafica, quindi vale su tutte le liste da lì
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
def spaghetti(client, diet):
    """Un pranzo di spaghetti, ingrediente che il catalogo non conosce."""
    week = client.get("/api/planning/weeks/current").json()
    meal = next(m for m in week["days"][0]["meals"] if m["slot_name"] == "Pranzo")
    res = client.put(
        f"/api/planning/meals/{meal['id']}/assign",
        json={
            "recipe": {
                "title": "Spaghetti al pomodoro",
                "instructions": "Lessa gli spaghetti e condiscili.",
                "calories": 700,
                "protein_g": 25,
                "carbs_g": 100,
                "fat_g": 15,
                "ingredients": [{"name": "spaghetti", "quantity": 100, "unit": "g"}],
            }
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def spaghetti_id(client, spaghetti, db):
    return db.query(Ingredient).filter(Ingredient.name == "spaghetti").first().id


def test_quello_che_il_catalogo_non_conosce_finisce_in_altro(client, spaghetti):
    """Il caso da cui nasce lo spostamento: nessuna parola chiave azzecca il reparto."""
    lst = client.get("/api/shopping/current").json()
    assert reparto(lst, "spaghetti") == "altro"


def test_spostare_un_ingrediente_lo_porta_nel_reparto_scelto(client, spaghetti_id):
    res = client.put(
        f"/api/config/ingredients/{spaghetti_id}/category", json={"category": "cereali"}
    )

    assert res.status_code == 200, res.text
    assert res.json()["label"] == "Pane e cereali"

    lst = client.get("/api/shopping/current").json()
    assert reparto(lst, "spaghetti") == "cereali"


def test_la_lista_porta_i_reparti_fra_cui_scegliere(client, spaghetti):
    """Servono tutti, non solo quelli che hanno qualcosa dentro: il reparto giusto
    per un ingrediente è quasi sempre uno di quelli ancora vuoti."""
    lst = client.get("/api/shopping/current").json()

    chiavi = [c["key"] for c in lst["all_categories"]]
    assert "cereali" in chiavi and "surgelati" in chiavi
    assert len(chiavi) == 12


def test_un_reparto_inventato_non_passa(client, spaghetti_id):
    res = client.put(
        f"/api/config/ingredients/{spaghetti_id}/category", json={"category": "scaffale 4"}
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
