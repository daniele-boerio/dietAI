"""Catalogo dei modelli disponibili sul provider.

Serve a togliere di mezzo il problema degli slug: invece di far digitare
`z-ai/glm-4.6` a memoria (e scoprire l'errore di battitura solo alla prima
generazione), il frontend fa scegliere da una lista con nome, prezzo e finestra di
contesto. La lista arriva dal provider, quindi comprende anche i modelli usciti dopo
che questo codice è stato scritto.
"""

import logging
import time

import httpx

from ..config import AI_BASE_URL, AI_PROVIDER

logger = logging.getLogger(__name__)

_CACHE_TTL = 3600  # un'ora: il listino non cambia a ogni apertura della pagina
_cache: tuple[float, list[dict]] | None = None


def _price_per_million(value) -> float | None:
    """OpenRouter espone i prezzi per singolo token, come stringa."""
    try:
        return round(float(value) * 1_000_000, 2)
    except (TypeError, ValueError):
        return None


def _normalize(entry: dict) -> dict:
    pricing = entry.get("pricing") or {}
    architecture = entry.get("architecture") or {}
    modalities = architecture.get("input_modalities") or []
    return {
        "id": entry.get("id"),
        "name": entry.get("name") or entry.get("id"),
        "context_length": entry.get("context_length"),
        "prompt_price": _price_per_million(pricing.get("prompt")),
        "completion_price": _price_per_million(pricing.get("completion")),
        # Un modello che accetta immagini è quello che può leggere una dieta
        # scansionata: al frontend serve saperlo per suggerirlo sul ruolo "diet".
        "supports_images": "image" in modalities,
    }


def list_models(force: bool = False) -> list[dict]:
    """Modelli disponibili, ordinati per nome. Lista vuota se il provider non li espone."""
    global _cache

    if AI_PROVIDER != "openrouter":
        return []

    now = time.time()
    if _cache and not force and _cache[0] > now:
        return _cache[1]

    try:
        # Endpoint pubblico: non serve la chiave dell'utente, quindi il catalogo si
        # può mostrare anche prima che ne abbia inserita una.
        response = httpx.get(f"{AI_BASE_URL}/models", timeout=15)
        response.raise_for_status()
        raw = response.json().get("data") or []
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Catalogo modelli non disponibile: %s", exc)
        return _cache[1] if _cache else []

    models = [_normalize(m) for m in raw if m.get("id")]
    models.sort(key=lambda m: m["name"].lower())
    _cache = (now + _CACHE_TTL, models)
    return models
