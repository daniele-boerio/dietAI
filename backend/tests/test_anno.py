"""Aderenza dell'anno: il calendario che dice quanto è stata seguita la dieta.

Guarda solo `is_followed`: un giorno pieno è quando tutti i pasti tracciati sono
seguiti, parziale se c'è dentro un "no", mancato se sono tutti "no". I giorni mai
tracciati restano fuori — non sono fallimenti, sono solo senza dato.
"""

from datetime import date, timedelta

import pytest

from app.services import planner, tracking
from tests.test_flow import FakeModel


@pytest.fixture()
def fake_ai(monkeypatch, client):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


@pytest.fixture()
def settimana(client, diet, fake_ai):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    return client.get("/api/planning/weeks/current").json()


def segna(client, meal_id, followed):
    assert client.put(
        f"/api/planning/meals/{meal_id}/followed", json={"is_followed": followed}
    ).status_code == 200


ANNO = planner.monday_of(date.today()).year


@pytest.fixture()
def oggi(monkeypatch):
    """Dice a che punto della settimana siamo, per la sola aderenza dell'anno.

    Serve perché `year_adherence` ferma la serie a oggi — un anno in corso non conta i
    giorni futuri — e la settimana che i test riempiono è quella corrente: senza dirlo,
    quanti giorni "sono già arrivati" dipende dal giorno in cui lanci la suite, e lo
    stesso test passa da mercoledì in poi e fallisce il lunedì.

    Non basta il `oggi_e_lunedi` del conftest: quello sostituisce `planner.today`,
    mentre `tracking` l'ha importata per nome (`from .planner import today`) e tiene il
    riferimento originale. È il motivo per cui questo test è rimasto rosso metà
    settimana senza che se ne accorgesse nessuno.
    """

    def a(giorno: int):  # 0 = lunedì della settimana in corso
        lunedi = planner.monday_of(date.today())
        monkeypatch.setattr(tracking, "today", lambda: lunedi + timedelta(days=giorno))

    return a


def test_un_giorno_tutto_seguito_e_pieno(client, settimana):
    for meal in settimana["days"][0]["meals"]:
        segna(client, meal["id"], True)

    year = client.get("/api/tracking/year").json()
    giorno = settimana["days"][0]["date"]

    assert year["days"][giorno] == "full"
    assert year["counts"]["full"] == 1


def test_un_no_in_mezzo_rende_il_giorno_parziale(client, settimana):
    meals = settimana["days"][1]["meals"]
    segna(client, meals[0]["id"], True)
    segna(client, meals[1]["id"], False)
    segna(client, meals[2]["id"], True)

    year = client.get("/api/tracking/year").json()
    assert year["days"][settimana["days"][1]["date"]] == "partial"
    assert year["counts"]["partial"] == 1


def test_tutti_no_e_un_giorno_mancato(client, settimana):
    for meal in settimana["days"][2]["meals"]:
        segna(client, meal["id"], False)

    year = client.get("/api/tracking/year").json()
    assert year["days"][settimana["days"][2]["date"]] == "missed"
    assert year["counts"]["missed"] == 1


def test_i_giorni_non_tracciati_restano_fuori(client, settimana):
    for meal in settimana["days"][0]["meals"]:
        segna(client, meal["id"], True)

    year = client.get("/api/tracking/year").json()
    # Un solo giorno ha un dato: gli altri sei non compaiono, non sono "mancati".
    assert year["tracked_days"] == 1
    assert len(year["days"]) == 1


def test_lo_score_pesa_pieno_uno_parziale_mezzo_mancato_zero(client, settimana):
    g = settimana["days"]
    for meal in g[0]["meals"]:  # pieno
        segna(client, meal["id"], True)
    segna(client, g[1]["meals"][0]["id"], True)  # parziale
    segna(client, g[1]["meals"][1]["id"], False)
    for meal in g[2]["meals"]:  # mancato
        segna(client, meal["id"], False)

    year = client.get("/api/tracking/year").json()
    # (1 + 0.5 + 0) / 3 = 50%
    assert year["tracked_days"] == 3
    assert year["score_pct"] == 50.0


def test_la_serie_conta_i_giorni_pieni_di_fila(client, settimana, oggi):
    oggi(6)  # domenica: la settimana è tutta passata, si guarda un archivio
    for i in (0, 1, 2, 4):  # lun, mar, mer pieni; gio no; ven pieno
        for meal in settimana["days"][i]["meals"]:
            segna(client, meal["id"], True)
    segna(client, settimana["days"][3]["meals"][0]["id"], False)

    year = client.get("/api/tracking/year").json()
    assert year["best_streak"] == 3


def test_i_giorni_non_ancora_arrivati_non_allungano_la_serie(client, settimana, oggi):
    """La serie si ferma a oggi, ed è voluto: segnare in anticipo tutta la settimana
    non deve regalare una serie da sette. Il numero è lì per dare soddisfazione a
    guardarlo, e un numero che si può gonfiare non ne dà nessuna."""
    oggi(1)  # martedì
    for giorno in settimana["days"]:
        for meal in giorno["meals"]:
            segna(client, meal["id"], True)

    year = client.get("/api/tracking/year").json()
    # Sette giorni pieni in tabella, due già vissuti.
    assert year["counts"]["full"] == 7
    assert year["best_streak"] == 2


def test_l_anno_espone_gli_anni_disponibili(client, settimana):
    year = client.get("/api/tracking/year").json()
    assert year["year"] == ANNO
    assert ANNO in year["available_years"]


def test_un_altro_anno_e_vuoto(client, settimana):
    for meal in settimana["days"][0]["meals"]:
        segna(client, meal["id"], True)

    year = client.get("/api/tracking/year", params={"year": ANNO - 3}).json()
    assert year["year"] == ANNO - 3
    assert year["tracked_days"] == 0
    assert year["days"] == {}
    assert year["score_pct"] == 0.0
