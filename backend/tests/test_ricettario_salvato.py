"""Il ricettario tiene solo le ricette salvate: preferite, votate o scritte a mano.

Prima teneva tutto quello che il modello generava, e dopo un mese i piatti piaciuti si
perdevano fra centinaia mai guardati. Le non salvate escono subito dal ricettario,
restano agganciate ai loro pasti finché servono e si cancellano davvero alla
generazione dopo, quando nessun pasto le usa più.
"""

import pytest

from app.models import Recipe
from app.services import planner
from tests.test_flow import FakeModel


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    assert client.post(f"/api/planning/weeks/{week['id']}/generate").status_code == 200
    return client.get("/api/planning/weeks/current").json()


def ricette_in_piano(week) -> list[int]:
    return sorted({m["recipe"]["id"] for d in week["days"] for m in d["meals"] if m["recipe"]})


def titoli(client, **params) -> set[int]:
    res = client.get("/api/recipes", params={"per_page": 100, **params})
    return {r["id"] for r in res.json()["items"]}


def test_le_generate_non_salvate_non_sono_nel_ricettario(client, settimana):
    assert ricette_in_piano(settimana)
    assert titoli(client) == set()


def test_votare_o_mettere_fra_le_preferite_la_salva(client, settimana):
    a, b = ricette_in_piano(settimana)[:2]
    client.put(f"/api/recipes/{a}/favorite", json={"is_favorite": True})
    client.put(f"/api/recipes/{b}/rate", json={"rating": 4})

    assert titoli(client) == {a, b}
    assert titoli(client, scope="proposable") == {a, b}


def test_quelle_votate_male_restano_ma_non_si_propongono(client, settimana):
    a = ricette_in_piano(settimana)[0]
    client.put(f"/api/recipes/{a}/rate", json={"rating": 2})

    assert a in titoli(client)
    assert a in titoli(client, scope="low")
    assert a not in titoli(client, scope="proposable")


def test_quelle_scritte_a_mano_sono_salvate(client, diet):
    res = client.post(
        "/api/recipes",
        json={
            "title": "Pasta al pomodoro di casa",
            "ingredients": [{"name": "pasta", "quantity": 80, "unit": "g"}],
            "instructions": "Cuoci.",
            "calories": 300,
            "protein_g": 10,
            "carbs_g": 60,
            "fat_g": 2,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["id"] in titoli(client)
    assert res.json()["id"] in titoli(client, scope="proposable")


def test_la_generazione_cancella_solo_le_non_salvate_che_nessuno_usa(client, db, settimana):
    usata, salvata = ricette_in_piano(settimana)[:2]
    client.put(f"/api/recipes/{salvata}/favorite", json={"is_favorite": True})
    # Due caselle svuotate: le loro ricette non le usa più nessuno.
    lunedi = settimana["days"][0]["meals"]
    orfana = next(m for m in lunedi if m["recipe"] and m["recipe"]["id"] not in (usata, salvata))
    orfana_id = orfana["recipe"]["id"]
    client.delete(f"/api/planning/meals/{orfana['id']}/recipe")
    for d in settimana["days"]:
        for m in d["meals"]:
            if m["recipe"] and m["recipe"]["id"] in (orfana_id, salvata):
                client.delete(f"/api/planning/meals/{m['id']}/recipe")

    prossima = client.get("/api/planning/weeks/next").json()
    client.post(f"/api/planning/weeks/{prossima['id']}/generate")

    db.expire_all()
    assert db.get(Recipe, orfana_id) is None
    assert db.get(Recipe, salvata) is not None  # preferita: resta anche senza pasti
    assert db.get(Recipe, usata) is not None  # ancora in un pasto: serve all'andamento


def test_prima_di_generare_si_vedono_le_ricette_da_salvare(client, settimana):
    a = ricette_in_piano(settimana)[0]
    prossima = client.get("/api/planning/weeks/next").json()

    da_salvare = client.get("/api/recipes/unsaved", params={"week_id": prossima["id"]}).json()
    ids = {r["id"] for r in da_salvare}
    assert set(ricette_in_piano(settimana)) <= ids

    client.put(f"/api/recipes/{a}/rate", json={"rating": 5})
    dopo = client.get("/api/recipes/unsaved", params={"week_id": prossima["id"]}).json()
    assert a not in {r["id"] for r in dopo}


def test_le_ricette_da_salvare_sono_solo_le_mie(client, guest_client, settimana):
    assert (
        guest_client.get(
            "/api/recipes/unsaved", params={"week_id": settimana["id"]}
        ).status_code
        == 404
    )
