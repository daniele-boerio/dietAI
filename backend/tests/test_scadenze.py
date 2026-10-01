"""Le scadenze in dispensa: quello che sta per scadere si usa per primo.

La dispensa era «da consumare in via prioritaria» tutta uguale. Con la data, il
contesto della generazione mette in cima quello che scade e lo dice, con il giorno.
"""

from datetime import timedelta

from app.services import planner
from app.services.planner import build_context


def oggi():
    return planner.today()


def test_la_scadenza_si_segna_e_si_legge(client):
    fra_tre = (oggi() + timedelta(days=3)).isoformat()
    res = client.post(
        "/api/config/pantry",
        json={"ingredient_name": "ricotta", "quantity": 250, "unit": "g", "expires_on": fra_tre},
    )
    assert res.status_code == 201, res.text
    assert res.json()["expires_on"] == fra_tre
    assert res.json()["expires_in_days"] == 3


def test_la_scadenza_si_corregge_e_si_toglie(client):
    item = client.post(
        "/api/config/pantry", json={"ingredient_name": "ricotta", "quantity": 250, "unit": "g"}
    ).json()
    assert item["expires_on"] is None

    domani = (oggi() + timedelta(days=1)).isoformat()
    item = client.put(f"/api/config/pantry/{item['id']}", json={"expires_on": domani}).json()
    assert item["expires_in_days"] == 1

    # Un PUT senza il campo non lo tocca; con null lo toglie.
    item = client.put(f"/api/config/pantry/{item['id']}", json={"quantity": 200}).json()
    assert item["expires_on"] == domani
    item = client.put(f"/api/config/pantry/{item['id']}", json={"expires_on": None}).json()
    assert item["expires_on"] is None


def test_il_contesto_mette_prima_quello_che_scade(client, diet, db):
    client.post("/api/config/pantry", json={"ingredient_name": "riso", "quantity": 1000, "unit": "g"})
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "ricotta", "quantity": 250, "unit": "g",
              "expires_on": (oggi() + timedelta(days=2)).isoformat()},
    )
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "zucchine", "quantity": 300, "unit": "g",
              "expires_on": (oggi() + timedelta(days=30)).isoformat()},
    )

    contesto = build_context(db, 1)
    riga = next(r for r in contesto.splitlines() if r.startswith("- Dispensa attuale"))

    assert riga.index("ricotta") < riga.index("zucchine") < riga.index("riso")
    assert "ricotta (250 g) — SCADE il" in riga
    # Fra un mese non è un'informazione per il piano di questa settimana.
    assert "zucchine (300 g)," in riga or riga.rstrip().endswith("zucchine (300 g)")


def test_una_scorta_scaduta_si_dice(client, diet, db):
    client.post(
        "/api/config/pantry",
        json={"ingredient_name": "ricotta", "quantity": 250, "unit": "g",
              "expires_on": (oggi() - timedelta(days=1)).isoformat()},
    )
    assert "ricotta (250 g) — SCADUTA il" in build_context(db, 1)
