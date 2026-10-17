"""Gli alimenti esclusi li controlla il server, non solo il prompt.

Prima gli esclusi arrivavano al modello e basta: una ricetta che li ignorava finiva in
piano e in lista della spesa senza un avviso. Qui si guarda che non entri.
"""

import pytest

from app.services import planner
from app.services.exclusions import ExcludedFoodError, check_recipe, find_excluded
from app.services.ingredients import normalize_name
from tests.conftest import TEST_EMAIL
from tests.test_flow import DAYS, FakeModel


def _escludi(client, nome, motivo="allergia"):
    res = client.post(
        "/api/config/excluded", json={"ingredient_name": nome, "reason": motivo}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _user_id(db):
    from app.models import User

    return db.query(User).filter(User.email == TEST_EMAIL).one().id


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.mark.parametrize(
    ("escluso", "ingrediente", "colpito"),
    [
        ("glutine", "pasta", True),
        ("glutine", "pasta senza glutine", False),
        ("glutine", "penne (senza glutine)", False),
        ("lattosio", "mozzarella", True),
        ("lattosio", "latte di soia", False),
        ("latticini", "yogurt greco", True),
        ("frutta a guscio", "pesto", True),
        ("arachidi", "burro di arachidi", True),
        ("noci", "noce", True),
        ("frutti di mare", "gamberetti", True),
        ("frutti di mare", "petto di pollo", False),
    ],
)
def test_le_famiglie_riconoscono_gli_alimenti(client, db, escluso, ingrediente, colpito):
    _escludi(client, escluso)
    assert bool(find_excluded(db, _user_id(db), [ingrediente])) is colpito


def test_una_ricetta_del_modello_con_un_escluso_non_passa(client, db):
    _escludi(client, "arachidi")
    with pytest.raises(ExcludedFoodError) as exc:
        check_recipe(
            db,
            _user_id(db),
            {"title": "Pollo satay", "ingredients": [{"name": "burro di arachidi"}]},
        )
    assert "arachidi" in exc.value.detail


def test_la_generazione_lascia_vuoti_i_piatti_con_un_escluso(client, diet, fake_ai):
    _escludi(client, "zucchine")
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text

    generation = res.json()["generation"]
    # Pranzo e cena del modello finto hanno le zucchine: entrano solo le colazioni.
    assert generation["filled"] == DAYS
    assert len(generation["excluded"]) == DAYS * 2

    lista = client.get("/api/shopping/current").json()
    nomi = {i["name"] for cat in lista["categories"] for i in cat["items"]}
    assert "zucchine" not in nomi


def test_aggiungere_un_escluso_dice_dove_e_gia_in_programma(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    riga = _escludi(client, "petto di pollo")
    # Le cene del modello finto: tutte da oggi (lunedì, nei test) a domenica.
    assert len(riga["conflicts"]) == DAYS
    assert "Cena" in riga["conflicts"][0]


def test_dal_ricettario_non_torna_un_piatto_con_un_escluso(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    week = client.get("/api/planning/weeks/current").json()
    cena = week["days"][0]["meals"][2]

    _escludi(client, "petto di pollo")
    pranzo = week["days"][1]["meals"][1]
    res = client.put(
        f"/api/planning/meals/{pranzo['id']}/assign",
        json={"recipe_id": cena["recipe"]["id"]},
    )
    assert res.status_code == 422
    assert "petto di pollo" in res.json()["detail"]


def test_le_glosse_che_cambiano_l_alimento_restano_nel_nome():
    assert normalize_name("penne (senza glutine)") == "pasta senza glutine"
    assert normalize_name("latte (senza lattosio)") == "latte senza lattosio"
    # Le altre glosse continuano a sparire.
    assert normalize_name("pasta corta (penne)") == "pasta"
