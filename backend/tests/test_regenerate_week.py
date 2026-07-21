"""Generazione parziale contro rigenerazione totale.

Ogni chiamata al modello si paga, e quella sulla settimana intera è la più cara
dell'app: il default deve riempire solo i buchi, e rifare tutto dev'essere una scelta
esplicita. Prima non lo era — il pulsante diceva "riempi i vuoti" e rigenerava tutto.
"""

import pytest

from app.services import planner
from tests.test_flow import DAYS, FakeModel


class ContaChiamate(FakeModel):
    """Come FakeModel, ma tiene i titoli distinti a ogni giro e conta le chiamate."""

    chiamate = 0

    def generate_json(self, system, prompt, **kwargs):
        ContaChiamate.chiamate += 1
        data = super().generate_json(system, prompt, **kwargs)
        for day in data["days"]:
            for meal in day["meals"]:
                meal["recipe"]["title"] += f" v{ContaChiamate.chiamate}"
        self.prompt = prompt
        return data


@pytest.fixture()
def fake_ai(monkeypatch, client):
    ContaChiamate.chiamate = 0
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ContaChiamate(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta"})


def _titoli(client):
    week = client.get("/api/planning/weeks/current").json()
    return [m["recipe"]["title"] for d in week["days"] for m in d["meals"] if m["recipe"]]


def test_la_generazione_normale_riempie_solo_i_vuoti(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    prima = _titoli(client)

    # Si svuota una casella sola: la seconda generazione deve toccare quella e basta.
    week = client.get("/api/planning/weeks/current").json()
    meal_id = week["days"][0]["meals"][0]["id"]
    client.delete(f"/api/planning/meals/{meal_id}/recipe")

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200
    assert res.json()["generation"]["filled"] == 1

    dopo = _titoli(client)
    # Tutte le altre ricette sono rimaste quelle di prima.
    assert sorted(t for t in dopo if not t.endswith("v2")) == sorted(
        t for t in prima if t not in (prima[0],)
    )


def test_a_settimana_piena_la_generazione_normale_si_ferma(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert res.status_code == 400
    assert "Rigenera tutto" in res.json()["detail"]  # dice come si fa, se è voluto
    assert ContaChiamate.chiamate == 1  # e soprattutto: non ha speso una seconda volta


def test_rigenera_tutto_rifa_ogni_ricetta(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    prima = _titoli(client)

    res = client.post(f"/api/planning/weeks/{week['id']}/generate?regenerate_all=true")
    assert res.status_code == 200
    assert res.json()["generation"]["filled"] == DAYS * 3

    dopo = _titoli(client)
    assert len(dopo) == len(prima)
    assert all(t.endswith("v2") for t in dopo)  # tutte nuove


def test_rigenera_tutto_non_tocca_i_pasti_fissi(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    week = client.get("/api/planning/weeks/current").json()
    meal = week["days"][0]["meals"][0]
    client.put(
        f"/api/planning/meals/{meal['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": {"type": "weekly", "day": 0}},
    )
    titolo_fisso = meal["recipe"]["title"]

    client.post(f"/api/planning/weeks/{week['id']}/generate?regenerate_all=true")

    dopo = client.get("/api/planning/weeks/current").json()
    assert dopo["days"][0]["meals"][0]["recipe"]["title"] == titolo_fisso


def test_le_ricette_vecchie_restano_nel_ricettario(client, diet, fake_ai):
    """La conferma promette questo: rigenerare non cancella nulla."""
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    prima = client.get("/api/recipes", params={"per_page": 100}).json()["total"]

    client.post(f"/api/planning/weeks/{week['id']}/generate?regenerate_all=true")
    dopo = client.get("/api/recipes", params={"per_page": 100}).json()["total"]

    assert dopo == prima * 2  # le nuove si aggiungono, le vecchie restano


def test_le_ricette_conservate_arrivano_al_modello_come_contesto(
    client, diet, fake_ai, monkeypatch
):
    """Riempiendo un buco, il modello deve sapere cosa c'è già negli altri giorni,
    altrimenti propone lo stesso piatto due volte nella stessa settimana."""
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    week = client.get("/api/planning/weeks/current").json()
    meal_id = week["days"][0]["meals"][1]["id"]
    client.delete(f"/api/planning/meals/{meal_id}/recipe")

    spia = ContaChiamate(None)
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: spia)
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert "PASTI GIÀ ASSEGNATI" in spia.prompt
    assert "Pranzo 1 v1" in spia.prompt  # il pranzo di martedì, che non è stato toccato


def test_a_piano_bloccato_non_si_rigenera_niente(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    client.post("/api/shopping/current/complete")

    res = client.post(f"/api/planning/weeks/{week['id']}/generate?regenerate_all=true")
    assert res.status_code == 409
