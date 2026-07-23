"""Pasti saltati a mano: "ho mangiato altro" manda la ricetta in fondo alla coda.

È il caso opposto ai giorni saltati per mancata spesa. Lì il cibo non era mai stato
comprato e il piano intero slitta; qui la spesa è fatta, gli ingredienti sono in
frigo, e allora il piatto non cucinato non si perde: si accoda alla prima casella
libera di quel pasto, senza spostare nient'altro.
"""

from datetime import date, timedelta

import pytest

from app.services import planner
from tests.test_flow import DAYS, FakeModel  # noqa: F401


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def settimana_generata(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def pasto(week: dict, dow: int, slot: str) -> dict:
    return next(m for m in week["days"][dow]["meals"] if m["slot_name"] == slot)


def titoli(week: dict, slot: str = "Cena") -> list:
    return [
        (pasto(week, d, slot)["recipe"] or {}).get("title") for d in range(len(week["days"]))
    ]


# ── Accodamento ────────────────────────────────────────────────────────────────


def test_ho_mangiato_altro_manda_la_ricetta_in_fondo(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")

    res = client.put(
        f"/api/planning/meals/{cena['id']}/followed",
        json={"is_followed": False, "deviation_notes": "pizza fuori"},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["is_skipped"] is True
    # La settimana è piena: la prima casella libera è il lunedì della prossima.
    assert body["moved_to"]["day_name"] == "Lunedì"
    assert body["moved_to"]["next_week"] is True

    nxt = client.get("/api/planning/weeks/next").json()
    assert pasto(nxt, 0, "Cena")["recipe"]["title"] == "Cena 0"


def test_gli_altri_giorni_non_si_muovono(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    week = client.get("/api/planning/weeks/current").json()

    # Nessuno slittamento a catena: da martedì in poi tutto com'era.
    assert titoli(week)[1:] == [f"Cena {i}" for i in range(1, DAYS)]
    # E la casella saltata conserva la ricetta come memoria di cosa c'era.
    assert pasto(week, 0, "Cena")["recipe"]["title"] == "Cena 0"
    assert pasto(week, 0, "Cena")["is_skipped"] is True


def test_se_c_e_un_buco_prima_la_ricetta_va_li(client, settimana_generata):
    """Meglio giovedì che lunedì prossimo: si mangia prima e non si sposta nulla."""
    giovedi = pasto(settimana_generata, 3, "Cena")
    assert client.delete(f"/api/planning/meals/{giovedi['id']}/recipe").status_code == 200

    lunedi = pasto(settimana_generata, 0, "Cena")
    res = client.put(f"/api/planning/meals/{lunedi['id']}/followed", json={"is_followed": False})
    assert res.json()["moved_to"]["day_name"] == "Giovedì"

    week = client.get("/api/planning/weeks/current").json()
    assert titoli(week)[3] == "Cena 0"


def test_l_ho_seguito_riporta_indietro_la_ricetta(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    res = client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": True})
    assert res.status_code == 200
    assert res.json()["is_skipped"] is False

    # La casella dove si era accodata torna vuota.
    nxt = client.get("/api/planning/weeks/next").json()
    assert pasto(nxt, 0, "Cena")["recipe"] is None
    assert titoli(client.get("/api/planning/weeks/current").json()) == [
        f"Cena {i}" for i in range(DAYS)
    ]


def test_un_pasto_fisso_non_si_accoda(client, settimana_generata):
    """Un piatto che l'utente ha ancorato a quel giorno resta lì: si segna e basta."""
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(
        f"/api/planning/meals/{cena['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": {"type": "weekly", "day": 0}},
    )

    res = client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})
    assert res.json()["moved_to"] is None

    nxt = client.get("/api/planning/weeks/next").json()
    # Nella prossima c'è la copia del pasto fisso, non un accodamento.
    assert pasto(nxt, 0, "Cena")["is_recurring"] is True


# ── A spesa fatta ──────────────────────────────────────────────────────────────


def test_funziona_anche_a_piano_bloccato(client, settimana_generata):
    """È il caso per cui esiste: il cibo è comprato, il piatto si sposta e basta."""
    assert client.post("/api/shopping/current/complete").status_code == 200

    cena = pasto(settimana_generata, 0, "Cena")
    res = client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})
    assert res.status_code == 200
    assert res.json()["moved_to"]["next_week"] is True

    week = client.get("/api/planning/weeks/current").json()
    assert week["is_locked"] is True
    assert titoli(week)[1:] == [f"Cena {i}" for i in range(1, DAYS)]


