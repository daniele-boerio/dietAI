"""Client AI: unico punto da cui si parla con un modello, qualunque sia il fornitore.

Due backend dietro la stessa interfaccia:

- **openrouter** (default): API OpenAI-compatibile. Una chiave sola dà accesso ai
  modelli di tutti i fornitori — Claude, GLM, DeepSeek, Qwen, Gemini — e cambiare
  modello è cambiare una stringa, non il codice.
- **anthropic**: SDK ufficiale. Serve per una cosa sola che l'altro non fa in modo
  affidabile: leggere un PDF nativamente (le diete scansionate).

Il modello si sceglie **per ruolo** (`planning`, `chat`, `diet`), perché i tre compiti
non hanno lo stesso peso: incastrare trenta pasti dentro i macro è difficile, rispondere
"posso preparalo la sera prima?" no.

Tre cose valgono per ogni chiamata e quindi stanno qui:

1. La chiave è dell'utente e sta cifrata nel DB. Viene decifrata solo qui, il più tardi
   possibile, e non finisce mai in un log o in una risposta HTTP.
2. Le generazioni lunghe (il piano settimanale) vanno in streaming: con `max_tokens`
   alto una richiesta non-streaming sbatte contro il timeout HTTP.
3. I prompt chiedono JSON puro, ma un modello ogni tanto lo incarta nei backtick o ci
   scrive una frase davanti. `_extract_json` recupera quei casi, e su fallimento si
   ritenta: molto più economico che far vedere un errore all'utente.
"""

import json
import logging
import re
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import (
    AI_BASE_URL,
    AI_MAX_RETRIES,
    AI_PROVIDER,
    default_model,
)
from ..crypto import decrypt_api_key
from ..models import User, UserPreferences

logger = logging.getLogger(__name__)

ROLES = ("planning", "chat", "diet")

# Oltre questa soglia si passa in streaming (vedi punto 2 nel docstring).
_STREAM_THRESHOLD = 8000


class AIError(HTTPException):
    """Errore parlante verso l'utente: la UI mostra `detail` così com'è."""

    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(status_code=status_code, detail=detail)


def _extract_json(text: str) -> dict | list:
    """Estrae l'oggetto JSON da una risposta del modello.

    Prova nell'ordine: parse diretto, blocco ```json ... ```, primo oggetto/array
    bilanciato nel testo. Solleva ValueError se non ne esce nulla.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Scansione a contatore di parentesi: una regex non basta, i JSON sono annidati.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError("Nessun JSON valido nella risposta del modello")


# ── Backend ────────────────────────────────────────────────────────────────────


class _AnthropicBackend:
    """SDK ufficiale Anthropic. L'unico che legge PDF nativamente."""

    supports_native_pdf = True

    def __init__(self, api_key: str):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=600)

    def complete(self, *, model, system, messages, max_tokens, thinking) -> str:
        params: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if thinking:
            params["thinking"] = {"type": "adaptive"}
            params["output_config"] = {"effort": "high"}

        anthropic = self._anthropic
        try:
            if max_tokens > _STREAM_THRESHOLD:
                with self._client.messages.stream(**params) as stream:
                    message = stream.get_final_message()
            else:
                message = self._client.messages.create(**params)
        except anthropic.AuthenticationError:
            raise AIError("API key non valida. Controllala in Impostazioni → Account.", 400)
        except anthropic.PermissionDeniedError:
            raise AIError("La tua API key non ha accesso a questo modello.", 400)
        except anthropic.NotFoundError:
            raise AIError(f"Il modello '{model}' non esiste per questa API key.", 400)
        except anthropic.RateLimitError:
            raise AIError("Limite di frequenza raggiunto. Riprova tra qualche minuto.", 429)
        except anthropic.APIConnectionError:
            raise AIError("Impossibile contattare il fornitore del modello.")
        except anthropic.APIStatusError as exc:
            logger.warning("Errore API Anthropic %s: %s", exc.status_code, exc.message)
            raise AIError(f"Errore dal fornitore ({exc.status_code}). Riprova.")

        if message.stop_reason == "refusal":
            raise AIError("Il modello ha rifiutato di rispondere a questa richiesta.")

        # Con il thinking attivo i primi blocchi sono di tipo "thinking": si tiene
        # solo il testo, che è l'unica cosa che ci interessa.
        return "".join(b.text for b in message.content if b.type == "text")

    def complete_with_pdf(self, *, model, system, pdf_b64, prompt) -> str:
        """Manda il PDF così com'è: serve per le diete scansionate, dove non c'è testo
        da estrarre e ci vuole un modello che veda la pagina."""
        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_b64,
                },
            },
            {"type": "text", "text": prompt},
        ]
        return self.complete(
            model=model,
            system=system,
            messages=[{"role": "user", "content": content}],
            max_tokens=8000,
            thinking=False,
        )


