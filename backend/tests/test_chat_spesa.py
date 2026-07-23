"""Chat della spesa: cambia un ingrediente in tutte le ricette che lo usano.

È la chat che si apre al supermercato: "non trovo le zucchine" → il modello riscrive
le ricette che le contengono e la lista della spesa si rifà da sola. A differenza
della chat sul pasto, lavora sulla settimana intera e può toccare più ricette in una
risposta sola.
"""

import json

import pytest

from app.routers import chat as chat_router
from app.services import planner
from tests.test_chat import FakeChat
from tests.test_flow import FakeModel


@pytest.fixture()
def week(client, diet, monkeypatch):
    """Una settimana generata dal modello finto: ogni pranzo e ogni cena usano zucchine."""
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    w = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{w['id']}/generate")
    return client.get("/api/planning/weeks/current").json()


def use_chat(monkeypatch, reply) -> FakeChat:
    fake = FakeChat(reply)
    monkeypatch.setattr(chat_router, "get_client", lambda db, user, role: fake)
    return fake


def pranzo_id(week, dow=0):
    return next(m["id"] for m in week["days"][dow]["meals"] if m["slot_name"] == "Pranzo")


# Ricetta di ricambio senza zucchine: melanzane al loro posto.
def _senza_zucchine(titolo="Pasta alle melanzane"):
    return {
        "title": titolo,
        "prep_time_min": 10,
        "cook_time_min": 15,
        "difficulty": "easy",
        "ingredients": [
            {"name": "pasta", "quantity": 100, "unit": "g"},
            {"name": "melanzane", "quantity": 150, "unit": "g"},
        ],
        "instructions": "1. Lessa la pasta.\n2. Salta le melanzane.",
        "nutrition": {"calories": 700, "protein_g": 30, "carbs_g": 90, "fat_g": 18},
        "tags": {"cuisine": "italiana", "type": "primo"},
    }


def _update_reply(meal_ids, testo="Ho messo le melanzane al posto delle zucchine."):
    data = {
        "ingredient": "zucchine",
        "meals": [{"meal_id": mid, "recipe": _senza_zucchine()} for mid in meal_ids],
    }
    return f"{testo}\n[RECIPES_UPDATE]\n{json.dumps(data, ensure_ascii=False)}"


# ── Modifica ───────────────────────────────────────────────────────────────────


def test_cambia_la_ricetta_e_rifa_la_lista(client, week, monkeypatch):
    prima = client.get("/api/shopping/current").json()
    zucchine_prima = next(
        i["quantity"] for c in prima["categories"] for i in c["items"] if i["name"] == "zucchine"
    )

    mid = pranzo_id(week)
    use_chat(monkeypatch, _update_reply([mid]))

    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages",
        json={"content": "Non trovo le zucchine, metti le melanzane nel pranzo di lunedì"},
    ).json()

    assert res["list_updated"] is True
    assert res["changed_meals"] == ["Lunedì / Pranzo"]
    # Il marcatore e il JSON non finiscono sotto gli occhi dell'utente.
    assert "[RECIPES_UPDATE]" not in res["content"]

    # La ricetta è cambiata davvero...
    meal = client.get(f"/api/planning/meals/{mid}").json()
    assert meal["recipe"]["title"] == "Pasta alle melanzane"

    # ...e la lista ha perso 150 g di zucchine (quel pranzo non le usa più).
    dopo = client.get("/api/shopping/current").json()
    zucchine_dopo = next(
        i["quantity"] for c in dopo["categories"] for i in c["items"] if i["name"] == "zucchine"
    )
    assert zucchine_dopo == pytest.approx(zucchine_prima - 150)
    # E le melanzane, che prima non c'erano, ora sono in lista.
    assert any(i["name"] == "melanzane" for c in dopo["categories"] for i in c["items"])


def test_cambia_piu_ricette_in_un_colpo(client, week, monkeypatch):
    ids = [pranzo_id(week, 0), pranzo_id(week, 1), pranzo_id(week, 2)]
    use_chat(monkeypatch, _update_reply(ids))

    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages",
        json={"content": "Togli le zucchine da tutti i pranzi"},
    ).json()

    assert res["changed_meals"] == ["Lunedì / Pranzo", "Martedì / Pranzo", "Mercoledì / Pranzo"]
    for mid in ids:
        assert client.get(f"/api/planning/meals/{mid}").json()["recipe"]["title"] == "Pasta alle melanzane"


def test_il_prompt_riceve_indice_e_lista(client, week, monkeypatch):
    fake = use_chat(monkeypatch, "Le zucchine le trovi surgelate, di solito.")
    client.post(
        f"/api/chat/shopping/{week['id']}/messages",
        json={"content": "Dove trovo le zucchine?"},
    )

    # Il modello vede i meal_id (per dire quale ricetta cambiare) e la lista attuale.
    assert "meal_id" in fake.system
    assert "zucchine" in fake.system
    assert "INGREDIENTI ATTUALMENTE IN LISTA" in fake.system
    assert "[RECIPES_UPDATE]" in fake.system


def test_una_domanda_non_cambia_niente(client, week, monkeypatch):
    use_chat(monkeypatch, "Le melanzane vanno benissimo come alternativa.")
    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages",
        json={"content": "Con cosa posso sostituire le zucchine?"},
    ).json()

    assert res["list_updated"] is False
    assert res["shopping_list"] is None


def test_un_meal_id_inventato_viene_ignorato(client, week, monkeypatch):
    use_chat(monkeypatch, _update_reply([999999]))
    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages", json={"content": "Cambia tutto"}
    ).json()

    assert res["list_updated"] is False
    assert "Nessuna ricetta corrispondeva" in res["content"]


def test_un_json_rotto_non_rompe_la_conversazione(client, week, monkeypatch):
    use_chat(monkeypatch, "Ecco.\n[RECIPES_UPDATE]\n{ non è json")
    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages", json={"content": "Cambia"}
    ).json()

    assert res["list_updated"] is False
    assert "Non sono riuscito ad applicare" in res["content"]


# ── A spesa fatta ──────────────────────────────────────────────────────────────


def test_a_spesa_fatta_la_chat_non_modifica(client, week, monkeypatch):
    client.post("/api/shopping/current/complete")

    mid = pranzo_id(week)
    fake = use_chat(monkeypatch, _update_reply([mid]))
    res = client.post(
        f"/api/chat/shopping/{week['id']}/messages", json={"content": "Cambia le zucchine"}
    ).json()

    assert res["list_updated"] is False
    assert "spesa è già fatta" in res["content"].lower()
    # Il modello è avvisato del blocco.
    assert "BLOCCATO" in fake.system
    # La ricetta è rimasta quella di prima.
    assert client.get(f"/api/planning/meals/{mid}").json()["recipe"]["title"] == "Pranzo 0"


# ── Storico ────────────────────────────────────────────────────────────────────


def test_lo_storico_si_conserva_e_si_svuota(client, week, monkeypatch):
    use_chat(monkeypatch, "Certo.")
    client.post(f"/api/chat/shopping/{week['id']}/messages", json={"content": "Ci sono uova?"})

    storico = client.get(f"/api/chat/shopping/{week['id']}/messages").json()
    assert [m["role"] for m in storico] == ["user", "assistant"]
    assert storico[0]["content"] == "Ci sono uova?"

    assert client.delete(f"/api/chat/shopping/{week['id']}/messages").status_code == 204
    assert client.get(f"/api/chat/shopping/{week['id']}/messages").json() == []


def test_una_settimana_inesistente_da_404(client):
    assert client.get("/api/chat/shopping/999999/messages").status_code == 404