# ── Effetti sul resto dell'app ─────────────────────────────────────────────────


def test_il_pasto_saltato_esce_dalla_lista_della_spesa(client, settimana_generata):
    prima = client.get("/api/shopping/current").json()
    pollo_prima = next(
        i for cat in prima["categories"] for i in cat["items"] if i["name"] == "petto di pollo"
    )

    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    dopo = client.get("/api/shopping/current").json()
    pollo_dopo = next(
        i for cat in dopo["categories"] for i in cat["items"] if i["name"] == "petto di pollo"
    )
    # Una cena in meno: 150 g di pollo che non si comprano più questa settimana.
    assert pollo_dopo["quantity"] == pytest.approx(pollo_prima["quantity"] - 150)


def test_i_totali_del_giorno_scendono_col_pasto_saltato(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    day = client.get("/api/planning/weeks/current").json()["days"][0]
    # 1700 - 600: cala il pianificato ma anche il target, o il giorno sembrerebbe
    # un fallimento invece di una cena in meno messa in programma.
    assert day["totals"]["calories"] == 1100
    assert day["totals"]["target_calories"] == 1100


def test_il_tracking_non_conta_il_pasto_saltato(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    tracking = client.get("/api/tracking/weekly").json()
    riga = next(m for m in tracking["days"][0]["meals"] if m["slot_name"] == "Cena")

    assert riga["is_skipped"] is True
    assert riga["color"] == "grey"
    assert tracking["days"][0]["totals"]["color"] == "green"  # non è un giorno andato male
    assert tracking["weekly_summary"]["compliance_pct"] == 100.0
    assert tracking["weekly_summary"]["meals_planned"] == DAYS * 3 - 1


def test_rigenera_tutto_non_ripesca_il_pasto_saltato(client, settimana_generata):
    cena = pasto(settimana_generata, 0, "Cena")
    client.put(f"/api/planning/meals/{cena['id']}/followed", json={"is_followed": False})

    res = client.post(
        f"/api/planning/weeks/{settimana_generata['id']}/generate", params={"regenerate_all": True}
    )
    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == DAYS * 3 - 1

    week = client.get("/api/planning/weeks/current").json()
    assert pasto(week, 0, "Cena")["is_skipped"] is True


# ── Giornata intera ────────────────────────────────────────────────────────────


def test_saltare_il_giorno_accoda_tutti_i_suoi_pasti(client, settimana_generata):
    sabato = settimana_generata["days"][5]

    res = client.put(f"/api/planning/days/{sabato['id']}/skip", json={"is_skipped": True})
    assert res.status_code == 200, res.text
    week = res.json()

    assert week["days"][5]["is_skipped"] is True
    assert all(m["is_skipped"] for m in week["days"][5]["meals"])
    assert week["meals_total"] == (DAYS - 1) * 3

    # Le tre ricette del sabato aprono la settimana prossima, una per pasto.
    nxt = client.get("/api/planning/weeks/next").json()
    assert [m["recipe"]["title"] for m in nxt["days"][0]["meals"]] == [
        "Colazione 5",
        "Pranzo 5",
        "Cena 5",
    ]


def test_rimettere_il_giorno_riporta_indietro_le_ricette(client, settimana_generata):
    sabato = settimana_generata["days"][5]
    client.put(f"/api/planning/days/{sabato['id']}/skip", json={"is_skipped": True})

    res = client.put(f"/api/planning/days/{sabato['id']}/skip", json={"is_skipped": False})
    assert res.status_code == 200
    week = res.json()

    assert week["days"][5]["is_skipped"] is False
    assert titoli(week) == [f"Cena {i}" for i in range(DAYS)]

    nxt = client.get("/api/planning/weeks/next").json()
    assert all(m["recipe"] is None for m in nxt["days"][0]["meals"])


def test_un_giorno_gia_passato_non_si_salta_a_mano(client, settimana_generata, monkeypatch):
    """I giorni passati li gestisce lo slittamento della spesa, non questo comando."""
    lunedi = planner.monday_of(date.today())
    monkeypatch.setattr(planner, "today", lambda: lunedi + timedelta(days=3))

    res = client.put(
        f"/api/planning/days/{settimana_generata['days'][0]['id']}/skip",
        json={"is_skipped": True},
    )
    assert res.status_code == 409
