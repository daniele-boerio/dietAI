"""La spesa copre tutte le settimane generate, non solo quella corrente.

Il punto è che la spesa segue il piano e non il calendario: se l'utente ha già
generato anche la settimana prossima, quegli ingredienti servono davvero e comprarli
nello stesso giro è tutto il senso dell'anti-spreco (una confezione sola invece di
due mezze). Quanto avanti spingersi lo decide lui, generando quello che vuole.

La conseguenza pesante è il blocco: se la spesa comprendeva due settimane, a spesa
fatta sono bloccate entrambe — quel cibo è comprato, cambiarne le ricette è buttarlo.
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


# ── Copertura ──────────────────────────────────────────────────────────────────


def test_una_settimana_sola_resta_come_prima(client, questa):
    """Senza altre settimane generate non cambia niente: sette giorni di spesa."""
    lst = client.get("/api/shopping/current").json()

    assert quantita(lst, "pasta") == pytest.approx(7 * 100)
    assert len(lst["weeks_covered"]) == 1


def test_la_lista_comprende_anche_la_settimana_generata_dopo(client, prossima):
    lst = client.get("/api/shopping/current").json()

    # Quattordici pranzi in programma, quattordici porzioni di pasta da comprare.
    assert quantita(lst, "pasta") == pytest.approx(14 * 100)
    assert [w["week_start_date"] for w in lst["weeks_covered"]] == [
        planner.current_week_start().isoformat(),
        planner.next_week_start().isoformat(),
    ]
    assert lst["covers_to"] == (planner.next_week_start() + timedelta(days=6)).isoformat()


def test_una_settimana_creata_ma_vuota_non_pesa(client, questa):
    """La settimana prossima esiste (aperta o creata dallo slittamento) ma è vuota:
    senza ricette non ha ingredienti, quindi la lista resta quella di prima."""
    client.get("/api/planning/weeks/next")

    lst = client.get("/api/shopping/current").json()
    assert quantita(lst, "pasta") == pytest.approx(7 * 100)
    assert len(lst["weeks_covered"]) == 1


def test_una_settimana_vuota_non_viene_bloccata_dalla_spesa(client, questa):
    """Il caso che rende la regola pericolosa se scritta male: la settimana prossima
    è stata solo aperta, non generata. Se la spesa la bloccasse, l'utente non
    potrebbe più generarla — e proprio nel momento in cui vuole farlo."""
    prossima_vuota = client.get("/api/planning/weeks/next").json()

    assert client.post("/api/shopping/current/complete").json()["weeks_locked"] == 1

    assert client.get("/api/planning/weeks/next").json()["is_locked"] is False
    assert client.post(f"/api/planning/weeks/{prossima_vuota['id']}/generate").status_code == 200


def test_la_dispensa_si_sottrae_una_volta_sola(client, prossima, db):
    """Due settimane in lista non raddoppiano lo sconto della dispensa."""
    from app.models import Ingredient, PantryItem, User

    user = db.query(User).first()
    pasta = db.query(Ingredient).filter(Ingredient.name == "pasta").first()
    db.add(PantryItem(user_id=user.id, ingredient_id=pasta.id, quantity_available=400, unit="g"))
    db.commit()

    lst = client.get("/api/shopping/current").json()
    assert quantita(lst, "pasta") == pytest.approx(14 * 100 - 400)


# ── Blocco ─────────────────────────────────────────────────────────────────────


def test_la_spesa_fatta_blocca_tutte_le_settimane_comprate(client, prossima):
    res = client.post("/api/shopping/current/complete")

    assert res.status_code == 200, res.text
    assert res.json()["weeks_locked"] == 2

    # Il cibo della settimana prossima è comprato: quel piano non si tocca più.
    assert client.post(f"/api/planning/weeks/{prossima['id']}/generate").status_code == 409
    assert client.get("/api/planning/weeks/next").json()["is_locked"] is True


def test_il_blocco_della_prossima_arriva_fino_alla_sua_fine(client, prossima):
    """Sette giorni contati da oggi scadrebbero prima che la settimana cominci: il
    piano tornerebbe modificabile con gli ingredienti già in frigo."""
    client.post("/api/shopping/current/complete")

    questa_scadenza = client.get("/api/planning/weeks/current").json()["lock_expires_at"]
    prossima_scadenza = client.get("/api/planning/weeks/next").json()["lock_expires_at"]

    assert prossima_scadenza > questa_scadenza
    assert prossima_scadenza.startswith(
        (planner.next_week_start() + timedelta(days=7)).isoformat()
    )


def test_quello_che_è_già_comprato_non_torna_in_lista(client, prossima):
    """Comprate due settimane non c'è una nuova spesa da fare: resta quella fatta.

    La settimana prossima è pagata con questa spesa, quindi non deve ricomparire come
    lista da comprare — sarebbe lo stesso cibo due volte.
    """
    client.post("/api/shopping/current/complete")

    lst = client.get("/api/shopping/current").json()
    assert lst["is_completed"] is True
    assert lst["week_start_date"] == planner.current_week_start().isoformat()
    assert client.post("/api/shopping/current/complete").status_code == 409


def test_dopo_la_spesa_si_riparte_dalla_settimana_ancora_da_comprare(client, questa):
    """Comprata questa, la spesa si sposta da sola sulla prossima appena la generi.

    Di liste aperte ce n'è una sola: non c'è una scheda da cambiare, la lista mostra
    sempre la prima settimana che ha ancora qualcosa da comprare.
    """
    client.post("/api/shopping/current/complete")

    w = client.get("/api/planning/weeks/next").json()
    assert client.post(f"/api/planning/weeks/{w['id']}/generate").status_code == 200

    lst = client.get("/api/shopping/current").json()
    assert lst["is_completed"] is False
    assert lst["week_start_date"] == planner.next_week_start().isoformat()
    assert lst["starts_ahead"] is True
    assert quantita(lst, "pasta") == pytest.approx(7 * 100)


def test_finche_non_c_è_niente_da_comprare_la_lista_resta_questa(client, questa):
    """La settimana prossima esiste ma è vuota: non ha senso mostrarla come spesa.

    Se bastasse esistere, subito dopo aver comprato ci si ritroverebbe davanti una
    lista vuota della settimana prossima al posto della conferma della spesa fatta.
    """
    client.post("/api/shopping/current/complete")
    client.get("/api/planning/weeks/next")  # aperta, non generata

    lst = client.get("/api/shopping/current").json()
    assert lst["is_completed"] is True
    assert lst["week_start_date"] == planner.current_week_start().isoformat()


# ── Il piano cambia in una settimana, la lista è dell'altra ────────────────────


def test_generare_la_prossima_riallinea_la_lista_di_questa(client, questa):
    """La dashboard legge la lista senza ricostruirla: se generare la settimana
    prossima non toccasse la lista di questa, resterebbe indietro di sette giorni."""
    client.get("/api/shopping/current")  # la lista di questa settimana esiste
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
