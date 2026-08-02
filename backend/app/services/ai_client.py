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
    model_matches_provider,
)
from ..crypto import decrypt_api_key
from ..models import User, UserPreferences
from .accounts import admin_user

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


def _empty_response_error(model: str, max_tokens: int, finish_reason: str | None) -> AIError:
    """Diagnosi per una risposta senza testo.

    Il caso di gran lunga più comune non è un guasto: è un modello che ragiona molto,
    consuma tutto `max_tokens` in ragionamento (che conta come output) e non arriva a
    scrivere la risposta. Dirlo esplicitamente evita di far cercare un guasto che non
    c'è, e suggerisce l'unica cosa che serve davvero: cambiare modello.
    """
    if finish_reason == "length":
        return AIError(
            f"Il modello '{model}' ha esaurito i {max_tokens} token disponibili prima di "
            "scrivere la risposta: di solito succede con i modelli che ragionano molto. "
            "Prova un modello più diretto da Impostazioni → Modelli AI."
        )
    if finish_reason in ("content_filter", "error"):
        return AIError(f"Il modello '{model}' ha rifiutato di rispondere a questa richiesta.")
    return AIError(
        f"Il modello '{model}' ha restituito una risposta vuota"
        + (f" (motivo: {finish_reason})" if finish_reason else "")
        + ". Riprova, oppure cambia modello da Impostazioni → Modelli AI."
    )


