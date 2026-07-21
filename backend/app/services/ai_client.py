"""Wrapper attorno all'SDK Anthropic: unico punto da cui si parla con Claude.

Tre cose che valgono per tutte le chiamate e che quindi stanno qui:

1. La API key è dell'utente e sta cifrata nel DB. Viene decifrata solo qui, il più
   tardi possibile, e non finisce mai in un log o in una risposta HTTP.
2. Le generazioni lunghe (il piano settimanale) vanno in streaming: con `max_tokens`
   alto una richiesta non-streaming sbatte contro il timeout HTTP dell'SDK.
3. I prompt chiedono JSON puro, ma un modello ogni tanto lo incarta nei backtick o ci
   scrive una frase davanti. `_extract_json` recupera quei casi, e su fallimento si
   ritenta: è molto più economico che far vedere un errore all'utente.
"""

import json
import logging
import re
import time

import anthropic
from fastapi import HTTPException

from ..config import AI_MAX_RETRIES, AI_MODEL_CHAT, AI_MODEL_PLANNING
from ..crypto import decrypt_api_key
from ..models import User

logger = logging.getLogger(__name__)

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

    # Scansione a contatore di parentesi: regex non basta, i JSON sono annidati.
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


class ClaudeClient:
    """Client legato a un utente: senza la sua API key non si costruisce."""

    def __init__(self, user: User):
        if not user.claude_api_key_enc:
            raise AIError(
                "API key di Claude non configurata. Inseriscila in Impostazioni → Account.",
                status_code=400,
            )
        self._client = anthropic.Anthropic(api_key=decrypt_api_key(user.claude_api_key_enc))

    # --- Chiamata di base ----------------------------------------------------

    def _create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        thinking: bool,
        effort: str | None,
    ) -> str:
        params: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if thinking:
            # Il piano settimanale è un problema di incastro (macro, ripetizioni,
            # avanzi): lasciare che il modello ragioni prima di scrivere paga.
            params["thinking"] = {"type": "adaptive"}
        if effort:
            params["output_config"] = {"effort": effort}

        try:
            if max_tokens > _STREAM_THRESHOLD:
                with self._client.messages.stream(**params) as stream:
                    message = stream.get_final_message()
            else:
                message = self._client.messages.create(**params)
        except anthropic.AuthenticationError:
            raise AIError(
                "API key di Claude non valida. Controllala in Impostazioni → Account.",
                status_code=400,
            )
        except anthropic.PermissionDeniedError:
            raise AIError("La tua API key non ha accesso a questo modello.", status_code=400)
        except anthropic.RateLimitError:
            raise AIError(
                "Anthropic ha applicato un limite di frequenza. Riprova tra qualche minuto.",
                status_code=429,
            )
        except anthropic.APIConnectionError:
            raise AIError("Impossibile contattare Anthropic. Controlla la connessione.")
        except anthropic.APIStatusError as exc:
            logger.warning("Errore API Anthropic %s: %s", exc.status_code, exc.message)
            raise AIError(f"Errore da Anthropic ({exc.status_code}). Riprova.")

        if message.stop_reason == "refusal":
            raise AIError("Claude ha rifiutato di rispondere a questa richiesta.")

        # Con il thinking attivo i primi blocchi sono di tipo "thinking": tiene solo
        # il testo, che è l'unica cosa che ci interessa.
        text = "".join(b.text for b in message.content if b.type == "text")
        if not text.strip():
            raise AIError("Claude ha restituito una risposta vuota. Riprova.")
        return text

    # --- API pubblica --------------------------------------------------------

    def generate_json(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 16000,
        thinking: bool = False,
        effort: str | None = None,
        model: str | None = None,
    ) -> dict | list:
        """Chiede una risposta JSON e la restituisce già parsata.

        Se il modello sbaglia formato, ritenta ricordandogli il vincolo: costa una
        chiamata in più ma evita di far fallire una generazione da 30 secondi.
        """
        messages = [{"role": "user", "content": prompt}]
        last_error = ""

        for attempt in range(AI_MAX_RETRIES):
            started = time.monotonic()
            text = self._create(
                model=model or AI_MODEL_PLANNING,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                thinking=thinking,
                effort=effort,
            )
            elapsed = time.monotonic() - started
            try:
                data = _extract_json(text)
                logger.info(
                    "Generazione AI riuscita (tentativo %s, %.1fs, %s caratteri)",
                    attempt + 1,
                    elapsed,
                    len(text),
                )
                return data
            except ValueError as exc:
                last_error = str(exc)
                logger.warning(
                    "Risposta AI non parsabile (tentativo %s/%s): %s",
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

        raise AIError(f"Claude non ha restituito un JSON valido ({last_error}).")

    def chat(self, system: str, messages: list[dict], *, max_tokens: int = 2000) -> str:
        """Conversazione multi-turno (chat per pasto). Risposta come testo libero."""
        return self._create(
            model=AI_MODEL_CHAT,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            thinking=False,
            effort=None,
        )

    def parse_pdf(self, system: str, pdf_b64: str, prompt: str) -> dict | list:
        """Manda un PDF a Claude e si fa restituire JSON strutturato.

        Il documento va PRIMA del testo nel blocco content: è l'ordine consigliato
        da Anthropic e in pratica dà letture più affidabili.
        """
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
        text = self._create(
            model=AI_MODEL_PLANNING,
            system=system,
            messages=[{"role": "user", "content": content}],
            max_tokens=8000,
            thinking=False,
            effort=None,
        )
        try:
            return _extract_json(text)
        except ValueError:
            logger.warning("Parsing PDF: risposta non JSON: %s", text[:300])
            raise AIError(
                "Non sono riuscito a leggere la dieta dal PDF. "
                "Prova con un file più leggibile o inserisci i pasti a mano."
            )
