"""Correggere a mano una ricetta del ricettario.

Il caso che l'ha chiesta: una ricetta salvata col cavolfiore «1 unità» invece che in
grammi. Prima si poteva solo chiedere alla chat di un pasto; ora la si corregge dal
ricettario, e la riga stessa cambia — con la spesa e i macro che la seguono.
"""

import pytest

from app.models import User
from app.services import macros
from app.services.recipes import create_recipe

RICETTA = {
    "title": "Pasta al cavolfiore",
    "description": "Il sugo della domenica",
    "prep_time_min": 10,
    "cook_time_min": 30,
    "difficulty": "easy",
    "instructions": "1. Cuoci il cavolfiore. 2. Condisci la pasta.",
    "calories": 450,
    "protein_g": 15.0,
    "carbs_g": 70.0,
    "fat_g": 10.0,
    "ingredients": [
        {"name": "cavolfiore", "quantity": 1, "unit": "unità"},
        {"name": "pasta", "quantity": 80, "unit": "g"},
    ],
}


def corpo(**campi):
    base = {k: RICETTA[k] for k in ("title", "description", "prep_time_min", "cook_time_min",
                                    "difficulty", "instructions")}
    base["ingredients"] = [
        {"name": "cavolfiore", "quantity": 200, "unit": "g"},
        {"name": "pasta", "quantity": 80, "unit": "g"},
    ]
    return {**base, **campi}


def voci_spesa(client):
    lst = client.get("/api/shopping/current").json()
    return {i["name"]: i for cat in lst["categories"] for i in cat["items"]}


@pytest.fixture()
def in_piano(client, diet):
    """La ricetta assegnata al pranzo di martedì: è in spesa."""
    week = client.get("/api/planning/weeks/current").json()
    pranzo = next(m for m in week["days"][1]["meals"] if m["slot_name"] == "Pranzo")
    res = client.put(f"/api/planning/meals/{pranzo['id']}/assign", json={"recipe": RICETTA})
    assert res.status_code == 200, res.text
    return res.json()


def test_si_correggono_gli_ingredienti_e_la_spesa_li_segue(client, in_piano):
    rid = in_piano["recipe"]["id"]
    assert voci_spesa(client)["cavolfiore"]["unit"] == "unità"

    res = client.put(f"/api/recipes/{rid}", json=corpo(title="Pasta e cavolfiore"))

    assert res.status_code == 200, res.text
    ricetta = res.json()
    assert ricetta["title"] == "Pasta e cavolfiore"
    assert {i["name"]: (i["quantity"], i["unit"]) for i in ricetta["ingredients"]}[
        "cavolfiore"
    ] == (200, "g")
    # Risponde intera, come la GET: la pagina si ridisegna con questa.
    assert "usage_history" in ricetta
    voce = voci_spesa(client)["cavolfiore"]
    assert (voce["quantity"], voce["unit"]) == (200, "g")


def test_il_pasto_che_la_usa_vede_la_ricetta_corretta(client, in_piano):
    client.put(f"/api/recipes/{in_piano['recipe']['id']}", json=corpo())
    pasto = client.get(f"/api/planning/meals/{in_piano['id']}").json()
    assert {i["name"]: i["unit"] for i in pasto["recipe"]["ingredients"]}["cavolfiore"] == "g"


def test_i_macro_scritti_a_mano_si_correggono_nel_modulo(client, diet):
    ricetta = client.post("/api/recipes", json=RICETTA).json()
    res = client.put(f"/api/recipes/{ricetta['id']}", json=corpo(calories=380, protein_g=14))
    assert res.json()["calories"] == 380
    assert res.json()["protein_g"] == 14


def test_le_altre_rifanno_i_macro_dagli_ingredienti(client, db, diet, monkeypatch):
    """Correggere le grammature e tenere le calorie di prima sarebbe a metà."""
    utente = db.query(User).filter(User.is_admin.is_(True)).one()
    generata = create_recipe(db, utente.id, RICETTA)  # del modello: numeri dichiarati
    db.commit()
    rid, prima = generata.id, generata.calories
    monkeypatch.setattr(macros, "ATTIVO", True)

    res = client.put(
        f"/api/recipes/{rid}",
        json=corpo(ingredients=[{"name": "pasta", "quantity": 160, "unit": "g"}], calories=1),
    )

    ricetta = res.json()
    assert ricetta["nutrition_source"] == "calcolata"
    assert ricetta["calories"] not in (prima, 1)


def test_senza_ingredienti_non_si_salva(client, in_piano):
    res = client.put(f"/api/recipes/{in_piano['recipe']['id']}", json=corpo(ingredients=[]))
    assert res.status_code == 422


def test_la_ricetta_di_un_altro_non_si_tocca(guest_client, in_piano):
    res = guest_client.put(f"/api/recipes/{in_piano['recipe']['id']}", json=corpo())
    assert res.status_code == 404
