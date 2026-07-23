"""Giorni saltati: il piano segue la spesa, non il calendario.

La regola è quella che rende utile la lista della spesa: se lunedì non sei andato a
fare la spesa, lunedì non hai cucinato quello che c'era in piano. Comprare mercoledì
gli ingredienti di lunedì è spreco puro, quindi il giorno si salta e le ricette
scalano in avanti — fino a traboccare sulla settimana dopo. Quando la spesa la fai,
tutto si congela com'è.
"""

from datetime import date, timedelta

import pytest

from app.services import planner
from tests.test_flow import DAYS, FakeModel  # noqa: F401  (fake_ai usa FakeModel)


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def oggi(monkeypatch):
    """Sposta "oggi" dentro la settimana corrente: 0 = lunedì, 2 = mercoledì."""
    lunedi = planner.monday_of(date.today())

    def imposta(offset: int) -> None:
        monkeypatch.setattr(planner, "today", lambda: lunedi + timedelta(days=offset))

    return imposta


@pytest.fixture()
def settimana_generata(client, diet, fake_ai):
    """Una settimana piena, generata di lunedì: Pranzo 0 … Pranzo 6."""
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return res.json()


def titoli(week: dict, slot: str = "Pranzo") -> list:
    """I titoli di quello slot giorno per giorno, None dove la casella è vuota."""
    out = []
    for day in week["days"]:
        meal = next(m for m in day["meals"] if m["slot_name"] == slot)
        out.append(meal["recipe"]["title"] if meal["recipe"] else None)
    return out


# ── Slittamento ────────────────────────────────────────────────────────────────


def test_i_giorni_passati_senza_spesa_si_saltano(client, settimana_generata, oggi):
    oggi(2)  # mercoledì, spesa mai fatta
    week = client.get("/api/planning/weeks/current").json()

    assert [d["is_skipped"] for d in week["days"]] == [True, True, False, False, False, False, False]
    assert week["days_skipped"] == 2


def test_le_ricette_slittano_in_avanti(client, settimana_generata, oggi):
    assert titoli(settimana_generata) == [f"Pranzo {i}" for i in range(DAYS)]

    oggi(2)
    week = client.get("/api/planning/weeks/current").json()

    # Quello che era di lunedì si mangia mercoledì, e a scalare fino a domenica.
    assert titoli(week) == [None, None, "Pranzo 0", "Pranzo 1", "Pranzo 2", "Pranzo 3", "Pranzo 4"]


def test_le_ricette_in_eccedenza_passano_alla_settimana_dopo(
    client, settimana_generata, oggi
):
    oggi(2)
    client.get("/api/planning/weeks/current")

    nxt = client.get("/api/planning/weeks/next").json()
    assert titoli(nxt)[:2] == ["Pranzo 5", "Pranzo 6"]
    # Il resto della settimana prossima resta da generare: non si inventa niente.
    assert titoli(nxt)[2:] == [None] * 5


def test_slittare_due_giorni_di_fila_non_scambia_l_ordine(
    client, settimana_generata, oggi
):
    """Il caso che il flag `is_shifted` esiste per risolvere.

    Martedì "Pranzo 6" trabocca sul lunedì dopo. Mercoledì slitta di nuovo tutto: se
    la ricetta già traboccata non rientrasse in fila, "Pranzo 5" le finirebbe davanti
    e la settimana prossima si aprirebbe con i piatti in ordine inverso.
    """
    oggi(1)
    client.get("/api/planning/weeks/current")
    assert titoli(client.get("/api/planning/weeks/next").json())[:1] == ["Pranzo 6"]

    oggi(2)
    client.get("/api/planning/weeks/current")

    nxt = client.get("/api/planning/weeks/next").json()
    assert titoli(nxt)[:2] == ["Pranzo 5", "Pranzo 6"]


def test_un_pasto_fisso_non_slitta(client, settimana_generata, oggi):
    """La pizza del sabato è del sabato: non diventa la cena di giovedì."""
    sabato = settimana_generata["days"][5]
    cena = next(m for m in sabato["meals"] if m["slot_name"] == "Cena")
    res = client.put(
        f"/api/planning/meals/{cena['id']}/recurring",
        json={"is_recurring": True, "recurring_rule": {"type": "weekly", "day": 5}},
    )
    assert res.status_code == 200

    oggi(2)
    week = client.get("/api/planning/weeks/current").json()

    assert titoli(week, "Cena")[5] == "Cena 5"
    # Le altre cene scalano scavalcandola: giovedì prende quella di martedì.
    assert titoli(week, "Cena")[2:5] == ["Cena 0", "Cena 1", "Cena 2"]
    assert titoli(week, "Cena")[6] == "Cena 3"


