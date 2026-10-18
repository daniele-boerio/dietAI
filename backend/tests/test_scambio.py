"""Scambiare la ricetta fra due pasti della stessa settimana.

I target restano dove sono e i totali dei due giorni cambiano: in nutrizione conta il
fabbisogno della settimana, e quello resta identico. Una casella vuota vale (il piatto
si sposta), mentre fissi, «lo faccio io», saltati e pasti già segnati restano fuori.
"""

import pytest

from app.services import planner
from tests.test_flow import FakeModel


@pytest.fixture()
def settimana(client, diet, monkeypatch):
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})
    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200, res.text
    return client.get("/api/planning/weeks/current").json()


def pasto(week, dow, nome) -> dict:
    return next(m for m in week["days"][dow]["meals"] if m["slot_name"] == nome)


def ricetta(client, meal_id):
    r = client.get(f"/api/planning/meals/{meal_id}").json()["recipe"]
    return r["id"] if r else None


def scambia(client, a, b):
    return client.post(f"/api/planning/meals/{a}/swap", json={"other_meal_id": b})


def test_pranzo_e_cena_di_due_giorni_si_scambiano(client, settimana):
    pranzo, cena = pasto(settimana, 0, "Pranzo"), pasto(settimana, 2, "Cena")
    prima = ricetta(client, pranzo["id"]), ricetta(client, cena["id"])

    res = scambia(client, pranzo["id"], cena["id"])

    assert res.status_code == 200, res.text
    assert (ricetta(client, pranzo["id"]), ricetta(client, cena["id"])) == prima[::-1]
    # I target restano del pasto, non viaggiano con la ricetta.
    assert res.json()["target"]["calories"] == pranzo["target"]["calories"]
    assert res.json()["swapped_with"]["meal_id"] == cena["id"]
    # La risposta è il pasto intero, come la GET: la pagina si ridisegna con questa.
    assert "week" in res.json() and res.json()["recipe"]["id"] == prima[1]


def test_il_totale_della_settimana_non_cambia(client, settimana):
    def totale():
        week = client.get("/api/planning/weeks/current").json()
        return sum(
            (m["recipe"] or {}).get("calories", 0) for d in week["days"] for m in d["meals"]
        )

    prima = totale()
    scambia(client, pasto(settimana, 0, "Colazione")["id"], pasto(settimana, 4, "Cena")["id"])
    assert totale() == prima


def test_con_una_casella_vuota_il_piatto_si_sposta(client, settimana):
    vuota = pasto(settimana, 3, "Pranzo")["id"]
    client.delete(f"/api/planning/meals/{vuota}/recipe")
    piena = pasto(settimana, 1, "Pranzo")["id"]
    piatto = ricetta(client, piena)

    assert scambia(client, piena, vuota).status_code == 200
    assert ricetta(client, vuota) == piatto
    assert ricetta(client, piena) is None


def test_due_caselle_vuote_non_sono_uno_scambio(client, settimana):
    a, b = pasto(settimana, 3, "Pranzo")["id"], pasto(settimana, 4, "Pranzo")["id"]
    client.delete(f"/api/planning/meals/{a}/recipe")
    client.delete(f"/api/planning/meals/{b}/recipe")
    assert scambia(client, a, b).status_code == 400


@pytest.mark.parametrize("stato", ["seguito", "fisso", "stesso"])
def test_quello_che_non_si_scambia(client, settimana, stato):
    a, b = pasto(settimana, 1, "Pranzo")["id"], pasto(settimana, 2, "Pranzo")["id"]
    if stato == "seguito":
        client.put(f"/api/planning/meals/{b}/followed", json={"is_followed": True})
    elif stato == "fisso":
        client.put(f"/api/planning/meals/{b}/recurring", json={"is_recurring": True})
    else:
        b = a
    prima = ricetta(client, a)

    res = scambia(client, a, b)

    assert res.status_code in (400, 409), res.text
    assert ricetta(client, a) == prima


def test_solo_nella_stessa_settimana(client, settimana):
    prossima = client.get("/api/planning/weeks/next").json()
    altro = prossima["days"][0]["meals"][1]["id"]
    assert scambia(client, pasto(settimana, 0, "Pranzo")["id"], altro).status_code == 400


def test_i_candidati_dicono_chi_non_si_puo_scambiare(client, settimana):
    a, b = pasto(settimana, 0, "Pranzo")["id"], pasto(settimana, 1, "Cena")["id"]
    client.put(f"/api/planning/meals/{b}/followed", json={"is_followed": True})

    candidati = client.get(f"/api/planning/meals/{a}/swap-candidates").json()

    assert a not in {c["meal_id"] for c in candidati}
    assert len(candidati) == 7 * 3 - 1
    per_id = {c["meal_id"]: c for c in candidati}
    assert per_id[b]["blocked"] == "già segnato"
    assert all(c["blocked"] is None for c in candidati if c["meal_id"] != b)


def test_il_rinvio_di_un_pasto_saltato_segue_il_piatto(client, settimana):
    """Lunedì «ho mangiato altro»: il piatto si accoda giovedì. Poi giovedì si scambia
    con venerdì. «L'ho seguito» su lunedì deve svuotare venerdì, dove il piatto è
    finito, e lasciare a giovedì il piatto che gli è arrivato."""
    lunedi, giovedi = pasto(settimana, 0, "Pranzo")["id"], pasto(settimana, 3, "Pranzo")["id"]
    venerdi = pasto(settimana, 4, "Pranzo")["id"]
    client.delete(f"/api/planning/meals/{giovedi}/recipe")
    rimandato = ricetta(client, lunedi)
    res = client.put(f"/api/planning/meals/{lunedi}/followed", json={"is_followed": False})
    assert res.json()["moved_to"]["meal_id"] == giovedi
    piatto_di_venerdi = ricetta(client, venerdi)

    assert scambia(client, giovedi, venerdi).status_code == 200
    assert ricetta(client, venerdi) == rimandato

    client.put(f"/api/planning/meals/{lunedi}/followed", json={"is_followed": True})
    assert ricetta(client, venerdi) is None
    assert ricetta(client, giovedi) == piatto_di_venerdi


def test_l_ospite_non_scambia_con_un_pasto_dell_amministratore(client, guest_client, settimana):
    guest_client.post(
        "/api/diet/manual",
        json={"meals": [{"name": "Pranzo", "order": 0, "calories": 700, "protein_g": 40,
                         "carbs_g": 80, "fat_g": 20}]},
    )
    suo = guest_client.get("/api/planning/weeks/current").json()["days"][0]["meals"][0]["id"]
    dell_admin = pasto(settimana, 0, "Pranzo")["id"]
    prima = ricetta(client, dell_admin)

    assert scambia(guest_client, suo, dell_admin).status_code == 404
    assert ricetta(client, dell_admin) == prima
