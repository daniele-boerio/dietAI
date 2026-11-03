"""«Ho mangiato questo» su una casella vuota.

Un giorno senza ricetta restava un buco: l'andamento non sapeva cosa contare e
healthAI non riceveva niente. Ora si scrive a parole cosa si è mangiato, il modello
lo trasforma in una ricetta (macro dagli ingredienti) e il pasto nasce già seguito.
"""

from datetime import timedelta

import pytest

from app.routers import planning as planning_router
from app.services import planner

PIZZA = {
    "title": "Pizza margherita",
    "description": "Mangiata in pizzeria.",
    "prep_time_min": 0,
    "cook_time_min": 0,
    "difficulty": "easy",
    "ingredients": [
        {"name": "farina 00", "quantity": 180, "unit": "g"},
        {"name": "mozzarella", "quantity": 100, "unit": "g"},
        {"name": "passata di pomodoro", "quantity": 80, "unit": "g"},
    ],
    "instructions": "1. Mangiato fuori: ricetta stimata.",
    "nutrition": {"calories": 850, "protein_g": 32, "carbs_g": 105, "fat_g": 30},
    "tags": {"type": "piatto unico"},
}


class ModelloFinto:
    def __init__(self, risposta=PIZZA):
        self.risposta = risposta
        self.system = self.prompt = None
        self.chiamate = 0

    def generate_json(self, system, prompt, **kwargs):
        self.chiamate += 1
        self.system, self.prompt = system, prompt
        return self.risposta


@pytest.fixture()
def finto(monkeypatch):
    modello = ModelloFinto()
    monkeypatch.setattr(planning_router, "get_client", lambda db, user, role: modello)
    return modello


@pytest.fixture()
def settimana(client, diet):
    return client.get("/api/planning/weeks/current").json()


def pasto(settimana, dow, nome):
    return next(m for m in settimana["days"][dow]["meals"] if m["slot_name"] == nome)


def mangiato(client, meal_id, testo="una pizza margherita in pizzeria"):
    return client.post(f"/api/planning/meals/{meal_id}/ate", json={"text": testo})


def test_la_casella_vuota_diventa_un_pasto_seguito(client, settimana, finto):
    cena = pasto(settimana, 0, "Cena")
    assert cena["recipe"] is None

    res = mangiato(client, cena["id"])

    assert res.status_code == 200, res.text
    dopo = res.json()
    assert dopo["recipe"]["title"] == "Pizza margherita"
    assert dopo["recipe"]["calories"] == 850
    assert dopo["is_followed"] is True
    # Al modello arrivano il pasto e le parole dell'utente, così come le ha scritte.
    assert "PASTO: Cena" in finto.prompt
    assert "una pizza margherita in pizzeria" in finto.prompt
    # Stessa forma della GET: la pagina si ridisegna con questa risposta.
    assert dopo.keys() == client.get(f"/api/planning/meals/{cena['id']}").json().keys()


def test_la_ricetta_finisce_nel_ricettario(client, settimana, finto):
    cena = pasto(settimana, 0, "Cena")
    ricetta = mangiato(client, cena["id"]).json()["recipe"]
    salvate = client.get("/api/recipes").json()["items"]
    assert ricetta["id"] in {r["id"] for r in salvate}


def test_l_andamento_la_conta(client, settimana, finto):
    cena = pasto(settimana, 0, "Cena")
    mangiato(client, cena["id"])
    lunedi = client.get("/api/tracking/weekly").json()["days"][0]
    riga = next(m for m in lunedi["meals"] if m["meal_id"] == cena["id"])
    assert riga["recipe_title"] == "Pizza margherita"
    assert riga["planned"]["calories"] == 850
    assert riga["is_followed"] is True


def test_non_scala_la_dispensa(client, settimana, finto):
    cena = pasto(settimana, 0, "Cena")
    client.post("/api/config/pantry", json={"ingredient_name": "mozzarella", "quantity": 250, "unit": "g"})
    prima = client.get("/api/config/pantry").json()

    assert mangiato(client, cena["id"]).status_code == 200
    assert client.get("/api/config/pantry").json() == prima


def test_su_una_casella_piena_no(client, settimana, finto):
    cena = pasto(settimana, 0, "Cena")
    mangiato(client, cena["id"])
    chiamate = finto.chiamate

    res = mangiato(client, cena["id"], "un panino")

    assert res.status_code == 409
    # Il rifiuto arriva prima del modello: nessuna chiamata sprecata.
    assert finto.chiamate == chiamate


def test_nel_futuro_e_un_pasto_libero_in_programma(client, settimana, finto):
    """Martedì non è ancora successo: la ricetta entra, il pasto non risulta seguito."""
    cena_di_martedi = pasto(settimana, 1, "Cena")
    res = mangiato(client, cena_di_martedi["id"], "pizza fuori con gli amici")
    assert res.status_code == 200, res.text
    assert res.json()["recipe"]["title"] == "Pizza margherita"
    assert res.json()["is_followed"] is None


def test_un_giorno_passato_si(client, settimana, finto, monkeypatch):
    oggi = planner.today()
    monkeypatch.setattr(planner, "today", lambda: oggi + timedelta(days=2))
    res = mangiato(client, pasto(settimana, 0, "Pranzo")["id"])
    assert res.status_code == 200, res.text


def test_testo_troppo_corto(client, settimana, finto):
    res = mangiato(client, pasto(settimana, 0, "Cena")["id"], "  ")
    assert res.status_code == 422


def test_l_altro_account_non_lo_tocca(client, guest_client, settimana, finto):
    cena = pasto(settimana, 0, "Cena")
    res = mangiato(guest_client, cena["id"])
    assert res.status_code == 404
    assert client.get(f"/api/planning/meals/{cena['id']}").json()["recipe"] is None
