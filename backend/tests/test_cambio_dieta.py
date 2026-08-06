"""Cambiare dieta a settimana già avviata: la griglia segue, non si somma.

Il caso che ha rotto: una dieta c'era già (PDF o inserita a mano), la settimana era in
piedi, e poi si usa «Calcola i macro dai tuoi dati». Il questionario non modifica i
pasti esistenti — crea una dieta nuova con `MealSlot` nuovi — e alle caselle di prima,
che puntano ancora ai vecchi, se ne aggiungevano altre sette per pasto: due colazioni,
due pranzi, due cene, tutti i giorni.
"""

import pytest

from app.services import planner
from tests.test_flow import FakeModel  # noqa: F401

QUESTIONARIO = {
    "sex": "uomo",
    "age": 30,
    "height_cm": 180,
    "weight_kg": 80,
    "activity": "moderato",
    "goal": "mantenere",
    "meals": ["colazione", "pranzo", "cena"],
}


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def settimana_generata(client, diet, fake_ai):
    """Una settimana piena di ricette, sulla dieta a tre pasti inserita a mano."""
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def pasti(week: dict, dow: int = 0) -> list[str]:
    return [m["slot_name"] for m in week["days"][dow]["meals"]]


def pasto(week: dict, dow: int, slot: str) -> dict:
    return next(m for m in week["days"][dow]["meals"] if m["slot_name"] == slot)


# ── Le caselle non si sommano ──────────────────────────────────────────────────


def test_ricalcolare_i_macro_non_raddoppia_i_pasti(client, settimana_generata):
    client.post("/api/diet/questionnaire", json=QUESTIONARIO)

    week = client.get("/api/planning/weeks/current").json()

    assert pasti(week) == ["Colazione", "Pranzo", "Cena"]
    assert all(len(giorno["meals"]) == 3 for giorno in week["days"])


def test_la_ricetta_gia_generata_resta_al_suo_posto(client, settimana_generata):
    """La settimana era già stata pagata: cambiano i target, non il piano."""
    prima = pasto(settimana_generata, 2, "Pranzo")

    dieta = client.post("/api/diet/questionnaire", json=QUESTIONARIO).json()
    dopo = pasto(client.get("/api/planning/weeks/current").json(), 2, "Pranzo")

    assert dopo["recipe"]["title"] == prima["recipe"]["title"]
    # Il pasto è quello della dieta nuova, coi suoi numeri.
    nuovo_slot = next(m for m in dieta["meals"] if m["name"] == "Pranzo")
    assert dopo["slot_id"] == nuovo_slot["id"]
    assert dopo["target"]["calories"] == nuovo_slot["calories"]


def test_quello_che_era_gia_segnato_non_si_perde(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": True})

    client.post("/api/diet/questionnaire", json=QUESTIONARIO)
    dopo = pasto(client.get("/api/planning/weeks/current").json(), 0, "Cena")

    assert dopo["is_followed"] is True
    assert dopo["id"] == cena["id"]


def test_la_spesa_non_chiede_due_volte_le_stesse_cose(client, settimana_generata):
    prima = client.get("/api/shopping/current").json()
    quantita = {i["name"]: i["quantity"] for c in prima["categories"] for i in c["items"]}

    client.post("/api/diet/questionnaire", json=QUESTIONARIO)
    client.get("/api/planning/weeks/current")

    dopo = client.get("/api/shopping/current").json()
    assert {
        i["name"]: i["quantity"] for c in dopo["categories"] for i in c["items"]
    } == quantita


# ── Un pasto che non si fa più ─────────────────────────────────────────────────


def test_un_pasto_tolto_dalla_dieta_esce_dalla_griglia(client, settimana_generata):
    """Chi la colazione smette di farla non deve ritrovarsela in piano tutti i giorni."""
    client.post(
        "/api/diet/questionnaire", json={**QUESTIONARIO, "meals": ["pranzo", "cena"]}
    )

    week = client.get("/api/planning/weeks/current").json()

    assert pasti(week) == ["Pranzo", "Cena"]
    assert week["meals_total"] == 14


def test_un_pasto_aggiunto_arriva_vuoto(client, settimana_generata):
    dieta = client.post(
        "/api/diet/questionnaire",
        json={**QUESTIONARIO, "meals": ["colazione", "pranzo", "spuntino_pomeriggio", "cena"]},
    ).json()

    week = client.get("/api/planning/weeks/current").json()

    assert pasti(week) == ["Colazione", "Pranzo", "Spuntino pomeriggio", "Cena"]
    assert pasto(week, 0, "Spuntino pomeriggio")["recipe"] is None
    # E gli altri tre restano pieni: la generazione successiva riempie solo il buco.
    assert len(dieta["meals"]) == 4
    assert week["meals_filled"] == 21


# ── Il caso senza settimana aperta ─────────────────────────────────────────────


def test_senza_una_settimana_gia_letta_non_cambia_niente(client, diet):
    """Il riallineamento non deve inventare caselle dove non c'era ancora niente."""
    client.post("/api/diet/questionnaire", json=QUESTIONARIO)

    week = client.get("/api/planning/weeks/current").json()
    assert pasti(week) == ["Colazione", "Pranzo", "Cena"]
    assert week["meals_filled"] == 0
