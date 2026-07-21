"""Modelli che ragionano: controllo dell'effort e diagnosi delle risposte vuote.

Su OpenRouter il ragionamento è acceso di default sui modelli che lo supportano, e i
suoi token si scalano da `max_tokens`. Un modello a effort alto può quindi consumare
l'intero budget pensando e restituire contenuto vuoto — che senza spiegazioni sembra
un guasto, mentre è solo un modello sbagliato per il compito.
"""

import pytest

from app.services import ai_client
from app.services.ai_client import AIError, _empty_response_error


class _Choice:
    def __init__(self, content, finish_reason):
        self.message = type("M", (), {"content": content})()
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_Choice(content, finish_reason)]


class _Completions:
    """Finto endpoint chat/completions: registra come è stato chiamato."""

    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _backend(response):
    backend = ai_client._OpenAICompatibleBackend.__new__(ai_client._OpenAICompatibleBackend)
    import openai

    backend._openai = openai
    completions = _Completions(response)
    backend._client = type("C", (), {"chat": type("Ch", (), {"completions": completions})()})()
    return backend, completions


def _call(backend, *, thinking=False, max_tokens=8000):
    return backend.complete(
        model="z-ai/glm-5.2",
        system="sistema",
        messages=[{"role": "user", "content": "ciao"}],
        max_tokens=max_tokens,
        thinking=thinking,
    )


# ── Controllo dell'effort ──────────────────────────────────────────────────────


def test_i_compiti_brevi_chiedono_ragionamento_basso():
    backend, completions = _backend(_Response("Ecco la risposta."))

    _call(backend, thinking=False)

    assert completions.kwargs["extra_body"] == {"reasoning": {"effort": "low"}}


def test_la_pianificazione_chiede_ragionamento_alto():
    """Incastrare trenta pasti nei macro è l'unico punto in cui ragionare paga."""
    backend, completions = _backend(_Response("{}"))

    _call(backend, thinking=True)

    assert completions.kwargs["extra_body"] == {"reasoning": {"effort": "high"}}


def test_il_budget_di_token_arriva_al_fornitore():
    backend, completions = _backend(_Response("ok"))
    _call(backend, max_tokens=8000)
    assert completions.kwargs["max_tokens"] == 8000


# ── Diagnosi delle risposte vuote ──────────────────────────────────────────────


def test_budget_esaurito_lo_dice_chiaramente():
    backend, _ = _backend(_Response("", finish_reason="length"))

    with pytest.raises(AIError) as exc:
        _call(backend, max_tokens=8000)

    detail = exc.value.detail
    assert "esaurito i 8000 token" in detail
    assert "ragionano molto" in detail
    assert "Modelli AI" in detail  # dice anche dove si cambia


def test_contenuto_nullo_non_diventa_una_stringa_none():
    backend, _ = _backend(_Response(None, finish_reason="stop"))

    with pytest.raises(AIError) as exc:
        _call(backend)

    assert "risposta vuota" in exc.value.detail


def test_un_rifiuto_del_modello_si_riconosce():
    backend, _ = _backend(_Response("", finish_reason="content_filter"))

    with pytest.raises(AIError) as exc:
        _call(backend)

    assert "rifiutato" in exc.value.detail


def test_una_risposta_normale_passa_intatta():
    backend, _ = _backend(_Response("  Certo, puoi sostituire i fichi con le pere.  "))
    assert "fichi" in _call(backend)


@pytest.mark.parametrize(
    "finish_reason,atteso",
    [
        ("length", "esaurito"),
        ("content_filter", "rifiutato"),
        ("stop", "risposta vuota"),
        (None, "risposta vuota"),
    ],
)
def test_diagnosi_per_ogni_motivo_di_arresto(finish_reason, atteso):
    assert atteso in _empty_response_error("modello/x", 4000, finish_reason).detail
