"""Catalogo dei modelli: normalizzazione, cache e nessun troncamento.

Il payload di esempio ricalca quello vero di OpenRouter (prezzi come stringhe per
singolo token, modalità di input dentro `architecture`): se cambiassero forma, questi
test lo direbbero prima che il selettore si svuoti in silenzio.
"""

import httpx
import pytest

from app.services import catalog


@pytest.fixture(autouse=True)
def reset_cache():
    catalog._cache = None
    yield
    catalog._cache = None


PAYLOAD = {
    "data": [
        {
            "id": "z-ai/glm-5.2",
            "name": "Z.AI: GLM 5.2",
            "context_length": 200000,
            "pricing": {"prompt": "0.0000004", "completion": "0.0000016"},
            "architecture": {"input_modalities": ["text"]},
        },
        {
            "id": "anthropic/claude-opus-4-8",
            "name": "Anthropic: Claude Opus 4.8",
            "context_length": 1000000,
            "pricing": {"prompt": "0.000005", "completion": "0.000025"},
            "architecture": {"input_modalities": ["text", "image"]},
        },
        {
            "id": "senza/prezzo",
            "name": "Modello senza listino",
            "context_length": None,
            "pricing": {},
            "architecture": {},
        },
        {"name": "Voce rotta senza id"},
    ]
}


def _fake_get(payload=PAYLOAD, calls=None):
    def get(url, timeout=None):
        if calls is not None:
            calls.append(url)
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    return get


def test_i_prezzi_diventano_per_milione_di_token(monkeypatch):
    monkeypatch.setattr(catalog.httpx, "get", _fake_get())

    models = {m["id"]: m for m in catalog.list_models()}

    # OpenRouter espone il prezzo del singolo token, come stringa.
    assert models["anthropic/claude-opus-4-8"]["prompt_price"] == 5.0
    assert models["anthropic/claude-opus-4-8"]["completion_price"] == 25.0
    assert models["z-ai/glm-5.2"]["completion_price"] == 1.6
    # Nessun listino: None, non zero — "gratis" sarebbe una bugia.
    assert models["senza/prezzo"]["prompt_price"] is None


def test_si_riconoscono_i_modelli_che_leggono_le_immagini(monkeypatch):
    monkeypatch.setattr(catalog.httpx, "get", _fake_get())

    models = {m["id"]: m for m in catalog.list_models()}

    # Serve a suggerire il modello giusto per una dieta scansionata.
    assert models["anthropic/claude-opus-4-8"]["supports_images"] is True
    assert models["z-ai/glm-5.2"]["supports_images"] is False
    assert models["senza/prezzo"]["supports_images"] is False


def test_le_voci_senza_id_vengono_scartate(monkeypatch):
    monkeypatch.setattr(catalog.httpx, "get", _fake_get())
    assert len(catalog.list_models()) == 3


def test_ordinamento_per_nome(monkeypatch):
    monkeypatch.setattr(catalog.httpx, "get", _fake_get())
    assert [m["id"] for m in catalog.list_models()][0] == "anthropic/claude-opus-4-8"


def test_il_catalogo_viene_messo_in_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(catalog.httpx, "get", _fake_get(calls=calls))

    catalog.list_models()
    catalog.list_models()
    assert len(calls) == 1  # il listino non cambia a ogni apertura della pagina

    catalog.list_models(force=True)
    assert len(calls) == 2


def test_se_il_provider_non_risponde_non_si_rompe_niente(monkeypatch):
    def boom(url, timeout=None):
        raise httpx.ConnectError("rete assente")

    monkeypatch.setattr(catalog.httpx, "get", boom)
    # Lista vuota: il frontend ripiega sul campo di testo libero.
    assert catalog.list_models() == []


def test_se_il_provider_cade_dopo_si_riusa_la_cache(monkeypatch):
    monkeypatch.setattr(catalog.httpx, "get", _fake_get())
    catalog.list_models()

    def boom(url, timeout=None):
        raise httpx.ConnectError("rete assente")

    monkeypatch.setattr(catalog.httpx, "get", boom)
    assert len(catalog.list_models(force=True)) == 3


# ── Endpoint ───────────────────────────────────────────────────────────────────


def test_l_endpoint_restituisce_tutto_il_catalogo(client, monkeypatch):
    """Nessun troncamento: un tetto qui renderebbe introvabili i modelli in fondo
    all'alfabeto, perché la ricerca del selettore lavora sulla lista ricevuta."""
    tanti = {
        "data": [
            {
                "id": f"provider/modello-{i:03}",
                "name": f"Modello {i:03}",
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "architecture": {"input_modalities": ["text"]},
            }
            for i in range(342)  # quanti ne espone OpenRouter davvero
        ]
    }
    monkeypatch.setattr(catalog.httpx, "get", _fake_get(tanti))

    data = client.get("/api/config/ai/models").json()

    assert data["total"] == 342
    assert len(data["models"]) == 342


def test_l_endpoint_filtra_lato_server_se_glielo_si_chiede(client, monkeypatch):
    monkeypatch.setattr(catalog.httpx, "get", _fake_get())

    data = client.get("/api/config/ai/models", params={"q": "glm"}).json()

    assert data["total"] == 1
    assert data["models"][0]["id"] == "z-ai/glm-5.2"
