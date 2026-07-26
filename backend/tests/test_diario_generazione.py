"""Il diario della generazione: far vedere cosa sta scrivendo il modello.

Una generazione dura minuti e si paga. Senza niente sotto gli occhi non c'è modo di
distinguere un modello che sta ragionando da uno piantato, né di capire a che punto
è. I pezzi passano già in streaming dentro `ai_client`: qui si controlla che arrivino
fino alla pagina, e che a fine corsa non resti niente appeso.
"""

from datetime import datetime, timezone

import pytest

from app.models import WeekPlan
from app.services import ai_client, planner
from app.services.planner import GenerationProgress
from tests.test_flow import DAYS, FakeModel


# ── Streaming: i pezzi arrivano a chi guarda ───────────────────────────────────


class _Delta:
    def __init__(self, content=None, **extra):
        self.content = content
        for chiave, valore in extra.items():
            setattr(self, chiave, valore)


class _Chunk:
    def __init__(self, delta, finish_reason=None):
        self.choices = [type("Ch", (), {"delta": delta, "finish_reason": finish_reason})()]


class _Completions:
    def __init__(self, chunks):
        self.chunks = chunks

    def create(self, **kwargs):
        assert kwargs.get("stream") is True
        return iter(self.chunks)


def _backend(chunks):
    backend = ai_client._OpenAICompatibleBackend.__new__(ai_client._OpenAICompatibleBackend)
    import openai

    backend._openai = openai
    completions = _Completions(chunks)
    backend._client = type("C", (), {"chat": type("Ch", (), {"completions": completions})()})()
    return backend


def _chiama(backend, on_progress=None):
    # Sopra la soglia di streaming: è la strada della generazione settimanale.
    return backend.complete(
        model="z-ai/glm-5.2",
        system="sistema",
        messages=[{"role": "user", "content": "genera"}],
        max_tokens=48000,
        thinking=True,
        on_progress=on_progress,
    )


def test_ragionamento_e_testo_arrivano_separati():
    backend = _backend(
        [
            _Chunk(_Delta(reasoning="Vediamo i macro")),
            _Chunk(_Delta(reasoning=" del lunedì.")),
            _Chunk(_Delta(content='{"days":')),
            _Chunk(_Delta(content=" []}"), finish_reason="stop"),
        ]
    )
    visti = []

    testo = _chiama(backend, on_progress=lambda kind, delta: visti.append((kind, delta)))

    assert testo == '{"days": []}'
    assert visti == [
        ("reasoning", "Vediamo i macro"),
        ("reasoning", " del lunedì."),
        ("content", '{"days":'),
        ("content", " []}"),
    ]


def test_il_ragionamento_si_riconosce_anche_con_l_altro_nome():
    """`reasoning` su OpenRouter, `reasoning_content` altrove: sono lo stesso campo."""
    backend = _backend([_Chunk(_Delta(reasoning_content="Ci penso"), "stop"), _Chunk(_Delta("ok"))])
    visti = []

    _chiama(backend, on_progress=lambda kind, delta: visti.append((kind, delta)))

    assert ("reasoning", "Ci penso") in visti


def test_senza_nessuno_che_guarda_lo_streaming_resta_quello_di_prima():
    backend = _backend([_Chunk(_Delta(content="ciao"), "stop")])
    assert _chiama(backend) == "ciao"


# ── Quello che finisce nel database ────────────────────────────────────────────


def test_il_diario_tiene_la_coda_e_i_conti():
    progress = GenerationProgress(week_id=1, expected_recipes=21)

    progress("reasoning", "penso " * 1000)
    progress("content", '{"title": "Pasta", "title": "Riso"')

    diario = progress.snapshot()
    assert len(diario["reasoning"]) == GenerationProgress.REASONING_TAIL
    assert diario["reasoning_chars"] == 6000
    # Le ricette scritte si contano dalle chiavi "title": è il modo più economico di
    # sapere a che punto è senza parsare un JSON ancora a metà.
    assert diario["recipes_written"] == 2
    assert diario["expected_recipes"] == 21


def test_la_coda_e_davvero_la_fine():
    progress = GenerationProgress(week_id=1)
    progress("reasoning", "x" * 5000 + "ULTIMA RIGA")

    assert progress.snapshot()["reasoning"].endswith("ULTIMA RIGA")


def test_senza_sessione_il_diario_non_esplode():
    """Il diario è un di più: se non si può scrivere, la generazione va avanti."""
    progress = GenerationProgress(week_id=1)
    progress.flush()  # nessuna eccezione


# ── L'endpoint che guarda la pagina ────────────────────────────────────────────


@pytest.fixture()
def api_key(client):
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})


def _week(db) -> WeekPlan:
    week = db.query(WeekPlan).first()
    db.refresh(week)
    return week


def test_a_riposo_il_diario_e_vuoto(client, diet):
    week = client.get("/api/planning/weeks/current").json()

    res = client.get(f"/api/planning/weeks/{week['id']}/progress").json()

    assert res["is_generating"] is False
    assert res.get("reasoning") is None


def test_durante_la_generazione_la_pagina_legge_il_diario(client, diet, db):
    week = client.get("/api/planning/weeks/current").json()
    riga = _week(db)
    riga.generation_started_at = datetime.now(timezone.utc)
    riga.generation_progress = {
        "reasoning": "Il lunedì lo apro con qualcosa di leggero",
        "content": '{"days": [',
        "reasoning_chars": 41,
        "content_chars": 10,
        "recipes_written": 3,
        "expected_recipes": 21,
    }
    db.commit()

    res = client.get(f"/api/planning/weeks/{week['id']}/progress").json()

    assert res["is_generating"] is True
    assert res["started_at"] is not None
    assert "leggero" in res["reasoning"]
    assert res["recipes_written"] == 3
    assert res["expected_recipes"] == 21


def test_finita_la_generazione_non_resta_niente_appeso(
    client, diet, db, monkeypatch, api_key
):
    """Il diario è la fotografia di adesso: se sopravvivesse, la volta dopo si
    vedrebbe il ragionamento della settimana scorsa."""
    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: FakeModel(user))

    week = client.get("/api/planning/weeks/current").json()
    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert res.status_code == 200, res.text
    assert res.json()["generation"]["filled"] == DAYS * 3
    assert _week(db).generation_progress is None


def test_una_generazione_fallita_non_lascia_il_diario(client, diet, db, monkeypatch, api_key):
    class ModelloRotto(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            raise ai_client.AIError("il fornitore è esploso")

    monkeypatch.setattr(planner, "get_client", lambda db_, user, role: ModelloRotto(user))

    week = client.get("/api/planning/weeks/current").json()
    assert client.post(f"/api/planning/weeks/{week['id']}/generate").status_code == 502

    riga = _week(db)
    assert riga.generation_started_at is None
    assert riga.generation_progress is None