def test_un_giorno_tracciato_non_si_salta(client, settimana_generata, oggi):
    """Aver detto "l'ho seguito" vuol dire che quel giorno hai mangiato, spesa o no."""
    for meal in settimana_generata["days"][0]["meals"]:
        client.put(f"/api/planning/meals/{meal['id']}/followed", json={"is_followed": True})

    oggi(2)
    week = client.get("/api/planning/weeks/current").json()

    assert [d["is_skipped"] for d in week["days"]][:2] == [False, True]
    # Lunedì resta intatto, e non cede le sue ricette alla fila.
    assert titoli(week)[0] == "Pranzo 0"
    assert titoli(week)[2] == "Pranzo 1"


# ── Effetti sul resto dell'app ─────────────────────────────────────────────────


def test_la_lista_della_spesa_perde_i_giorni_saltati(client, settimana_generata, oggi):
    oggi(2)
    lst = client.get("/api/shopping/current").json()
    items = {i["name"]: i for cat in lst["categories"] for i in cat["items"]}

    # Zucchine: 250 g al giorno, ma i giorni rimasti sono cinque, non sette.
    assert items["zucchine"]["quantity"] == pytest.approx(5 * 250)
    # E la lista dice da quando parte, così il totale più basso si spiega da sé.
    assert lst["days_skipped"] == 2
    assert lst["covers_from"] == (planner.monday_of(date.today()) + timedelta(days=2)).isoformat()


def test_la_generazione_non_riempie_i_giorni_saltati(client, diet, fake_ai, oggi):
    oggi(2)
    week = client.get("/api/planning/weeks/current").json()
    assert week["meals_total"] == 5 * 3  # cinque giorni per tre pasti, non sette

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == 5 * 3

    assert titoli(res.json())[:2] == [None, None]


def test_il_tracking_non_conta_i_giorni_saltati(client, settimana_generata, oggi):
    oggi(2)
    tracking = client.get("/api/tracking/weekly").json()

    assert [d["is_skipped"] for d in tracking["days"]][:2] == [True, True]

    summary = tracking["weekly_summary"]
    assert summary["days_skipped"] == 2
    # Un giorno saltato non è un giorno andato male: media e aderenza restano piene.
    assert summary["avg_daily_calories_planned"] == 1700
    assert summary["compliance_pct"] == 100.0
    assert summary["meals_planned"] == 5 * 3


def test_su_un_giorno_saltato_non_si_tocca_niente(client, settimana_generata, oggi):
    colazione = settimana_generata["days"][0]["meals"][0]

    oggi(2)
    client.get("/api/planning/weeks/current")

    assert client.post(f"/api/planning/meals/{colazione['id']}/regenerate").status_code == 409
    res = client.put(
        f"/api/planning/meals/{colazione['id']}/assign",
        json={"recipe_id": settimana_generata["days"][3]["meals"][0]["recipe"]["id"]},
    )
    assert res.status_code == 409
    assert "saltato" in res.json()["detail"]


# ── La spesa fatta congela tutto ───────────────────────────────────────────────


def test_la_spesa_fatta_ferma_lo_slittamento(client, settimana_generata, oggi):
    assert client.post("/api/shopping/current/complete").status_code == 200

    oggi(4)  # passano tre giorni: a piano bloccato non si salta più niente
    week = client.get("/api/planning/weeks/current").json()

    assert week["is_locked"] is True
    assert week["days_skipped"] == 0
    assert titoli(week) == [f"Pranzo {i}" for i in range(DAYS)]


def test_dopo_lo_sblocco_d_emergenza_non_si_slitta_lo_stesso(
    client, settimana_generata, oggi
):
    """Sbloccare non disfa la spesa: il cibo è in casa, i piatti restano dove sono."""
    client.post("/api/shopping/current/complete")
    assert client.post(f"/api/planning/weeks/{settimana_generata['id']}/unlock").status_code == 200

    oggi(3)
    week = client.get("/api/planning/weeks/current").json()

    assert week["is_locked"] is False
    assert week["days_skipped"] == 0
    assert titoli(week) == [f"Pranzo {i}" for i in range(DAYS)]


def test_la_spesa_fatta_a_meta_settimana_congela_i_giorni_gia_saltati(
    client, settimana_generata, oggi
):
    """Spesa di mercoledì: lunedì e martedì restano saltati, il resto si blocca."""
    oggi(2)
    client.get("/api/planning/weeks/current")
    assert client.post("/api/shopping/current/complete").status_code == 200

    oggi(4)
    week = client.get("/api/planning/weeks/current").json()

    assert week["days_skipped"] == 2
    assert titoli(week)[2:] == ["Pranzo 0", "Pranzo 1", "Pranzo 2", "Pranzo 3", "Pranzo 4"]
