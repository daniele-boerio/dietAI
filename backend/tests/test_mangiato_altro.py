"""«Ho mangiato altro: cosa?» — il testo, la stima e cosa ne fa l'andamento.

Un pasto saltato era un buco nei dati. Ora quello che l'utente scrive si stima in
calorie e macro, e l'andamento sa dire quanto si è mangiato davvero — ma solo nei
giorni di cui si sa tutto, perché un totale fatto di metà pasti non è il totale del
giorno.
"""

import pytest

from app.routers import planning as planning_router
from app.services import planner
from tests.test_flow import FakeModel


class ModelloCheStima(FakeModel):
    def generate_json(self, system, prompt, **kwargs):
        if "COSA HA MANGIATO INVECE" in prompt:
            return {"calories": 850, "protein_g": 32, "carbs_g": 105, "fat_g": 30,
                    "note": "pizza margherita intera"}
        return super().generate_json(system, prompt, **kwargs)


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    finto = lambda db, user, role: ModelloCheStima(user)  # noqa: E731
    monkeypatch.setattr(planner, "get_client", finto)
    monkeypatch.setattr(planning_router, "get_client", finto)
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    return client.post(f"/api/planning/weeks/{week['id']}/generate").json()


def pasto(settimana, dow, nome):
    return next(m for m in settimana["days"][dow]["meals"] if m["slot_name"] == nome)


def test_la_stima_si_salva_sul_pasto(client, settimana):
    cena = pasto(settimana, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    res = client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "una pizza"})

    assert res.status_code == 200, res.text
    assert res.json()["deviation_notes"] == "una pizza"
    assert res.json()["eaten_nutrition"]["calories"] == 850
    assert res.json()["eaten_nutrition"]["note"] == "pizza margherita intera"


def test_su_un_pasto_non_saltato_non_si_scrive(client, settimana):
    cena = pasto(settimana, 0, "Cena")
    res = client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "una pizza"})
    assert res.status_code == 400


def test_cambiare_risposta_cancella_la_stima(client, settimana):
    cena = pasto(settimana, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})
    client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "una pizza"})

    res = client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": True})
    assert res.json()["eaten_nutrition"] is None


def test_il_testo_vuoto_cancella(client, settimana):
    cena = pasto(settimana, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})
    client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "una pizza"})

    res = client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": ""})
    assert res.json()["eaten_nutrition"] is None
    assert res.json()["deviation_notes"] is None


def test_l_andamento_conta_quello_che_si_e_mangiato_davvero(client, settimana):
    """Lunedì: colazione e pranzo seguiti (400 + 700), cena sostituita da una pizza
    (850). Il giorno è completo: 1950 kcal mangiate davvero."""
    for nome in ("Colazione", "Pranzo"):
        m = pasto(settimana, 0, nome)
        client.put(f"/api/planning/meals/{m['id']}/followed", json={"is_followed": True})
    cena = pasto(settimana, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})
    client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "una pizza"})

    tracking = client.get("/api/tracking/weekly").json()
    lunedi = tracking["days"][0]["totals"]
    assert lunedi["eaten_complete"] is True
    assert lunedi["eaten_calories"] == 400 + 700 + 850
    assert tracking["weekly_summary"]["avg_daily_calories_eaten"] == 1950


def test_un_giorno_a_meta_non_ha_un_totale(client, settimana):
    """Martedì solo il pranzo è segnato: il totale non si dice, e la media non lo conta."""
    m = pasto(settimana, 1, "Pranzo")
    client.put(f"/api/planning/meals/{m['id']}/followed", json={"is_followed": True})

    tracking = client.get("/api/tracking/weekly").json()
    assert tracking["days"][1]["totals"]["eaten_complete"] is False
    assert tracking["weekly_summary"]["avg_daily_calories_eaten"] is None


def test_il_pasto_di_un_altro_non_si_tocca(client, guest_client, settimana):
    cena = pasto(settimana, 0, "Cena")
    res = guest_client.put(f"/api/planning/meals/{cena['id']}/eaten", json={"text": "x"})
    assert res.status_code == 404
