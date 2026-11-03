"""La cache del prompt sui modelli Anthropic.

Il prompt di sistema (regole, dieta, contesto) è lungo e sempre uguale fra le
chiamate vicine: i pezzi della settimana generati in parallelo, i messaggi di una
chat. Chiesto in cache, chi lo ripete entro cinque minuti parte prima e lo paga un
decimo. Anthropic la vuole chiesta (`cache_control`); gli altri la fanno da sé.
"""

from tests.test_reasoning_budget import _anthropic_backend, _backend, _Response


def _chiama(backend, model):
    backend.complete(
        model=model, system="regole lunghe", messages=[{"role": "user", "content": "ciao"}],
        max_tokens=2000, thinking=False,
    )


def test_su_openrouter_i_modelli_anthropic_chiedono_la_cache():
    backend, completions = _backend(_Response("ok"))
    _chiama(backend, "anthropic/claude-opus-4-8")
    sistema = completions.kwargs["messages"][0]
    assert sistema["role"] == "system"
    assert sistema["content"] == [
        {"type": "text", "text": "regole lunghe", "cache_control": {"type": "ephemeral"}}
    ]


def test_gli_altri_modelli_ricevono_il_testo_semplice():
    backend, completions = _backend(_Response("ok"))
    _chiama(backend, "z-ai/glm-5.2")
    assert completions.kwargs["messages"][0] == {"role": "system", "content": "regole lunghe"}


def test_sull_sdk_anthropic_il_sistema_va_in_cache():
    backend, messages = _anthropic_backend()
    _chiama(backend, "claude-opus-4-8")
    assert messages.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
