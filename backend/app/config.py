"""Configurazione centralizzata: tutte le env var si leggono da qui."""

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

# --- Modelli Claude ---
# Opus per la generazione (rispettare i macro su 7 giorni è un problema di
# pianificazione, non di scrittura); lo stesso modello regge la chat, dove però
# il contesto è molto più piccolo e quindi costa poco.
AI_MODEL_PLANNING = os.getenv("AI_MODEL_PLANNING", "claude-opus-4-8")
AI_MODEL_CHAT = os.getenv("AI_MODEL_CHAT", "claude-opus-4-8")

# Quante volte ritentare una risposta AI non parsabile come JSON prima di arrendersi.
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", 3))
