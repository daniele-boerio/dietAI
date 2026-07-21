"""Configurazione centralizzata: tutte le env var si leggono da qui."""

import logging
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Carica backend/.env quando si gira in locale. In Docker il file non esiste e le
# variabili arrivano dall'ambiente: load_dotenv non fa nulla e non solleva.
load_dotenv()


def _clean(value: str | None) -> str:
    """Ripulisce un segreto letto dall'ambiente.

    Incollando un valore in un pannello web (Coolify) capita di portarsi dietro
    virgolette, spazi o un a capo. Per SECRET_KEY passerebbe inosservato — cambia
    solo la firma dei token — ma una chiave Fernet con un apice attaccato smette di
    essere valida, e l'errore che si vede ("chiave non valida") non fa sospettare
    la punteggiatura.
    """
    return (value or "").strip().strip("\"'").strip()


# --- Database ---
DB_USER = os.getenv("DB_USER", "dietai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "dietai")

# quote_plus sulla password: se contiene @ / : # (Coolify le genera casuali) senza
# escaping romperebbe il parsing dell'URL.
DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# --- Auth ---
SECRET_KEY = _clean(os.getenv("SECRET_KEY"))
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# L'access token è a vita breve: sta in un cookie httpOnly, ma se comunque trapelasse
# la finestra di abuso è di minuti. La sessione lunga la regge il refresh token.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 90))

# In locale si gira su http: con Secure attivo il browser scarterebbe i cookie
# e il login non funzionerebbe mai. In produzione deve restare true.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() != "false"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

# --- Crittografia della API key Claude ---
# Chiave Fernet (AES-128-CBC + HMAC) generata con:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Senza, la API key dell'utente non è salvabile: gli endpoint che la usano rispondono 503.
ENCRYPTION_KEY = _clean(os.getenv("ENCRYPTION_KEY"))

# --- Utente seed ---
# L'app è single-user: l'utente non si registra, viene creato da `python -m app.seed`.
SEED_USER_EMAIL = os.getenv("SEED_USER_EMAIL", "utente@dietai.local")
SEED_USER_PASSWORD = os.getenv("SEED_USER_PASSWORD", "")

# --- Provider AI ---
# "openrouter": una chiave sola per tutti i modelli di tutti i fornitori, API
#   OpenAI-compatibile. È il default perché permette di cambiare modello senza
#   toccare il codice né aprire altri account.
# "anthropic": SDK ufficiale, l'unico che sa leggere un PDF nativamente (serve
#   solo per le diete scansionate: vedi services/pdf.py).
AI_PROVIDER = (_clean(os.getenv("AI_PROVIDER")) or "openrouter").lower()

AI_BASE_URL = _clean(os.getenv("AI_BASE_URL")) or "https://openrouter.ai/api/v1"

# Modelli di default per ruolo. L'utente li cambia dalla UI (finiscono in
# user_preferences); questi valgono finché non lo fa.
#
# Perché ruoli diversi: la pianificazione settimanale è un problema di incastro
# (macro, ripetizioni, avanzi) e vuole il modello più capace; la chat sono tante
# chiamate piccole su compiti facili; la lettura della dieta si fa tre volte l'anno.
_DEFAULTS = {
    "openrouter": {
        "planning": "anthropic/claude-opus-4-8",
        "chat": "anthropic/claude-opus-4-8",
        "diet": "anthropic/claude-opus-4-8",
    },
    "anthropic": {
        "planning": "claude-opus-4-8",
        "chat": "claude-opus-4-8",
        "diet": "claude-opus-4-8",
    },
}


def model_matches_provider(model: str) -> bool:
    """Il nome del modello ha la forma giusta per il provider configurato?

    Su OpenRouter gli slug portano il fornitore davanti (`anthropic/claude-opus-4-8`);
    l'SDK Anthropic vuole l'ID nudo (`claude-opus-4-8`). Scambiarli è l'errore che
    capita passando da un provider all'altro e lasciandosi dietro una variabile
    d'ambiente, e senza questo controllo si manifesta come una 400 del fornitore alla
    prima generazione — mezzo minuto dopo, con un messaggio che non dice cosa fare.
    """
    model = (model or "").strip()
    if not model:
        return False
    return ("/" in model) if AI_PROVIDER == "openrouter" else ("/" not in model)


def default_model(role: str) -> str:
    fallback = _DEFAULTS.get(AI_PROVIDER, _DEFAULTS["openrouter"])[role]
    env = _clean(os.getenv(f"AI_MODEL_{role.upper()}"))
    if not env:
        return fallback

    if not model_matches_provider(env):
        logging.getLogger(__name__).warning(
            "AI_MODEL_%s vale %r, che non è un modello valido per il provider %r: "
            "uso %r. Con OpenRouter serve lo slug completo, tipo 'anthropic/%s'.",
            role.upper(),
            env,
            AI_PROVIDER,
            fallback,
            env,
        )
        return fallback
    return env


# Prefisso atteso per la chiave, per accorgersi subito di un incollaggio sbagliato.
API_KEY_PREFIX = {"openrouter": "sk-or-", "anthropic": "sk-ant-"}.get(AI_PROVIDER, "")

API_KEY_URL = {
    "openrouter": "https://openrouter.ai/keys",
    "anthropic": "https://console.anthropic.com/settings/keys",
}.get(AI_PROVIDER, "")

# Quante volte ritentare una risposta AI non parsabile come JSON prima di arrendersi.
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 3))
