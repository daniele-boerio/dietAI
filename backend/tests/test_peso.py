"""Lo storico del peso, e quando proporre di ricalcolare i target.

I target di una dieta da questionario dipendono dal peso: sei chili dopo sono i target
di un'altra persona. L'app non li ricalcola da sola, ma lo dice — e solo quando la
differenza vale un ricalcolo.
"""

from datetime import date, timedelta

from app.services import planner
from tests.test_questionario import RISPOSTE


def oggi():
    return planner.today()


def test_il_questionario_e_la_prima_pesata(client):
    client.post("/api/diet/questionnaire", json=RISPOSTE)

    storico = client.get("/api/tracking/weight").json()
    assert storico["entries"] == [{"day": oggi().isoformat(), "weight_kg": 80}]
    assert storico["target_weight"] == 80
    assert storico["recalc"] is None


def test_ripesarsi_lo_stesso_giorno_corregge(client):
    client.put("/api/tracking/weight", json={"weight_kg": 81.0})
    storico = client.put("/api/tracking/weight", json={"weight_kg": 80.4}).json()

    assert [e["weight_kg"] for e in storico["entries"]] == [80.4]


def test_le_pesate_stanno_in_ordine_di_data(client):
    ieri = (oggi() - timedelta(days=1)).isoformat()
    client.put("/api/tracking/weight", json={"weight_kg": 79.0})
    storico = client.put("/api/tracking/weight", json={"weight_kg": 79.6, "day": ieri}).json()

    assert [e["day"] for e in storico["entries"]] == [ieri, oggi().isoformat()]


def test_un_giorno_futuro_non_si_segna(client):
    domani = (oggi() + timedelta(days=1)).isoformat()
    res = client.put("/api/tracking/weight", json={"weight_kg": 79.0, "day": domani})
    assert res.status_code == 400


def test_sotto_la_soglia_non_si_propone_niente(client):
    client.post("/api/diet/questionnaire", json=RISPOSTE)  # 80 kg
    storico = client.put("/api/tracking/weight", json={"weight_kg": 78.5}).json()
    assert storico["recalc"] is None


def test_oltre_la_soglia_si_propone_il_ricalcolo(client):
    client.post("/api/diet/questionnaire", json=RISPOSTE)  # 80 kg
    domani_non_serve = oggi()  # la pesata nuova sostituisce quella del questionario
    storico = client.put(
        "/api/tracking/weight", json={"weight_kg": 76.5, "day": domani_non_serve.isoformat()}
    ).json()

    assert storico["recalc"] == {"target_weight": 80, "latest_weight": 76.5, "delta": -3.5}


def test_la_dieta_del_nutrizionista_non_si_ricalcola(client, diet):
    """I suoi numeri non vengono da una formula che l'app conosce: niente proposta."""
    storico = client.put("/api/tracking/weight", json={"weight_kg": 60.0}).json()
    assert storico["target_weight"] is None
    assert storico["recalc"] is None


def test_una_pesata_si_cancella(client):
    client.put("/api/tracking/weight", json={"weight_kg": 70.0})
    storico = client.delete(f"/api/tracking/weight/{oggi().isoformat()}").json()
    assert storico["entries"] == []


def test_le_pesate_degli_altri_non_si_vedono(client, guest_client):
    client.put("/api/tracking/weight", json={"weight_kg": 70.0})
    assert guest_client.get("/api/tracking/weight").json()["entries"] == []


def test_un_peso_assurdo_e_rifiutato(client):
    assert client.put("/api/tracking/weight", json={"weight_kg": 0}).status_code == 422
    assert isinstance(date.today(), date)
