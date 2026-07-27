"""Cosa entra nella spesa: da oggi in avanti, tolto quello che non si cucinerà.

La lista è "quello che il piano chiede meno quello che c'è in casa", e la parte
"quello che il piano chiede" ha tre esclusioni, tutte per lo stesso motivo — non
comprare roba che non servirà:

· i giorni già passati, perché per lunedì non si cucina più da mercoledì;
· i pasti già segnati come seguiti, perché quel piatto è stato cucinato;
· i giorni e i pasti saltati, che hanno già la loro ricetta accodata altrove.

Il piano invece non si muove da solo: i giorni passati restano com'erano, con le loro
ricette al loro posto. Quello che si è mangiato lo dice l'utente, pasto per pasto.
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


def quantita(lst: dict, nome: str) -> float:
    return next(
        (i["quantity"] for c in lst["categories"] for i in c["items"] if i["name"] == nome), 0
    )


# ── Il piano non si muove da solo ──────────────────────────────────────────────


def test_i_giorni_passati_restano_dove_sono(client, settimana_generata, oggi):
    """Il piano segue il calendario: quello che era di lunedì resta di lunedì.

    Spostare i piatti in avanti da soli aveva senso quando la spesa bloccava la
    settimana; adesso quello che non si è mangiato lo si sposta dicendolo ("ho
    mangiato altro"), che è la stessa cosa ma decisa da chi ha cucinato.
    """
    oggi(2)  # mercoledì
    week = client.get("/api/planning/weeks/current").json()

    assert [d["is_skipped"] for d in week["days"]] == [False] * 7
    assert titoli(week) == [f"Pranzo {i}" for i in range(DAYS)]


# ── Cosa esce dalla lista ──────────────────────────────────────────────────────


def test_per_i_giorni_passati_non_si_compra_piu(client, settimana_generata, oggi):
    lunedi = client.get("/api/shopping/current").json()
    assert quantita(lunedi, "zucchine") == pytest.approx(7 * 250)

    oggi(2)
    mercoledi = client.get("/api/shopping/current").json()

    # Restano i cinque pranzi da mercoledì a domenica.
    assert quantita(mercoledi, "zucchine") == pytest.approx(5 * 250)
    assert mercoledi["covers_from"] == (planner.monday_of(date.today()) + timedelta(days=2)).isoformat()


def test_un_pasto_gia_seguito_esce_dalla_lista(client, settimana_generata):
    """L'hai cucinato: ricomprarlo sarebbe comprare due volte la stessa cena."""
    pranzo = next(
        m for m in settimana_generata["days"][0]["meals"] if m["slot_name"] == "Pranzo"
    )
    client.put(f"/api/planning/meals/{pranzo['id']}/followed", json={"is_followed": True})

    lst = client.get("/api/shopping/current").json()
    # 250 g al giorno fra pranzo (150) e cena (100): sparisce solo il pranzo di lunedì.
    assert quantita(lst, "zucchine") == pytest.approx(7 * 250 - 150)


def test_il_pasto_saltato_non_esce_dalla_spesa_ma_si_sposta(client, settimana_generata):
    """"Ho mangiato altro" rimanda il piatto, non lo cancella: si cucinerà, va comprato."""
    pranzo = next(
        m for m in settimana_generata["days"][0]["meals"] if m["slot_name"] == "Pranzo"
    )
    res = client.put(f"/api/planning/meals/{pranzo['id']}/followed", json={"is_followed": False})
    assert res.json()["moved_to"]["next_week"] is True

    lst = client.get("/api/shopping/current").json()
    assert quantita(lst, "zucchine") == pytest.approx(7 * 250)


# ── Giornate saltate a mano ────────────────────────────────────────────────────


def test_saltare_una_giornata_accoda_le_sue_ricette(client, settimana_generata):
    """Weekend fuori: i piatti di giovedì si spostano, quindi restano da comprare."""
    giovedi = settimana_generata["days"][3]
    res = client.put(f"/api/planning/days/{giovedi['id']}/skip", json={"is_skipped": True})
    assert res.status_code == 200, res.text

    week = client.get("/api/planning/weeks/current").json()
    assert week["days"][3]["is_skipped"] is True
    # La casella tiene la ricetta per memoria, ma non conta più da nessuna parte.
    assert all(m["is_skipped"] for m in week["days"][3]["meals"])

    # Il piatto si cucinerà un altro giorno, quindi si compra lo stesso.
    lst = client.get("/api/shopping/current").json()
    assert quantita(lst, "zucchine") == pytest.approx(7 * 250)
    assert titoli(client.get("/api/planning/weeks/next").json())[0] == "Pranzo 3"


def test_la_generazione_non_riempie_i_giorni_saltati(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.put(f"/api/planning/days/{week['days'][3]['id']}/skip", json={"is_skipped": True})

    week = client.get("/api/planning/weeks/current").json()
    assert week["meals_total"] == 6 * 3  # sei giorni per tre pasti, non sette

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == 6 * 3
    assert titoli(res.json())[3] is None


def test_il_tracking_non_conta_i_giorni_saltati(client, settimana_generata):
    giovedi = settimana_generata["days"][3]
    client.put(f"/api/planning/days/{giovedi['id']}/skip", json={"is_skipped": True})

    tracking = client.get("/api/tracking/weekly").json()

    assert [d["is_skipped"] for d in tracking["days"]][3] is True
    summary = tracking["weekly_summary"]
    assert summary["days_skipped"] == 1
    # Un giorno saltato non è un giorno andato male: media e aderenza restano piene.
    assert summary["avg_daily_calories_planned"] == 1700
    assert summary["compliance_pct"] == 100.0
    assert summary["meals_planned"] == 6 * 3


def test_su_un_giorno_saltato_non_si_tocca_niente(client, settimana_generata):
    giovedi = settimana_generata["days"][3]
    colazione = giovedi["meals"][0]
    client.put(f"/api/planning/days/{giovedi['id']}/skip", json={"is_skipped": True})

    assert client.post(f"/api/planning/meals/{colazione['id']}/regenerate").status_code == 409
    res = client.put(
        f"/api/planning/meals/{colazione['id']}/assign",
        json={"recipe_id": settimana_generata["days"][0]["meals"][0]["recipe"]["id"]},
    )
    assert res.status_code == 409
    assert "saltat" in res.json()["detail"]
