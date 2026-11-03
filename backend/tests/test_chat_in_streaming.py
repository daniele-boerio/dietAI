"""La chat in streaming: il testo compare mentre il modello lo scrive.

Prima la pagina guardava tre puntini per tutta la risposta. Ora la rotta `/stream`
manda una riga JSON per pezzo di prosa e alla fine la stessa risposta della POST
normale. Il JSON della ricetta, dopo il marcatore, non deve mai uscire a pezzi.
"""

import json

from app.routers import chat as chat_router
from app.services.chat import ProseStream
from tests.test_chat import _risposta_con_ricetta, meal_id  # noqa: F401 — fixture


class ChatAPezzi:
    def __init__(self, reply, pezzo=7):
        self.reply = reply
        self.pezzo = pezzo
        self.streaming = False

    def chat(self, system, messages, on_progress=None, **kwargs):
        self.streaming = on_progress is not None
        if on_progress:
            for i in range(0, len(self.reply), self.pezzo):
                on_progress("content", self.reply[i : i + self.pezzo])
        return self.reply


def _eventi(res):
    return [json.loads(riga) for riga in res.text.splitlines() if riga.strip()]


def test_la_prosa_esce_a_pezzi_e_il_json_mai():
    usciti = []
    filtro = ProseStream("[RECIPE_UPDATE]", usciti.append)
    risposta = _risposta_con_ricetta("Ho tolto il burro e messo l'olio.")
    for i in range(0, len(risposta), 5):
        filtro("content", risposta[i : i + 5])
    assert "".join(usciti).strip() == "Ho tolto il burro e messo l'olio."
    assert len(usciti) > 1


def test_il_ragionamento_non_si_mostra():
    usciti = []
    filtro = ProseStream("[RECIPE_UPDATE]", usciti.append)
    filtro("reasoning", "penso a cosa rispondere")
    filtro("content", "Certo, ecco come fare a cuocerlo meglio.")
    assert "penso" not in "".join(usciti)


def test_la_rotta_manda_i_pezzi_e_poi_la_risposta_intera(client, meal_id, monkeypatch):  # noqa: F811
    finto = ChatAPezzi(_risposta_con_ricetta("Ho alleggerito il condimento."))
    monkeypatch.setattr(chat_router, "get_client", lambda db, user, role: finto)

    res = client.post(f"/api/chat/meals/{meal_id}/messages/stream", json={"content": "più leggero"})

    assert res.status_code == 200
    assert res.headers["x-accel-buffering"] == "no"
    assert finto.streaming
    eventi = _eventi(res)
    testo = "".join(e["delta"] for e in eventi if "delta" in e)
    assert testo.strip() == "Ho alleggerito il condimento."
    fine = eventi[-1]["done"]
    assert fine["recipe_updated"] is True
    assert fine["recipe"]["title"] == "Pasta al pesto di zucchine"
    # Come la POST normale: la modifica è scritta, non solo raccontata.
    assert client.get(f"/api/planning/meals/{meal_id}").json()["recipe"]["title"] == "Pasta al pesto di zucchine"


def test_un_errore_a_meta_arriva_come_evento(client, meal_id, monkeypatch):  # noqa: F811
    class Rotto:
        def chat(self, *a, **k):
            raise RuntimeError("rete giù")

    monkeypatch.setattr(chat_router, "get_client", lambda db, user, role: Rotto())
    res = client.post(f"/api/chat/meals/{meal_id}/messages/stream", json={"content": "ciao"})
    assert _eventi(res)[-1] == {"error": "Qualcosa è andato storto, riprova."}


def test_la_chat_della_spesa_in_streaming(client, meal_id, monkeypatch):  # noqa: F811
    finto = ChatAPezzi("Puoi prendere le zucchine surgelate, vanno bene uguale.")
    monkeypatch.setattr(chat_router, "get_client", lambda db, user, role: finto)
    week = client.get("/api/planning/weeks/current").json()

    res = client.post(f"/api/chat/shopping/{week['id']}/messages/stream", json={"content": "zucchine?"})

    eventi = _eventi(res)
    assert "".join(e.get("delta", "") for e in eventi).startswith("Puoi prendere")
    assert eventi[-1]["done"]["content"].startswith("Puoi prendere")
