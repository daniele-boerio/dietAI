"""Chat per pasto: conversazione, modifica della ricetta e comportamento a piano bloccato.

Questi test nascono da un bug vero: `MEAL_CHAT_SYSTEM` contiene lo schema JSON della
ricetta, e riempirlo con `str.format()` faceva esplodere ogni messaggio con un
KeyError su una graffa del JSON. La chat non aveva funzionato un solo giorno, e
nessun test se n'era accorto perché nessun test la toccava.
"""

import json
import re

import pytest

from app.routers import chat as chat_router
from app.services import planner, prompts
from tests.test_flow import FakeModel

RICETTA_AGGIORNATA = {
    "title": "Pasta al pesto di zucchine",
    "description": "Versione più leggera",
    "prep_time_min": 10,
    "cook_time_min": 12,
    "difficulty": "easy",
    "ingredients": [
        {"name": "pasta", "quantity": 90, "unit": "g"},
        {"name": "zucchine", "quantity": 120, "unit": "g"},
    ],
    "instructions": "1. Lessa la pasta.\n2. Condisci.",
    "nutrition": {"calories": 690, "protein_g": 38, "carbs_g": 82, "fat_g": 18},
    "tags": {"cuisine": "italiana", "type": "primo"},
}


class FakeChat:
    """Modello finto per la chat: risponde quello che gli si dice di rispondere."""

    def __init__(self, reply):
        self.reply = reply
        self.system = None
        self.messages = None

    def chat(self, system, messages, **kwargs):
        self.system = system
        self.messages = messages
        return self.reply


@pytest.fixture()
def meal_id(client, diet, monkeypatch):
    """Una settimana generata: restituisce l'id del pranzo di lunedì."""
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    week = client.get("/api/planning/weeks/current").json()
    return week["days"][0]["meals"][1]["id"]  # Pranzo


def use_chat(monkeypatch, reply) -> FakeChat:
    fake = FakeChat(reply)
    monkeypatch.setattr(chat_router, "get_client", lambda db, user, role: fake)
    return fake


# ── Il bug ─────────────────────────────────────────────────────────────────────


def test_un_messaggio_in_chat_riceve_risposta(client, meal_id, monkeypatch):
    """Il caso che andava in 500: il prompt di sistema contiene un esempio JSON."""
    use_chat(monkeypatch, "Sì, puoi prepararlo la sera prima e conservarlo in frigo.")

    res = client.post(
        f"/api/chat/meals/{meal_id}/messages", json={"content": "Posso prepararlo prima?"}
    )

    assert res.status_code == 200, res.text
    assert "frigo" in res.json()["content"]
    assert res.json()["recipe_updated"] is False


def test_il_prompt_di_sistema_arriva_completo_al_modello(client, meal_id, monkeypatch):
    fake = use_chat(monkeypatch, "Va bene.")
    client.post(f"/api/chat/meals/{meal_id}/messages", json={"content": "Ciao"})

    # I segnaposto sono stati riempiti...
    assert "Pranzo" in fake.system
    assert "Lunedì" in fake.system
    # ...e lo schema JSON della ricetta è sopravvissuto intatto.
    assert '"title"' in fake.system
    assert '"nutrition"' in fake.system
    assert "[RECIPE_UPDATE]" in fake.system


@pytest.mark.parametrize(
    "nome,template",
    [(n, t) for n, t in vars(prompts).items() if isinstance(t, str) and n.isupper()],
)
def test_nessun_prompt_si_rompe_sui_segnaposto(nome, template):
    """Guardia generale: `render` riempie i segnaposto e non tocca le graffe del JSON.

    Se qualcuno tornasse a usare str.format() su un prompt con un esempio JSON, o
    aggiungesse un esempio JSON a un prompt formattato, questo test lo direbbe subito.
    """
    placeholder = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
    chiavi = set(placeholder.findall(template))

    reso = prompts.render(template, **{k: f"<{k}>" for k in chiavi})

    assert not placeholder.search(reso), f"{nome}: segnaposto non sostituiti"
    # Le graffe del JSON restano dove sono: nessuna sostituzione di troppo.
    assert reso.count("{") == template.count("{") - len(
        [m for m in placeholder.finditer(template)]
    )


# ── Modifica della ricetta ─────────────────────────────────────────────────────


def _risposta_con_ricetta(testo="Ho alleggerito il condimento."):
    return f"{testo}\n[RECIPE_UPDATE]\n{json.dumps(RICETTA_AGGIORNATA, ensure_ascii=False)}"


