"""La spesa comprende tutto il piano da oggi in avanti, non solo questa settimana.

La spesa segue il piano e non il calendario: se l'utente ha già generato anche la
settimana prossima, quegli ingredienti servono davvero e comprarli nello stesso giro è
tutto l'anti-spreco (una confezione sola invece di due mezze). Quanto avanti spingersi
lo decide lui, generando quello che vuole.

E siccome la lista è "quello che il piano chiede meno quello che c'è in casa", non ha
bisogno di essere chiusa: a spesa fatta si svuota da sé, perché la roba comprata è
finita in dispensa.
"""

import json
from datetime import timedelta

import pytest

from app.routers import chat as chat_router
from app.services import planner
from tests.test_chat import FakeChat
from tests.test_chat_spesa import _senza_zucchine
from tests.test_flow import FakeModel


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def questa(client, diet, fake_ai):
    """La settimana corrente, generata."""
    w = client.get("/api/planning/weeks/current").json()
    assert client.post(f"/api/planning/weeks/{w['id']}/generate").status_code == 200
    return w


@pytest.fixture()
def prossima(client, questa):
    """Anche la settimana dopo, generata: è la scelta esplicita dell'utente."""
    w = client.get("/api/planning/weeks/next").json()
    assert client.post(f"/api/planning/weeks/{w['id']}/generate").status_code == 200
    return w


def quantita(lst: dict, nome: str) -> float:
    return next(
        (i["quantity"] for c in lst["categories"] for i in c["items"] if i["name"] == nome), 0
    )


def spunta_tutto(client) -> dict:
    """Il giro al supermercato: si spunta riga per riga, come al banco."""
    lst = client.get("/api/shopping/current").json()
    for categoria in lst["categories"]:
        for item in categoria["items"]:
            client.put(f"/api/shopping/items/{item['id']}/check", json={"is_checked": True})
    return lst


# ── Copertura ──────────────────────────────────────────────────────────────────


def test_una_settimana_sola(client, questa):
    """Sette giorni generati, sette giorni di spesa."""
    lst = client.get("/api/shopping/current").json()

    assert quantita(lst, "pasta") == pytest.approx(7 * 100)
    assert lst["covers_from"] == planner.current_week_start().isoformat()
    assert lst["covers_to"] == (planner.current_week_start() + timedelta(days=6)).isoformat()


def test_la_lista_comprende_anche_la_settimana_generata_dopo(client, prossima):
    lst = client.get("/api/shopping/current").json()

    # Quattordici pranzi in programma, quattordici porzioni di pasta da comprare.
    assert quantita(lst, "pasta") == pytest.approx(14 * 100)
    assert lst["covers_to"] == (planner.next_week_start() + timedelta(days=6)).isoformat()


def test_una_settimana_creata_ma_vuota_non_pesa(client, questa):
    """La settimana prossima esiste ma è vuota: senza ricette non ha ingredienti."""
    client.get("/api/planning/weeks/next")

    lst = client.get("/api/shopping/current").json()
    assert quantita(lst, "pasta") == pytest.approx(7 * 100)
    assert lst["covers_to"] == (planner.current_week_start() + timedelta(days=6)).isoformat()


def test_la_dispensa_si_sottrae_una_volta_sola(client, prossima, db):
    """Due settimane in lista non raddoppiano lo sconto della dispensa."""
    from app.models import Ingredient, PantryItem, User

    user = db.query(User).first()
    pasta = db.query(Ingredient).filter(Ingredient.name == "pasta").first()
    db.add(PantryItem(user_id=user.id, ingredient_id=pasta.id, quantity_available=400, unit="g"))
    db.commit()

    lst = client.get("/api/shopping/current").json()
    assert quantita(lst, "pasta") == pytest.approx(14 * 100 - 400)


# ── Spesa fatta ────────────────────────────────────────────────────────────────


def test_la_spesa_fatta_svuota_la_lista(client, questa):
    """Non perché qualcuno la cancelli: quello che hai comprato adesso è in dispensa."""
    spunta_tutto(client)

    res = client.post("/api/shopping/current/complete")
    assert res.status_code == 200, res.text

    lst = client.get("/api/shopping/current").json()
    assert lst["total_items"] == 0
    assert lst["completed_at"] is not None
    assert any(p["name"] == "pasta" for p in client.get("/api/config/pantry").json())


