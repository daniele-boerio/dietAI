"""Input sbagliati e risposte storte del modello: 4xx leggibili, mai 500.

Ognuno di questi casi finiva in un 500 — spesso dopo una chiamata al modello già
pagata — o, peggio, passava in silenzio.
"""

import pytest

from app.routers import recipes as recipes_router
from app.services import planner
from tests.test_flow import FakeModel


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    return client.get("/api/planning/weeks/current").json()


@pytest.mark.parametrize("regola", [{"type": "weekly", "day": 9}, {"type": "weekly", "day": "x"},
                                     {"type": "mensile"}])
def test_una_regola_di_ricorrenza_sbagliata_e_un_422(client, settimana, regola):
    pasto = settimana["days"][0]["meals"][0]
    res = client.put(
        f"/api/planning/meals/{pasto['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": regola},
    )
    assert res.status_code == 422


def test_un_nome_che_si_svuota_e_un_400(client):
    for rotta in ("/api/config/pantry", "/api/config/base-ingredients"):
        res = client.post(rotta, json={"ingredient_name": "fresco"})
        assert res.status_code == 400, (rotta, res.text)


@pytest.mark.parametrize("anno", [0, 1999, 10000])
def test_l_anno_fuori_misura_e_un_422(client, anno):
    assert client.get(f"/api/tracking/year?year={anno}").status_code == 422


def test_l_andamento_non_inventa_settimane_passate(client, diet, db):
    from app.models import WeekPlan

    res = client.get("/api/tracking/weekly?week_start_date=2001-01-01")
    assert res.status_code == 404
    assert db.query(WeekPlan).count() == 0
    assert client.get("/api/tracking/weekly?week_start_date=9999-12-31").status_code == 400


def test_una_sostituzione_con_numeri_a_parole_non_va_in_500(client, settimana, monkeypatch):
    pranzo = settimana["days"][0]["meals"][1]

    class Sostituto:
        model = "finto"

        def generate_json(self, *a, **k):
            return {
                "substitute": {"name": "farro", "quantity": "q.b.", "unit": "g"},
                "updated_nutrition": {"calories": "circa 450"},
            }

    monkeypatch.setattr(recipes_router, "get_client", lambda db, user, role: Sostituto())
    res = client.post(
        f"/api/recipes/{pranzo['recipe']['id']}/substitute",
        json={"ingredient_to_replace": "pasta", "meal_id": pranzo["id"]},
    )
    assert res.status_code == 200, res.text


def test_un_meal_id_altrui_non_allarga_la_sostituzione(client, settimana):
    pranzo = settimana["days"][0]["meals"][1]
    res = client.post(
        f"/api/recipes/{pranzo['recipe']['id']}/substitute",
        json={"ingredient_to_replace": "pasta", "meal_id": 999999},
    )
    assert res.status_code == 404


def test_una_settimana_con_giorni_storti_tiene_quelli_buoni(client, diet, monkeypatch):
    class ModelloDisordinato(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            data = super().generate_json(system, prompt, **kwargs)
            data["days"][1] = "lunedì"  # una stringa al posto di un giorno
            data["days"][2]["meals"] = ["cena"]
            return data

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloDisordinato(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == 5 * 3


def test_la_sostituzione_riceve_le_regole_dell_utente(client, settimana, monkeypatch):
    res = client.put(
        "/api/config/preferences",
        json={"prefer_seasonal": True, "notes": "Sono celiaco: niente glutine."},
    )
    assert res.status_code == 200, res.text
    pranzo = settimana["days"][0]["meals"][1]
    visto = {}

    class Sostituto:
        model = "finto"

        def generate_json(self, system, prompt, **k):
            visto["prompt"] = prompt
            return {"substitute": {"name": "riso", "quantity": 80, "unit": "g"}}

    monkeypatch.setattr(recipes_router, "get_client", lambda db, user, role: Sostituto())
    client.post(
        f"/api/recipes/{pranzo['recipe']['id']}/substitute",
        json={"ingredient_to_replace": "pasta", "meal_id": pranzo["id"]},
    )
    assert "Sono celiaco" in visto["prompt"]


@pytest.mark.parametrize(
    ("rotta", "corpo"),
    [
        ("/api/recipes", {"title": "x", "instructions": "y", "calories": 1, "protein_g": 1,
                          "carbs_g": 1, "fat_g": 1, "difficulty": "estrema"}),
        ("/api/recipes", {"title": "x", "instructions": "y" * 10001, "calories": 1,
                          "protein_g": 1, "carbs_g": 1, "fat_g": 1}),
    ],
)
def test_una_ricetta_fuori_misura_e_un_422(client, rotta, corpo):
    """Una difficoltà fuori elenco era un 500 dal CHECK del database."""
    assert client.post(rotta, json=corpo).status_code == 422


def test_giorni_fuori_settimana_e_assegnazioni_ambigue(client, settimana):
    week_id = settimana["id"]
    assert client.post(f"/api/planning/weeks/{week_id}/generate", json={"days": [9]}).status_code == 422
    pasto = settimana["days"][0]["meals"][0]
    assert client.put(f"/api/planning/meals/{pasto['id']}/assign", json={}).status_code == 422
