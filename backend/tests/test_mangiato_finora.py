"""Il totale del giorno nella settimana: quanto si è mangiato davvero finora.

Prima l'intestazione del giorno diceva il piano intero anche a colazione appena
fatta. Ora `eaten_calories` somma solo i pasti segnati, coi loro valori: un pranzo da
700 conta 700 anche se la dieta ne chiedeva 500, e un giorno che deve venire dice 0.
"""

from tests.test_flow import FakeModel  # noqa: F401
from app.services import planner


def _settimana(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    return client.post(f"/api/planning/weeks/{week['id']}/generate").json()


def test_senza_pasti_segnati_e_zero(client, diet, monkeypatch):
    week = _settimana(client, diet, monkeypatch)
    for day in week["days"]:
        assert day["totals"]["eaten_calories"] == 0
        assert day["totals"]["tracked_meals"] == 0
        assert day["totals"]["calories"] > 0  # il piano c'è, solo non è ancora mangiato


def test_cresce_coi_pasti_seguiti(client, diet, monkeypatch):
    week = _settimana(client, diet, monkeypatch)
    colazione, pranzo, _cena = week["days"][0]["meals"]
    client.put(f"/api/planning/meals/{colazione['id']}/followed", json={"is_followed": True})
    lunedi = client.get("/api/planning/weeks/current").json()["days"][0]["totals"]
    assert lunedi["eaten_calories"] == colazione["recipe"]["calories"]
    assert lunedi["tracked_meals"] == 1

    client.put(f"/api/planning/meals/{pranzo['id']}/followed", json={"is_followed": True})
    lunedi = client.get("/api/planning/weeks/current").json()["days"][0]["totals"]
    # I valori del piatto, non il target del pasto.
    assert lunedi["eaten_calories"] == colazione["recipe"]["calories"] + pranzo["recipe"]["calories"]
