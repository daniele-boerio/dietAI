"""Il promemoria serale: arriva all'ora scelta, una volta, e solo se serve.

Una notifica che non chiede niente insegna a ignorare le notifiche: per questo il
giro manda solo a chi oggi ha ancora pasti da segnare.
"""

from datetime import datetime, time

import pytest

from app.services import planner, push
from tests.test_flow import FakeModel

ISCRIZIONE = {
    "endpoint": "https://push.example.com/abc123",
    "keys": {"p256dh": "BFakeP256dhKeyForTests", "auth": "fakeAuth"},
}


@pytest.fixture()
def inviate(monkeypatch):
    """Le notifiche non escono: si mettono in un elenco."""
    elenco = []

    def finta(db, user_id, payload):
        elenco.append((user_id, payload))
        return 1

    monkeypatch.setattr(push, "send", finta)
    return elenco


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    return client.post(f"/api/planning/weeks/{week['id']}/generate").json()


def alle(hh, mm):
    return datetime.combine(planner.today(), time(hh, mm), tzinfo=push.FUSO)


def test_la_chiave_pubblica_e_stabile_e_della_forma_giusta(client):
    a = client.get("/api/push").json()["public_key"]
    b = client.get("/api/push").json()["public_key"]
    assert a == b
    assert len(a) == 87  # 65 byte di punto non compresso, in base64url senza padding


def test_iscriversi_e_disiscriversi(client):
    assert client.post("/api/push/subscribe", json=ISCRIZIONE).json()["devices"] == 1
    # Lo stesso dispositivo due volte resta un dispositivo.
    assert client.post("/api/push/subscribe", json=ISCRIZIONE).json()["devices"] == 1
    res = client.post("/api/push/unsubscribe", json={"endpoint": ISCRIZIONE["endpoint"]})
    assert res.json()["devices"] == 0


def test_il_dispositivo_segue_chi_e_loggato(client, guest_client):
    client.post("/api/push/subscribe", json=ISCRIZIONE)
    guest_client.post("/api/push/subscribe", json=ISCRIZIONE)
    assert client.get("/api/push").json()["devices"] == 0
    assert guest_client.get("/api/push").json()["devices"] == 1


def test_l_ora_si_valida(client):
    assert client.put("/api/push/reminder", json={"time": "25:00"}).status_code == 400
    assert client.put("/api/push/reminder", json={"time": "21:30"}).json()["reminder_time"] == "21:30"
    assert client.put("/api/push/reminder", json={"time": None}).json()["reminder_time"] is None


def test_il_promemoria_arriva_all_ora_e_una_volta_sola(client, settimana, db, inviate):
    client.put("/api/push/reminder", json={"time": "21:00"})

    assert push.send_due_reminders(db, alle(20, 59)) == 0
    assert push.send_due_reminders(db, alle(21, 0)) == 1
    assert push.send_due_reminders(db, alle(21, 1)) == 0  # già fatto oggi

    _, payload = inviate[0]
    assert payload["title"] == "Com'è andata oggi?"
    assert "3 pasti" in payload["body"]


def test_chi_ha_gia_risposto_a_tutto_non_riceve_niente(client, settimana, db, inviate):
    for m in settimana["days"][0]["meals"]:
        client.put(f"/api/planning/meals/{m['id']}/followed", json={"is_followed": True})
    client.put("/api/push/reminder", json={"time": "21:00"})

    assert push.send_due_reminders(db, alle(21, 30)) == 0
    assert inviate == []


def test_spostare_l_ora_rimette_in_gioco_il_promemoria_di_oggi(client, settimana, db, inviate):
    client.put("/api/push/reminder", json={"time": "20:00"})
    push.send_due_reminders(db, alle(20, 0))
    client.put("/api/push/reminder", json={"time": "22:00"})

    assert push.send_due_reminders(db, alle(22, 0)) == 1


def test_senza_dispositivi_la_prova_lo_dice(client):
    assert client.post("/api/push/test").status_code == 400


def test_la_notifica_esce_cifrata_e_firmata(client, db, monkeypatch):
    """Il giro vero di `push.send`, fino alla richiesta HTTP esclusa: chiavi del
    browser generate qui, firma VAPID derivata dalla SECRET_KEY, payload cifrato."""
    import base64

    import requests
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    def b64(b):
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    browser = ec.generate_private_key(ec.SECP256R1())
    client.post("/api/push/subscribe", json={
        "endpoint": "https://fcm.googleapis.com/fcm/send/prova",
        "keys": {
            "p256dh": b64(browser.public_key().public_bytes(
                Encoding.X962, PublicFormat.UncompressedPoint)),
            "auth": b64(b"0123456789abcdef"),
        },
    })

    chiamate = []

    class Risposta:
        status_code = 201
        text = ""

    def finto_post(url, data=None, headers=None, **kw):
        chiamate.append((url, data, headers))
        return Risposta()

    monkeypatch.setattr(requests, "post", finto_post)

    assert push.send(db, 1, {"title": "x", "body": "y"}) == 1
    url, corpo, intestazioni = chiamate[0]
    assert url.startswith("https://fcm.googleapis.com/")
    assert intestazioni["content-encoding"] == "aes128gcm"
    assert intestazioni["authorization"].startswith("vapid t=")
    assert b"title" not in corpo  # cifrato
