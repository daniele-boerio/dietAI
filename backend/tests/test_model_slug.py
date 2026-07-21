"""Slug del modello: forma giusta per il provider attivo.

`claude-opus-4-8` va bene con l'SDK Anthropic, ma su OpenRouter è `anthropic/claude-opus-4-8`.
Scambiarli è l'errore naturale quando si cambia provider lasciandosi dietro una
variabile d'ambiente, e senza controlli arriva fino a una 400 del fornitore in mezzo
alla generazione — trenta secondi buttati e un messaggio che non dice cosa fare.
"""

import httpx
import openai
import pytest

from app import config
from app.services import ai_client
from app.services.ai_client import _provider_message, model_for
from app.models import User, UserPreferences


@pytest.mark.parametrize(
    "provider,model,valido",
    [
        ("openrouter", "anthropic/claude-opus-4-8", True),
        ("openrouter", "z-ai/glm-5.2", True),
        ("openrouter", "claude-opus-4-8", False),  # ID nudo: manca il fornitore
        ("openrouter", "", False),
        ("anthropic", "claude-opus-4-8", True),
        ("anthropic", "anthropic/claude-opus-4-8", False),  # slug di troppo
    ],
)
def test_forma_dello_slug(monkeypatch, provider, model, valido):
    monkeypatch.setattr(config, "AI_PROVIDER", provider)
    assert config.model_matches_provider(model) is valido


def test_una_env_var_rimasta_indietro_non_rompe_la_generazione(monkeypatch, caplog):
    """AI_MODEL_PLANNING con l'ID Anthropic mentre il provider è OpenRouter."""
    monkeypatch.setattr(config, "AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODEL_PLANNING", "claude-opus-4-8")

    with caplog.at_level("WARNING"):
        model = config.default_model("planning")

    assert model == "anthropic/claude-opus-4-8"  # il default del provider
    assert "AI_MODEL_PLANNING" in caplog.text  # e lo dice, non lo nasconde


def test_una_env_var_valida_viene_rispettata(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_MODEL_CHAT", "z-ai/glm-5.2")
    assert config.default_model("chat") == "z-ai/glm-5.2"


def test_un_modello_salvato_per_un_altro_provider_viene_ignorato(client, db, monkeypatch):
    user = db.query(User).one()
    db.add(UserPreferences(user_id=user.id, ai_model_planning="claude-opus-4-8"))
    db.commit()

    monkeypatch.setattr(ai_client, "AI_PROVIDER", "openrouter")
    monkeypatch.setattr(config, "AI_PROVIDER", "openrouter")

    assert model_for(db, user.id, "planning") == "anthropic/claude-opus-4-8"


def test_l_endpoint_rifiuta_uno_slug_senza_fornitore(client):
    res = client.put("/api/config/ai/models", json={"planning": "claude-opus-4-8"})

    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "non è un modello valido" in detail
    assert "anthropic/claude-opus-4-8" in detail  # dice anche come si scrive


def test_l_endpoint_accetta_uno_slug_completo(client):
    res = client.put("/api/config/ai/models", json={"planning": "z-ai/glm-5.2"})

    assert res.status_code == 200
    roles = {r["key"]: r for r in res.json()["roles"]}
    assert roles["planning"]["model"] == "z-ai/glm-5.2"


def test_il_messaggio_del_fornitore_arriva_all_utente():
    """Su una 400 il fornitore dice esattamente cosa non va: non va sprecato."""
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(400, request=request)
    exc = openai.BadRequestError(
        "Error code: 400",
        response=response,
        body={"error": {"message": "claude-opus-4-8 is not a valid model ID", "code": 400}},
    )

    assert _provider_message(exc) == "claude-opus-4-8 is not a valid model ID"


def test_se_il_fornitore_non_spiega_niente_si_usa_il_messaggio_dell_eccezione():
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    exc = openai.BadRequestError(
        "Qualcosa è andato storto", response=httpx.Response(400, request=request), body=None
    )
    assert "Qualcosa è andato storto" in _provider_message(exc)
