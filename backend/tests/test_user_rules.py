"""Regole libere dell'utente: salvate come testo e passate al modello così come sono.

Sono le cose che non stanno in una lista di ingredienti — "niente insaccati", "carne
al massimo due volte a settimana". Non vanno interpretate: il destinatario è un
modello linguistico, e trasformarle in caselle perderebbe le sfumature.
"""

from app.services import planner
from app.services.planner import build_context
from tests.test_flow import FakeModel

REGOLE = "Niente insaccati.\nCarne rossa al massimo due volte a settimana."


def _set_rules(client, notes):
    prefs = client.get("/api/config/preferences").json()
    return client.put("/api/config/preferences", json={**prefs, "notes": notes})


def test_le_regole_si_salvano_e_si_rileggono(client):
    assert _set_rules(client, REGOLE).status_code == 200
    assert client.get("/api/config/preferences").json()["notes"] == REGOLE


def test_senza_regole_il_campo_e_vuoto(client):
    assert client.get("/api/config/preferences").json()["notes"] is None


def test_spazi_e_righe_vuote_non_diventano_una_regola(client):
    _set_rules(client, "   \n  ")
    assert client.get("/api/config/preferences").json()["notes"] is None


def test_le_regole_finiscono_nel_contesto_dei_prompt(client, db, diet):
    _set_rules(client, REGOLE)

    from app.models import User

    context = build_context(db, db.query(User).one().id)

    assert "Niente insaccati" in context
    assert "Carne rossa al massimo due volte a settimana" in context
    # Presentate come vincolo, non come nota di colore.
    assert "REGOLE SCRITTE DALL'UTENTE" in context


def test_senza_regole_il_contesto_lo_dice(client, db, diet):
    from app.models import User

    context = build_context(db, db.query(User).one().id)
    assert "REGOLE SCRITTE DALL'UTENTE, da rispettare alla lettera come i macro: nessuna" in context


def test_le_regole_arrivano_alla_generazione_settimanale(client, db, diet, monkeypatch):
    """Il punto è tutto qui: il modello le deve vedere mentre costruisce il piano."""
    _set_rules(client, REGOLE)

    visti = {}

    class SpiaModel(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            visti["prompt"] = prompt
            return super().generate_json(system, prompt, **kwargs)

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: SpiaModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta"})

    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert "Niente insaccati" in visti["prompt"]


def test_una_regola_lunghissima_viene_rifiutata(client):
    prefs = client.get("/api/config/preferences").json()
    res = client.put("/api/config/preferences", json={**prefs, "notes": "x" * 2001})
    assert res.status_code == 422  # il prompt si rimanda a ogni generazione: ha un tetto