class _OpenAICompatibleBackend:
    """Qualunque endpoint OpenAI-compatibile: OpenRouter, e volendo altri."""

    supports_native_pdf = False

    def __init__(self, api_key: str):
        import openai

        self._openai = openai
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=AI_BASE_URL,
            timeout=600,
            # OpenRouter usa questi header per l'attribuzione: sono facoltativi e
            # non identificano l'utente, solo l'applicazione.
            default_headers={"X-Title": "DietAI"},
        )

    def complete(self, *, model, system, messages, max_tokens, thinking) -> str:
        # `thinking` non ha un equivalente unico tra i fornitori: chi ragiona lo fa
        # da sé in base al prompt, quindi qui si ignora invece di inventare un
        # parametro che alcuni modelli rifiuterebbero.
        payload = [{"role": "system", "content": system}, *messages]

        openai = self._openai
        try:
            if max_tokens > _STREAM_THRESHOLD:
                # Streaming: una generazione da trentamila token può richiedere
                # minuti, e senza stream molti proxy chiudono la connessione prima.
                chunks = []
                stream = self._client.chat.completions.create(
                    model=model, messages=payload, max_tokens=max_tokens, stream=True
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    piece = chunk.choices[0].delta.content
                    if piece:
                        chunks.append(piece)
                return "".join(chunks)

            response = self._client.chat.completions.create(
                model=model, messages=payload, max_tokens=max_tokens
            )
            return response.choices[0].message.content or ""
        except openai.AuthenticationError:
            raise AIError("API key non valida. Controllala in Impostazioni → Account.", 400)
        except openai.PermissionDeniedError:
            raise AIError("La tua API key non ha accesso a questo modello.", 400)
        except openai.NotFoundError:
            raise AIError(
                f"Il modello '{model}' non esiste. Scegline uno dalla lista in "
                "Impostazioni → Modelli AI.",
                400,
            )
        except openai.RateLimitError:
            raise AIError(
                "Limite di frequenza raggiunto, oppure crediti esauriti sul fornitore.",
                429,
            )
        except openai.APIConnectionError:
            raise AIError("Impossibile contattare il fornitore del modello.")
        except openai.APIStatusError as exc:
            logger.warning("Errore API %s: %s", exc.status_code, exc.message)
            raise AIError(f"Errore dal fornitore ({exc.status_code}). Riprova.")


# ── Client ─────────────────────────────────────────────────────────────────────


def model_for(db: Session, user_id: int, role: str) -> str:
    """Il modello scelto dall'utente per quel ruolo, o il default dell'ambiente."""
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    chosen = getattr(prefs, f"ai_model_{role}", None) if prefs else None
    return (chosen or "").strip() or default_model(role)


class AIClient:
    """Client legato a un utente e a un ruolo: senza la sua API key non si costruisce."""

    def __init__(self, user: User, model: str):
        if not user.claude_api_key_enc:
            raise AIError(
                "API key non configurata. Inseriscila in Impostazioni → Account.", 400
            )
        self.model = model
        api_key = decrypt_api_key(user.claude_api_key_enc)
        self._backend = (
            _AnthropicBackend(api_key)
            if AI_PROVIDER == "anthropic"
            else _OpenAICompatibleBackend(api_key)
        )

    @property
    def supports_native_pdf(self) -> bool:
        return self._backend.supports_native_pdf

    def _complete(self, system, messages, max_tokens, thinking) -> str:
        text = self._backend.complete(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            thinking=thinking,
        )
        if not text.strip():
            raise AIError("Il modello ha restituito una risposta vuota. Riprova.")
        return text

    def generate_json(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 16000,
        thinking: bool = False,
    ) -> dict | list:
        """Chiede una risposta JSON e la restituisce già parsata.

        Se il modello sbaglia formato, ritenta ricordandogli il vincolo: costa una
        chiamata in più ma evita di far fallire una generazione da mezzo minuto.
        """
        messages = [{"role": "user", "content": prompt}]
        last_error = ""

        for attempt in range(AI_MAX_RETRIES):
            started = time.monotonic()
            text = self._complete(system, messages, max_tokens, thinking)
            elapsed = time.monotonic() - started
            try:
                data = _extract_json(text)
                logger.info(
                    "Generazione riuscita con %s (tentativo %s, %.1fs, %s caratteri)",
                    self.model,
                    attempt + 1,
                    elapsed,
                    len(text),
                )
                return data
            except ValueError as exc:
                last_error = str(exc)
                logger.warning(
                    "Risposta non parsabile da %s (tentativo %s/%s): %s",
                    self.model,
                    attempt + 1,
                    AI_MAX_RETRIES,
                    text[:200],
                )
                messages = [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text[:2000]},
                    {
                        "role": "user",
                        "content": (
                            "La risposta precedente non era JSON valido. Rispondi di nuovo "
                            "con SOLO il JSON richiesto: niente markdown, niente backtick, "
                            "niente testo prima o dopo."
                        ),
                    },
                ]

        raise AIError(
            f"Il modello '{self.model}' non ha restituito un JSON valido ({last_error}). "
            "Se succede spesso, prova un modello più capace da Impostazioni → Modelli AI."
        )

    def chat(self, system: str, messages: list[dict], *, max_tokens: int = 2000) -> str:
        """Conversazione multi-turno (chat per pasto). Risposta come testo libero."""
        return self._complete(system, messages, max_tokens, False)

    def parse_pdf(self, system: str, pdf_b64: str, prompt: str) -> dict | list:
        """Legge un PDF senza estrarne prima il testo. Solo backend Anthropic."""
        if not self.supports_native_pdf:
            raise AIError(
                "Il provider configurato non legge i PDF direttamente.", 400
            )
        text = self._backend.complete_with_pdf(
            model=self.model, system=system, pdf_b64=pdf_b64, prompt=prompt
        )
        try:
            return _extract_json(text)
        except ValueError:
            logger.warning("Parsing PDF: risposta non JSON: %s", text[:300])
            raise AIError(
                "Non sono riuscito a leggere la dieta dal PDF. "
                "Prova con un file più leggibile o inserisci i pasti a mano."
            )


def get_client(db: Session, user: User, role: str) -> AIClient:
    """Costruisce il client per un ruolo, col modello scelto dall'utente."""
    if role not in ROLES:
        raise ValueError(f"Ruolo AI sconosciuto: {role}")
    return AIClient(user, model_for(db, user.id, role))
