"""Stato "generazione in corso": vive nel database, non nella pagina.

Serve a due cose. La prima è ritrovare il caricamento tornando sulla pagina — o dopo
un F5 — invece di vedere una settimana mezza vuota senza capire perché. La seconda,
più importante, è non pagare due volte: senza questo stato bastava ricaricare e
ripremere il pulsante per far partire una seconda generazione in parallelo.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import WeekPlan
from app.services import planner
from app.services.ai_client import AIError
from tests.test_flow import DAYS, FakeModel


@pytest.fixture()
def api_key(client):
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


def _week(db) -> WeekPlan:
    week = db.query(WeekPlan).first()
    db.refresh(week)
    return week


def test_a_riposo_la_settimana_non_sta_generando(client, diet):
    assert client.get("/api/planning/weeks/current").json()["is_generating"] is False


def test_durante_la_generazione_lo_stato_e_visibile_nel_database(
    client, diet, db, monkeypatch, api_key
):
    visto = {}

    class ModelloSpia(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            # Siamo dentro la chiamata al modello: qui la settimana deve già
            # risultare "in generazione" per chiunque la legga.
            visto["in_corso"] = planner.is_generating(_week(db))
            return super().generate_json(system, prompt, **kwargs)

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: ModelloSpia(user))

    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert visto["in_corso"] is True
    assert res.json()["is_generating"] is False  # a fine corsa il segno sparisce
    assert _week(db).generation_started_at is None


def test_una_seconda_generazione_in_parallelo_viene_rifiutata(client, diet, db, api_key):
    """È il caso del ricarico pagina + secondo clic: costerebbe il doppio."""
    week = client.get("/api/planning/weeks/current").json()
    _week(db).generation_started_at = datetime.now(timezone.utc)
    db.commit()

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert res.status_code == 409
    assert "già una generazione in corso" in res.json()["detail"]


def test_la_pagina_ritrova_la_generazione_in_corso(client, diet, db, api_key):
    client.get("/api/planning/weeks/current")  # la settimana nasce alla prima lettura
    _week(db).generation_started_at = datetime.now(timezone.utc)
    db.commit()

    # È quello a cui si aggancia il frontend per rimettere il caricamento.
    assert client.get("/api/planning/weeks/current").json()["is_generating"] is True


def test_una_generazione_dimenticata_scade(client, diet, db, monkeypatch, api_key):
    """Se il processo muore a metà, la settimana non deve restare bloccata per sempre."""
    week = client.get("/api/planning/weeks/current").json()
    _week(db).generation_started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    db.commit()

    assert client.get("/api/planning/weeks/current").json()["is_generating"] is False

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: FakeModel(user))
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert res.status_code == 200
    assert res.json()["generation"]["filled"] == DAYS * 3


def test_se_il_modello_fallisce_lo_stato_viene_ripulito(client, diet, db, monkeypatch, api_key):
    """Altrimenti un errore lascerebbe la settimana in "sto generando" per un quarto d'ora."""

    class ModelloRotto(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            raise AIError("il fornitore è esploso")

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: ModelloRotto(user))

    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert res.status_code == 502
    assert _week(db).generation_started_at is None
    # E infatti si può riprovare subito.
    assert client.get("/api/planning/weeks/current").json()["is_generating"] is False


# ── Com'è finita ───────────────────────────────────────────────────────────────
#
# Una generazione dura minuti e la risposta della POST non arriva quasi mai a
# destinazione: davanti c'è un proxy che chiude molto prima (nginx a 300s, Cloudflare a
# 100s) e a quel punto il messaggio d'errore viene scritto su una connessione morta.
# Chi guarda vede solo il polling, e "non sta più generando" da solo non distingue una
# settimana riuscita da una fallita: annunciava "Settimana pronta ✓" in tutti e due i
# casi. L'esito deve quindi restare sulla settimana, come lo stato di prima.


def _fallisci(monkeypatch, messaggio="il fornitore è esploso"):
    class ModelloRotto(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            raise AIError(messaggio)

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: ModelloRotto(user))


def test_il_motivo_del_fallimento_resta_sulla_settimana(client, diet, monkeypatch, api_key):
    _fallisci(monkeypatch, "il modello ha esaurito i token")
    week = client.get("/api/planning/weeks/current").json()

    client.post(f"/api/planning/weeks/{week['id']}/generate")

    dopo = client.get("/api/planning/weeks/current").json()
    assert dopo["is_generating"] is False
    assert "esaurito i token" in dopo["generation_error"]
    # Anche da qui: è l'endpoint che la pagina interroga mentre aspetta.
    progresso = client.get(f"/api/planning/weeks/{week['id']}/progress").json()
    assert "esaurito i token" in progresso["error"]


def test_una_risposta_di_forma_sbagliata_non_blocca_la_settimana(
    client, diet, db, monkeypatch, api_key
):
    """JSON valido ma senza `days`: sollevava fuori dal try, e la settimana restava
    ferma su "sto generando" per un quarto d'ora senza che nessuno lo sapesse."""

    class ModelloConfuso(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            return {"giorni": []}

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: ModelloConfuso(user))

    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert res.status_code == 502
    assert _week(db).generation_started_at is None
    assert client.get("/api/planning/weeks/current").json()["generation_error"]


def test_una_generazione_riuscita_cancella_l_errore_di_prima(
    client, diet, monkeypatch, api_key
):
    """L'errore racconta l'ultimo tentativo, non è una macchia sulla settimana."""
    _fallisci(monkeypatch)
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")
    assert client.get("/api/planning/weeks/current").json()["generation_error"]

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: FakeModel(user))
    assert client.post(f"/api/planning/weeks/{week['id']}/generate").status_code == 200

    assert client.get("/api/planning/weeks/current").json()["generation_error"] is None
