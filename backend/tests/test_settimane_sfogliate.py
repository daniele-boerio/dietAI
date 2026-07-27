"""Sfogliare il piano: indietro per rivedere, avanti per pianificare.

Prima si poteva stare solo su questa settimana o sulla prossima. Ora si va indietro
quanto si vuole — ma il passato si consulta e basta: non lo si crea sfogliandolo, e
non ci si spende una chiamata al modello.
"""

from datetime import date, timedelta

import pytest

from app.models import WeekPlan
from app.services import planner
from tests.test_flow import FakeModel


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def oggi(monkeypatch):
    """Sposta "oggi" di N giorni dal lunedì di questa settimana."""

    def imposta(offset_giorni: int) -> None:
        lunedi = planner.monday_of(date.today())
        monkeypatch.setattr(
            planner, "today", lambda: lunedi + timedelta(days=offset_giorni)
        )

    return imposta


def lunedi(settimane: int = 0) -> str:
    return (planner.monday_of(date.today()) + timedelta(weeks=settimane)).isoformat()


def test_una_data_qualsiasi_apre_la_sua_settimana(client, diet):
    """L'indirizzo porta un giorno, la risposta è la settimana che lo contiene."""
    mercoledi = (planner.monday_of(date.today()) + timedelta(days=2)).isoformat()
    week = client.get(f"/api/planning/weeks/by-date/{mercoledi}").json()

    assert week["week_start_date"] == lunedi(0)
    assert week["is_current"] is True
    assert week["is_past"] is False
    assert len(week["days"]) == 7


def test_avanti_la_settimana_nasce_quando_la_si_apre(client, diet):
    """Quanto avanti pianificare lo decide l'utente: nessun tetto."""
    week = client.get(f"/api/planning/weeks/by-date/{lunedi(5)}").json()

    assert week["id"] is not None
    assert week["is_past"] is False
    assert len(week["days"]) == 7


def test_una_settimana_passata_mai_pianificata_resta_vuota(client, diet, db):
    """Sfogliare all'indietro non deve riempire l'archivio di settimane mai vissute."""
    week = client.get(f"/api/planning/weeks/by-date/{lunedi(-3)}").json()

    assert week["id"] is None
    assert week["is_past"] is True
    assert week["days"] == []
    assert db.query(WeekPlan).filter(WeekPlan.week_start_date < date.today()).count() == 0


def test_la_settimana_scorsa_si_rilegge_intera(client, diet, oggi):
    prima = client.get("/api/planning/weeks/current").json()
    oggi(7)  # una settimana dopo: quella di prima è passata

    passata = client.get(f"/api/planning/weeks/by-date/{lunedi(0)}").json()

    assert passata["id"] == prima["id"]
    assert passata["is_past"] is True
    assert passata["is_current"] is False
    assert len(passata["days"]) == 7


def test_anche_il_passato_si_modifica(client, diet, oggi, fake_ai):
    """Le ricette si cambiano quando si vuole, anche quelle di una settimana finita.

    La spesa non ne risente: la lista guarda da oggi in avanti, quindi rifare la
    settimana scorsa non rimette niente nel carrello.
    """
    prima = client.post(
        f"/api/planning/weeks/{client.get('/api/planning/weeks/current').json()['id']}/generate"
    ).json()
    meal = prima["days"][0]["meals"][0]
    altra = prima["days"][1]["meals"][0]["recipe"]["id"]
    oggi(7)

    assert client.put(
        f"/api/planning/meals/{meal['id']}/assign", json={"recipe_id": altra}
    ).status_code == 200
    assert client.post(f"/api/planning/weeks/{prima['id']}/generate?regenerate_all=true").status_code == 200
    # E la spesa non ne risente: guarda da oggi in avanti, e quella settimana è finita.
    assert client.get("/api/shopping/current").json()["total_items"] == 0


def test_il_pasto_passato_si_puo_ancora_tracciare(client, diet, oggi):
    """È il motivo per cui si torna indietro: segnare com'è andata."""
    prima = client.get("/api/planning/weeks/current").json()
    meal_id = prima["days"][0]["meals"][0]["id"]
    oggi(7)

    res = client.put(f"/api/planning/meals/{meal_id}/followed", json={"is_followed": True})
    assert res.status_code == 200, res.text
    assert res.json()["is_followed"] is True
    assert res.json()["week"]["is_past"] is True
