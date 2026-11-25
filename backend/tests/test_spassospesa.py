"""SpassoSpesa: la lista della spesa di casa legge la nostra e rimette in dispensa.

Le rotte non hanno sessione: le protegge il token condiviso, e l'utente lo dice la
mail. Senza token configurato non esistono (404); col token sbagliato 401.
"""

import pytest

from app import config
from tests.conftest import GUEST_EMAIL, TEST_EMAIL
from tests.test_spesa_multisettimana import fake_ai, questa  # noqa: F401 - fixture

TOKEN = "token-condiviso-di-test"
H = {"Authorization": f"Bearer {TOKEN}"}
BASE = "/api/integrazioni/spassospesa"


@pytest.fixture()
def token(monkeypatch):
    monkeypatch.setattr(config, "SPASSOSPESA_TOKEN", TOKEN)


def test_senza_token_configurato_le_rotte_non_esistono(client):
    assert client.get(f"{BASE}/account", params={"email": TEST_EMAIL}, headers=H).status_code == 404


def test_token_sbagliato(client, token):
    r = client.get(f"{BASE}/account", params={"email": TEST_EMAIL}, headers={"Authorization": "Bearer altro"})
    assert r.status_code == 401


def test_account(client, token):
    assert client.get(f"{BASE}/account", params={"email": TEST_EMAIL.upper()}, headers=H).json() == {"exists": True}
    assert client.get(f"{BASE}/account", params={"email": "nessuno@x.it"}, headers=H).json() == {"exists": False}


def test_lista_e_dispensa(client, token, questa):  # noqa: F811
    lst = client.get(f"{BASE}/lista", params={"email": TEST_EMAIL}, headers=H)
    assert lst.status_code == 200, lst.text
    items = lst.json()["items"]
    assert items and all(i["ingredient_id"] and i["label"] for i in items)
    pasta = next(i for i in items if i["name"] == "Pasta")

    body = {
        "email": TEST_EMAIL,
        "items": [
            {"ingredient_id": pasta["ingredient_id"], "name": "Pasta", "quantity": pasta["quantity"], "unit": pasta["unit"]},
            {"name": "Detersivo piatti", "label": "1"},
        ],
    }
    r = client.post(f"{BASE}/dispensa", json=body, headers=H)
    assert r.status_code == 200, r.text
    assert r.json() == {"stored": ["pasta"], "skipped": ["Detersivo piatti"]}

    # In dispensa, e quindi fuori dalla lista di dietAI.
    assert any(p["name"] == "pasta" for p in client.get("/api/config/pantry").json())
    dopo = client.get(f"{BASE}/lista", params={"email": TEST_EMAIL}, headers=H).json()["items"]
    assert "Pasta" not in [i["name"] for i in dopo]


def test_un_nome_senza_quantita_prende_quella_della_lista(client, token, questa):  # noqa: F811
    items = client.get(f"{BASE}/lista", params={"email": TEST_EMAIL}, headers=H).json()["items"]
    primo = items[0]
    r = client.post(f"{BASE}/dispensa", json={"email": TEST_EMAIL, "items": [{"name": primo["name"]}]}, headers=H)
    assert r.json()["stored"] == [primo["name"].lower()]
    scorta = next(p for p in client.get("/api/config/pantry").json() if p["name"] == primo["name"].lower())
    assert scorta["quantity"] == pytest.approx(primo["quantity"])


def test_la_dispensa_e_di_chi_dice_la_mail(client, guest_client, token, questa):  # noqa: F811
    items = client.get(f"{BASE}/lista", params={"email": TEST_EMAIL}, headers=H).json()["items"]
    client.post(f"{BASE}/dispensa", json={"email": GUEST_EMAIL, "items": [{"ingredient_id": items[0]["ingredient_id"], "label": "2"}]}, headers=H)
    assert client.get("/api/config/pantry").json() == []
    assert len(guest_client.get("/api/config/pantry").json()) == 1


def test_mail_sconosciuta(client, token):
    assert client.get(f"{BASE}/lista", params={"email": "x@y.it"}, headers=H).status_code == 404
    assert client.post(f"{BASE}/dispensa", json={"email": "x@y.it", "items": []}, headers=H).status_code == 404
