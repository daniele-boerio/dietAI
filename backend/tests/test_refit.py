"""Il ritocco a posteriori delle ricette in programma fuori target."""

import pytest

from app.services import macros, planner
from app.services.refit import refit_future_meals
from tests.test_flow import FakeModel


@pytest.fixture(autouse=True)
def calcolo_acceso(monkeypatch):
    monkeypatch.setattr(macros, "ATTIVO", True)


def test_le_ricette_fuori_target_si_ritoccano_e_il_passato_no(client, diet, db, monkeypatch):
    # Generate coi macro dichiarati (ritocco spento), come le ricette di prima.
    monkeypatch.setattr(macros, "ATTIVO", False)
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    settimana = client.post(f"/api/planning/weeks/{week['id']}/generate").json()
    monkeypatch.setattr(macros, "ATTIVO", True)

    anteprima = refit_future_meals(db, planner.today(), apply=False)
    assert any("Pranzo" in r["title"] for r in anteprima.ritoccate)

    esito = refit_future_meals(db, planner.today(), apply=True)
    pranzo = next(m for m in settimana["days"][0]["meals"] if m["slot_name"] == "Pranzo")
    ricetta = client.get(f"/api/planning/meals/{pranzo['id']}").json()["recipe"]
    assert ricetta["nutrition_source"] == "calcolata"
    assert abs(ricetta["calories"] - 700) <= 70
    assert esito.ritoccate
