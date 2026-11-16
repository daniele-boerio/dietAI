"""Il riepilogo di un giorno qualsiasi: quello che la home mostra per oggi.

Dalla striscia dei giorni della settimana si apre la giornata: pasti, macro e il
resto (fibre, zuccheri...). La risposta ha la stessa forma dei pasti della home, così
le due pagine disegnano la giornata con lo stesso componente.
"""

from datetime import timedelta

from tests.test_flow import FakeModel  # noqa: F401
from app.services import planner


def _settimana(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    return client.post(f"/api/planning/weeks/{week['id']}/generate").json()


def test_un_giorno_della_settimana(client, diet, monkeypatch):
    week = _settimana(client, diet, monkeypatch)
    martedi = week["days"][1]
    r = client.get(f"/api/tracking/day/{martedi['date']}")
    assert r.status_code == 200
    giorno = r.json()
    assert giorno["has_diet"] and giorno["date"] == martedi["date"]
    assert giorno["day_name"] == martedi["day_name"]
    assert giorno["week_start_date"] == week["week_start_date"]
    assert not giorno["is_today"] and not giorno["is_past"]
    assert [m["meal_id"] for m in giorno["meals"]] == [m["id"] for m in martedi["meals"]]
    pasto = giorno["meals"][0]
    # I target dei macro del pasto e i valori oltre ai macro della ricetta.
    assert {"target_protein_g", "target_carbs_g", "target_fat_g"} <= pasto.keys()
    assert {"fiber_g", "sugar_g", "saturated_fat_g", "alcohol_g", "caffeine_mg"} <= pasto[
        "recipe"
    ].keys()


def test_oggi_e_come_la_home(client, diet, monkeypatch):
    _settimana(client, diet, monkeypatch)
    oggi = planner.today()
    giorno = client.get(f"/api/tracking/day/{oggi.isoformat()}").json()
    home = client.get("/api/tracking/dashboard").json()
    assert giorno["is_today"]
    assert giorno["meals"] == home["today"]["meals"]


def test_settimana_passata_che_non_ce_non_si_crea(client, diet):
    lontano = planner.today() - timedelta(days=70)
    giorno = client.get(f"/api/tracking/day/{lontano.isoformat()}").json()
    assert giorno["is_past"] and giorno["meals"] == []
    settimane = client.get("/api/tracking/weeks").json()
    assert all(s["week_start_date"] != (lontano - timedelta(days=lontano.weekday())).isoformat()
               for s in settimane)


def test_settimana_futura_si_apre(client, diet):
    avanti = planner.today() + timedelta(days=14)
    giorno = client.get(f"/api/tracking/day/{avanti.isoformat()}").json()
    assert giorno["meals"]  # le caselle ci sono, vuote
    assert all(m["recipe"] is None and m["is_followed"] is None for m in giorno["meals"])


def test_data_non_valida(client, diet):
    assert client.get("/api/tracking/day/ieri").status_code == 422
