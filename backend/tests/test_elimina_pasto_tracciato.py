"""Eliminare o rigenerare un pasto tracciato rimette gli ingredienti nella dispensa."""

import pytest

from tests.conftest import TEST_EMAIL


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    """Una settimana generata: ogni pranzo usa 100 g di pasta e 150 g di zucchine."""
    from app.services import planner
    from tests.test_flow import FakeModel

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def pranzo(settimana, dow=0) -> dict:
    return next(
        m for m in settimana["days"][dow]["meals"] if m["slot_name"] == "Pranzo"
    )


def scorta(client, nome: str):
    return next(
        (p for p in client.get("/api/config/pantry").json() if p["name"] == nome), None
    )


def test_eliminare_un_pasto_tracciato_rimette_gli_ingredienti_in_dispensa(
    client, settimana
):
    """Se ho segnato "l'ho seguito", gli ingredienti sono stati tolti dalla dispensa.
    Eliminando il pasto devo reimmettere quello che era stato tolto."""
    # Prepara la dispensa
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"},
    )

    # Segna il pasto come seguito: gli ingredienti vengono scalati
    mid = pranzo(settimana)["id"]
    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": True})

    assert scorta(client, "pasta")["quantity"] == 400  # 500 - 100

    # Elimina il pasto: gli ingredienti devono tornare
    res = client.delete(f"/api/planning/meals/{mid}/recipe")

    assert res.status_code == 200, res.text
    assert res.json()["recipe"] is None  # La casella è vuota
    assert scorta(client, "pasta")["quantity"] == 500  # Tornati i 100 g


def test_rigenerare_un_pasto_tracciato_rimette_gli_ingredienti_in_dispensa(
    client, settimana
):
    """Se ho segnato "l'ho seguito", gli ingredienti sono stati tolti dalla dispensa.
    Rigenerando il pasto devo reimmettere quello che era stato tolto."""
    # Prepara la dispensa
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"},
    )

    # Segna il pasto come seguito: gli ingredienti vengono scalati
    mid = pranzo(settimana)["id"]
    client.put(f"/api/planning/meals/{mid}/followed", json={"is_followed": True})

    assert scorta(client, "pasta")["quantity"] == 400  # 500 - 100

    # Rigenera il pasto: gli ingredienti devono tornare (la ricetta nuova avrà gli stessi)
    res = client.post(f"/api/planning/meals/{mid}/regenerate")

    assert res.status_code == 200, res.text
    assert res.json()["recipe"] is not None  # Nuovo piatto assegnato
    # Con la ricetta FakeModel (sempre la stessa), gli ingredienti sono identici
    assert (
        scorta(client, "pasta")["quantity"] == 400
    )  # FakeModel torna la stessa ricetta, che consume altri 100 g


def test_eliminare_pasto_non_tracciato_non_cambia_dispensa(client, settimana):
    """Se non ho segnato com'è andata, non c'è niente da reimmettere."""
    # Prepara la dispensa
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "pasta", "quantity": 500, "unit": "g"},
    )

    # Elimina il pasto senza segnarlo
    mid = pranzo(settimana)["id"]
    res = client.delete(f"/api/planning/meals/{mid}/recipe")

    assert res.status_code == 200, res.text
    assert scorta(client, "pasta")["quantity"] == 500  # Niente è stato cambiato