def _reasoning_delta(delta) -> str:
    """Il pezzo di ragionamento dentro un chunk, se il modello lo lascia vedere.

    Non è nello schema OpenAI, quindi arriva fra i campi extra e il nome cambia da
    fornitore a fornitore: `reasoning` su OpenRouter, `reasoning_content` altrove. Chi
    il ragionamento lo tiene nascosto (le o-series) non manda niente, e va bene così:
    resta il testo della risposta, che mentre esce dice già a che punto siamo.
    """
    extra = getattr(delta, "model_extra", None) or {}
    for field in ("reasoning", "reasoning_content"):
        value = getattr(delta, field, None) or extra.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def _provider_message(exc) -> str:
    """Il messaggio dell'errore così come lo ha scritto il fornitore.

    OpenRouter lo mette in `body["error"]["message"]`; altri endpoint compatibili
    variano, quindi si ripiega sul messaggio dell'eccezione.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
    return getattr(exc, "message", None) or str(exc)


# ── Backend ────────────────────────────────────────────────────────────────────


class _AnthropicBackend:
    """SDK ufficiale Anthropic. L'unico che legge PDF nativamente."""

    supports_native_pdf = True

    def __init__(self, api_key: str):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=600)

    def complete(self, *, model, system, messages, max_tokens, thinking, on_progress=None) -> str:
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
                    if on_progress:
                        # Gli eventi si consumano uno a uno solo se serve guardarli:
                        # altrimenti basta aspettare il messaggio finale.
                        for event in stream:
                            if event.type != "content_block_delta":
                                continue
                            kind = getattr(event.delta, "type", "")
                            if kind == "thinking_delta":
                                on_progress("reasoning", event.delta.thinking)
                            elif kind == "text_delta":
                                on_progress("content", event.delta.text)
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
        text = "".join(b.text for b in message.content if b.type == "text")
        if not text.strip():
            # Stessa diagnosi dell'altro backend: "max_tokens" qui significa che il
            # budget è finito prima della risposta.
            raise _empty_response_error(
                model,
                max_tokens,
                "length" if message.stop_reason == "max_tokens" else message.stop_reason,
            )
        return text

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

    def complete(self, *, model, system, messages, max_tokens, thinking, on_progress=None) -> str:
        payload = [{"role": "system", "content": system}, *messages]

        # Sui modelli che ragionano (GLM, Hy3, o-series...) il ragionamento è ACCESO
        # di default e i suoi token si scalano da max_tokens: senza un freno un modello
        # brucia l'intero budget pensando e restituisce contenuto vuoto.
        #
        # Il freno però va chiesto in TOKEN, non in "effort", e questa è la lezione che
        # è costata una settimana di generazioni fallite. Su OpenRouter `effort: high`
        # riserva al ragionamento circa l'80% di max_tokens — e max_tokens qui è
        # dimensionato per il solo contenuto. Su una richiesta da 24.000 token per nove
        # ricette ne restavano ~4.800 per scriverle: non è andata male, non poteva
        # andare bene, e il conto non torna a nessuna scala (spezzare la settimana in
        # giorni lo riproduce identico, più piccolo). Con `max_tokens` il patto è
        # esplicito: pensa quanto vuoi fin qui, il resto serve per rispondere.
        #
        # Chi il parametro non lo supporta lo ignora, e chi accetta solo l'effort se lo
        # fa riconvertire da OpenRouter: si può mandare sempre.
        if thinking:
            extra_body = {"reasoning": {"max_tokens": max(1024, max_tokens // 4)}}
        else:
            extra_body = {"reasoning": {"effort": "low"}}

        openai = self._openai
        try:
            if max_tokens > _STREAM_THRESHOLD:
                # Streaming: una generazione da trentamila token può richiedere
                # minuti, e senza stream molti proxy chiudono la connessione prima.
                chunks = []
                finish_reason = None
                stream = self._client.chat.completions.create(
                    model=model,
                    messages=payload,
                    max_tokens=max_tokens,
                    stream=True,
                    extra_body=extra_body,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                    piece = choice.delta.content
                    if piece:
                        chunks.append(piece)
                    # I pezzi passano di qui comunque: darli a chi guarda costa una
                    # chiamata di funzione e trasforma minuti di schermata muta in
                    # qualcosa che si vede lavorare.
                    if on_progress:
                        thought = _reasoning_delta(choice.delta)
                        if thought:
                            on_progress("reasoning", thought)
                        if piece:
                            on_progress("content", piece)
                text = "".join(chunks)
            else:
                response = self._client.chat.completions.create(
                    model=model, messages=payload, max_tokens=max_tokens, extra_body=extra_body
                )
                choice = response.choices[0]
                text = choice.message.content or ""
                finish_reason = choice.finish_reason

            if not text.strip():
                raise _empty_response_error(model, max_tokens, finish_reason)
            return text
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
        except openai.BadRequestError as exc:
            # Sui 400 il messaggio del fornitore è quasi sempre preciso ("X is not a
            # valid model ID"): riportarlo vale molto più di un generico "errore 400",
            # che costringerebbe ad andare a leggere i log del server.
            raise AIError(
                f"Il fornitore ha rifiutato la richiesta per il modello '{model}': "
                f"{_provider_message(exc)}",
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
        except openai.APIError as exc:
            # Errore arrivato DENTRO lo stream, a intestazioni già mandate: OpenRouter
            # lo scrive come un evento nel corpo della risposta quando il fornitore a
            # valle si pianta, e l'SDK lo rilancia come APIError puro — che non è né uno
            # status error né un errore di connessione. Senza questo ramo usciva di qui
            # come eccezione non gestita, cioè come 500 con traceback al posto di un
            # messaggio leggibile, ed è il caso più probabile su una generazione lunga.
            logger.warning("Stream interrotto dal fornitore: %s", _provider_message(exc))
            raise AIError(
                f"Il fornitore ha interrotto la risposta del modello '{model}': "
                f"{_provider_message(exc)}"
            )


# ── Client ─────────────────────────────────────────────────────────────────────


def model_for(db: Session, user_id: int, role: str) -> str:
    """Il modello scelto dall'utente per quel ruolo, o il default dell'ambiente.

    Se la scelta salvata non ha la forma giusta per il provider attivo (capita
    cambiando provider dopo aver scelto i modelli) si ripiega sul default invece di
    andare a sbattere contro una 400.
    """
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    chosen = ((getattr(prefs, f"ai_model_{role}", None) if prefs else None) or "").strip()

    if chosen and not model_matches_provider(chosen):
        logger.warning(
            "Il modello salvato per %r (%r) non vale per il provider %r: uso il default.",
            role,
            chosen,
            AI_PROVIDER,
        )
        chosen = ""

    return chosen or default_model(role)


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

    def _complete(self, system, messages, max_tokens, thinking, on_progress=None) -> str:
        text = self._backend.complete(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            thinking=thinking,
            on_progress=on_progress,
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
        on_progress=None,
    ) -> dict | list:
        """Chiede una risposta JSON e la restituisce già parsata.

        Se il modello sbaglia formato, ritenta ricordandogli il vincolo: costa una
        chiamata in più ma evita di far fallire una generazione da mezzo minuto.

        `on_progress(kind, delta)` — se passata e se la chiamata va in streaming —
        riceve i pezzi man mano che escono, con `kind` fra "reasoning" e "content".
        """
        messages = [{"role": "user", "content": prompt}]
        last_error = ""

        for attempt in range(AI_MAX_RETRIES):
            started = time.monotonic()
            text = self._complete(system, messages, max_tokens, thinking, on_progress)
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


def ai_owner(db: Session, user: User) -> User:
    """Chi mette la chiave — e quindi sceglie i modelli — per le chiamate di `user`.

    L'amministratore paga per tutti: chi non lo è genera con la sua chiave e con i
    modelli che ha scelto lui. È la stessa decisione presa due volte, e a ragione —
    chi paga il conto decide il rapporto fra costo e qualità, e all'altro utente la
    schermata dei modelli non viene nemmeno mostrata.
    """
    if user.is_admin:
        return user
    return admin_user(db) or user


def get_client(db: Session, user: User, role: str) -> AIClient:
    """Costruisce il client per un ruolo, con la chiave e il modello di chi paga."""
    if role not in ROLES:
        raise ValueError(f"Ruolo AI sconosciuto: {role}")

    if not user.ai_enabled:
        raise AIError(
            "Le funzioni AI sono sospese su questo account. "
            "Il piano, la spesa e la dispensa restano come sono.",
            403,
        )

    owner = ai_owner(db, user)
    if not owner.claude_api_key_enc:
        # Due messaggi perché sono due problemi diversi: uno lo risolve chi legge,
        # l'altro no. Mandare l'ospite in "Impostazioni → Account" sarebbe crudele:
        # quella schermata, per lui, non esiste.
        raise AIError(
            "API key non configurata. Inseriscila in Impostazioni → Account."
            if owner.id == user.id
            else "L'amministratore non ha configurato nessuna API key: "
            "le funzioni AI sono spente.",
            400,
        )

    return AIClient(owner, model_for(db, owner.id, role))