def test_la_chat_aggiorna_davvero_la_ricetta(client, meal_id, monkeypatch):
    use_chat(monkeypatch, _risposta_con_ricetta())

    res = client.post(
        f"/api/chat/meals/{meal_id}/messages",
        json={"content": "Rendilo più leggero"},
    ).json()

    assert res["recipe_updated"] is True
    assert res["recipe"]["title"] == "Pasta al pesto di zucchine"
    assert res["recipe"]["calories"] == 690
    # Il marcatore e il JSON non vanno mostrati all'utente.
    assert "[RECIPE_UPDATE]" not in res["content"]
    assert "nutrition" not in res["content"]

    # La modifica è persistita, non solo restituita.
    meal = client.get(f"/api/planning/meals/{meal_id}").json()
    assert meal["recipe"]["title"] == "Pasta al pesto di zucchine"


def test_la_lista_della_spesa_segue_la_modifica(client, meal_id, monkeypatch):
    prima = client.get("/api/shopping/current").json()
    pasta_prima = next(
        i["quantity"] for c in prima["categories"] for i in c["items"] if i["name"] == "pasta"
    )

    use_chat(monkeypatch, _risposta_con_ricetta())
    client.post(f"/api/chat/meals/{meal_id}/messages", json={"content": "Meno pasta"})

    dopo = client.get("/api/shopping/current").json()
    pasta_dopo = next(
        i["quantity"] for c in dopo["categories"] for i in c["items"] if i["name"] == "pasta"
    )
    # Un pranzo su sette passa da 100 g a 90 g.
    assert pasta_dopo == pytest.approx(pasta_prima - 10)


def test_un_json_rotto_non_rompe_la_conversazione(client, meal_id, monkeypatch):
    use_chat(monkeypatch, "Ecco fatto.\n[RECIPE_UPDATE]\n{ questo non è JSON")

    res = client.post(
        f"/api/chat/meals/{meal_id}/messages", json={"content": "Cambia tutto"}
    ).json()

    assert res["recipe_updated"] is False
    assert "Non sono riuscito ad applicare la modifica" in res["content"]


# ── Piano bloccato ─────────────────────────────────────────────────────────────


def test_a_piano_bloccato_la_chat_risponde_ma_non_modifica(client, meal_id, monkeypatch):
    client.post("/api/shopping/current/complete")

    fake = use_chat(monkeypatch, _risposta_con_ricetta())
    res = client.post(
        f"/api/chat/meals/{meal_id}/messages", json={"content": "Cambiala"}
    ).json()

    assert res["recipe_updated"] is False
    assert "bloccato" in res["content"]
    # Il modello viene avvisato del blocco, così non propone modifiche a vuoto.
    assert "BLOCCATO" in fake.system


# ── Storico ────────────────────────────────────────────────────────────────────


def test_lo_storico_conserva_domanda_e_risposta(client, meal_id, monkeypatch):
    use_chat(monkeypatch, "Certo che sì.")
    client.post(f"/api/chat/meals/{meal_id}/messages", json={"content": "È senza glutine?"})

    storico = client.get(f"/api/chat/meals/{meal_id}/messages").json()

    assert [m["role"] for m in storico] == ["user", "assistant"]
    assert storico[0]["content"] == "È senza glutine?"
    assert storico[1]["content"] == "Certo che sì."


def test_lo_storico_precedente_viene_rimandato_al_modello(client, meal_id, monkeypatch):
    use_chat(monkeypatch, "Prima risposta.")
    client.post(f"/api/chat/meals/{meal_id}/messages", json={"content": "Primo messaggio"})

    fake = use_chat(monkeypatch, "Seconda risposta.")
    client.post(f"/api/chat/meals/{meal_id}/messages", json={"content": "Secondo messaggio"})

    contenuti = [m["content"] for m in fake.messages]
    assert contenuti == ["Primo messaggio", "Prima risposta.", "Secondo messaggio"]


def test_lo_storico_si_puo_svuotare(client, meal_id, monkeypatch):
    use_chat(monkeypatch, "Ok.")
    client.post(f"/api/chat/meals/{meal_id}/messages", json={"content": "Ciao"})

    assert client.delete(f"/api/chat/meals/{meal_id}/messages").status_code == 204
    assert client.get(f"/api/chat/meals/{meal_id}/messages").json() == []


def test_un_pasto_inesistente_da_404(client, meal_id):
    assert client.get("/api/chat/meals/999999/messages").status_code == 404