def test_quello_che_non_hai_spuntato_resta_in_lista(client, questa):
    """Non l'hai comprato, quindi manca ancora: nessuno deve ricordarselo a mano."""
    lst = client.get("/api/shopping/current").json()
    tutti = [i for c in lst["categories"] for i in c["items"]]
    for item in tutti[1:]:
        client.put(f"/api/shopping/items/{item['id']}/check", json={"is_checked": True})

    client.post("/api/shopping/current/complete")

    dopo = client.get("/api/shopping/current").json()
    rimasti = [i["name"] for c in dopo["categories"] for i in c["items"]]
    assert rimasti == [tutti[0]["name"]]


def test_senza_niente_di_spuntato_non_si_conferma(client, questa):
    """Confermare senza aver preso niente svuoterebbe la lista senza riempire la dispensa."""
    res = client.post("/api/shopping/current/complete")

    assert res.status_code == 400
    assert client.get("/api/shopping/current").json()["total_items"] > 0


def test_una_settimana_nuova_rimette_in_lista_quello_che_manca(client, questa):
    """"Se genero una ricetta nuova me la aggiunge": non serve nessuna regola in più.

    Gli ingredienti della settimana appena generata in dispensa non ci sono, quindi
    compaiono; quelli comprati per questa restano coperti dalla scorta.
    """
    spunta_tutto(client)
    client.post("/api/shopping/current/complete")
    assert client.get("/api/shopping/current").json()["total_items"] == 0

    w = client.get("/api/planning/weeks/next").json()
    assert client.post(f"/api/planning/weeks/{w['id']}/generate").status_code == 200

    lst = client.get("/api/shopping/current").json()
    # Quattordici pranzi in piano, sette porzioni di pasta già in dispensa.
    assert quantita(lst, "pasta") == pytest.approx(7 * 100)


def test_a_spesa_fatta_le_ricette_si_cambiano_lo_stesso(client, questa):
    """Il blocco non c'è più: si corregge quando si vuole, la dispensa la si sistema a mano."""
    spunta_tutto(client)
    client.post("/api/shopping/current/complete")

    week = client.get("/api/planning/weeks/current").json()
    meal = week["days"][0]["meals"][0]
    altra = week["days"][1]["meals"][0]["recipe"]["id"]

    assert client.put(
        f"/api/planning/meals/{meal['id']}/assign", json={"recipe_id": altra}
    ).status_code == 200
    assert client.post(f"/api/planning/weeks/{week['id']}/generate?regenerate_all=true").status_code == 200


# ── Il piano cambia in una settimana, la lista è dell'altra ────────────────────


def test_generare_la_prossima_riallinea_la_lista_di_questa(client, questa):
    """La dashboard legge la lista senza ricostruirla: se generare la settimana
    prossima non toccasse la lista, resterebbe indietro di sette giorni."""
    client.get("/api/shopping/current")  # la lista esiste
    prima = client.get("/api/tracking/dashboard").json()["shopping"]

    w = client.get("/api/planning/weeks/next").json()
    client.post(f"/api/planning/weeks/{w['id']}/generate")

    dopo = client.get("/api/tracking/dashboard").json()["shopping"]
    # Stessi ingredienti (le righe non cambiano), ma il doppio della roba: è il costo
    # a dire se la lista si è davvero rifatta.
    assert dopo["total_items"] == prima["total_items"]
    assert dopo["estimated_cost"] == pytest.approx(prima["estimated_cost"] * 2, rel=0.05)


def test_la_chat_della_spesa_cambia_anche_i_pasti_della_prossima(client, prossima, monkeypatch):
    """Al supermercato non esistono le settimane: se le zucchine non si trovano, vanno
    tolte da tutte le ricette che quella spesa sta comprando."""
    settimana = client.get("/api/planning/weeks/next").json()
    pranzo = next(m for m in settimana["days"][0]["meals"] if m["slot_name"] == "Pranzo")

    data = {"meals": [{"meal_id": pranzo["id"], "recipe": _senza_zucchine()}]}
    fake = FakeChat(f"Fatto.\n[RECIPES_UPDATE]\n{json.dumps(data, ensure_ascii=False)}")
    monkeypatch.setattr(chat_router, "get_client", lambda db, user, role: fake)

    questa_settimana = client.get("/api/planning/weeks/current").json()
    res = client.post(
        f"/api/chat/shopping/{questa_settimana['id']}/messages",
        json={"content": "Non trovo le zucchine"},
    ).json()

    # Il modello ha visto un pasto della settimana prossima e l'ha potuto cambiare.
    assert len(res["changed_meals"]) == 1
    assert client.get(f"/api/planning/meals/{pranzo['id']}").json()["recipe"]["title"] == (
        "Pasta alle melanzane"
    )
    assert res["list_updated"] is True
