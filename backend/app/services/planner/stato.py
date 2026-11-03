"""Lo stato della generazione sul `WeekPlan`: in corso, diario, esito, errore, e chi se la aggiudica."""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...models import (
    WeekPlan,
)
from .settimane import _as_utc
from .. import planner  # per i nomi che i test sostituiscono: vedi __init__

logger = logging.getLogger(__name__)


GENERATION_TIMEOUT = timedelta(minutes=15)


def is_generating(week: WeekPlan) -> bool:
    started = _as_utc(week.generation_started_at)
    if started is None:
        return False
    return datetime.now(timezone.utc) - started < GENERATION_TIMEOUT


class GenerationProgress:
    """Il diario di bordo della generazione: cosa sta uscendo dal modello, adesso.

    Una generazione dura minuti e finora la pagina non poteva dire altro che "sto
    lavorando": nessun modo di distinguere un modello che sta ragionando da uno
    piantato, o di capire a che ricetta è arrivato. Ora i pezzi che passano già in
    streaming vengono raccolti qui e messi dove la pagina può leggerli.

    Passa dal database, come `generation_started_at` e per lo stesso motivo: chi
    guarda non è per forza chi ha premuto il pulsante, e la pagina si può ricaricare.
    Se ne tiene solo la coda — a nessuno serve rileggere trentamila caratteri, e la
    riga deve restare piccola perché la si riscrive ogni paio di secondi.

    Le scritture vanno su una sessione a parte, aperta e chiusa a ogni giro: quella
    della richiesta ha in mano la settimana a metà, e non può essere committata solo
    per far vedere due righe di testo. Se il diario non si scrive non succede niente
    di grave, quindi ogni errore qui viene ingoiato: sarebbe assurdo perdere una
    generazione pagata per un log.
    """

    REASONING_TAIL = 4000
    CONTENT_TAIL = 2000
    FLUSH_EVERY = 2.0  # secondi

    def __init__(self, week_id: int, expected_recipes: int = 0, session_factory=None):
        self.week_id = week_id
        self.expected_recipes = expected_recipes
        self._session_factory = session_factory
        # Un canale per chiamata: con la settimana in parallelo più chiamate scrivono
        # insieme, e mescolate in una lista sola il testo diventava una poltiglia e le
        # ricette si contavano a metà. Il canale 0 è quello di sempre (`__call__`).
        self._channels: list[dict] = [{"reasoning": [], "content": [], "counts": True}]
        self._lock = threading.Lock()
        self._last_flush = 0.0
        self._latest = 0

    def __call__(self, kind: str, delta: str) -> None:
        self._write(0, kind, delta)

    def channel(self, *, counts_recipes: bool = True):
        """Un nuovo canale per una chiamata che corre in parallelo alle altre.
        `counts_recipes=False` per il piano della settimana, che di titoli ne scrive
        ma ricette non ne produce."""
        with self._lock:
            self._channels.append({"reasoning": [], "content": [], "counts": counts_recipes})
            index = len(self._channels) - 1
        return lambda kind, delta: self._write(index, kind, delta)

    def _write(self, index: int, kind: str, delta: str) -> None:
        with self._lock:
            channel = self._channels[index]
            channel["reasoning" if kind == "reasoning" else "content"].append(delta)
            self._latest = index
            now = time.monotonic()
            if now - self._last_flush < self.FLUSH_EVERY:
                return
            self._last_flush = now
        self.flush()

    def snapshot(self) -> dict:
        with self._lock:
            testi = [
                ("".join(c["reasoning"]), "".join(c["content"]), c["counts"])
                for c in self._channels
            ]
            latest = self._latest
        reasoning, content, _ = testi[latest]
        return {
            # La coda di chi ha scritto per ultimo: è quello che si vede «muoversi».
            "reasoning": reasoning[-self.REASONING_TAIL :],
            "content": content[-self.CONTENT_TAIL :],
            "reasoning_chars": sum(len(r) for r, _, _ in testi),
            "content_chars": sum(len(c) for _, c, _ in testi),
            # Ogni ricetta comincia con la sua chiave "title": contarle è il modo più
            # economico di dire a che punto siamo senza parsare un JSON a metà.
            "recipes_written": sum(c.count('"title"') for _, c, conta in testi if conta),
            "expected_recipes": self.expected_recipes,
        }

    def flush(self) -> None:
        self._last_flush = time.monotonic()
        if not self._session_factory:
            return

        session = self._session_factory()
        try:
            session.query(WeekPlan).filter(WeekPlan.id == self.week_id).update(
                {WeekPlan.generation_progress: self.snapshot()},
                synchronize_session=False,
            )
            session.commit()
        except Exception:
            # A livello warning: in produzione (INFO) un diario fermo sembrava una
            # generazione bloccata, e il perché non compariva da nessuna parte.
            logger.warning("Diario della generazione non scritto", exc_info=True)
            session.rollback()
        finally:
            session.close()


def clear_generation_progress(db: Session, week: WeekPlan) -> None:
    """Cancella il diario nel database, non solo nell'oggetto in memoria.

    Il diario lo scrive un'altra sessione, quindi questa non sa che il valore sia mai
    cambiato: assegnare `None` all'attributo non produrrebbe nessuna UPDATE e la
    fotografia dell'ultima generazione resterebbe appesa alla settimana per sempre.
    """
    week.generation_progress = None
    db.query(WeekPlan).filter(WeekPlan.id == week.id).update(
        {WeekPlan.generation_progress: None}, synchronize_session=False
    )


def store_generation_outcome(db: Session, week: WeekPlan, outcome: dict) -> None:
    """Lascia sulla settimana il resoconto della generazione appena finita.

    In background il resoconto (`filled`, `missing`, `excluded`) lo restituiva
    `_apply_generated_week` a un thread che lo buttava via, e la pagina annunciava
    «Settimana pronta ✓» anche con cinque caselle vuote su nove. Sta nella colonna del
    diario come l'errore: a generazione ferma è libera.
    """
    week.generation_progress = {"result": outcome}
    db.query(WeekPlan).filter(WeekPlan.id == week.id).update(
        {WeekPlan.generation_progress: {"result": outcome}}, synchronize_session=False
    )


def generation_outcome(week: WeekPlan) -> dict | None:
    """Com'è andata l'ultima generazione riuscita: quante caselle, quante no e perché."""
    if is_generating(week):
        return None
    return (week.generation_progress or {}).get("result")


def generation_error(week: WeekPlan) -> str | None:
    """Perché l'ultima generazione non è arrivata in fondo, se è andata male.

    Sta nella stessa colonna del diario, che a generazione ferma è libera: sono due
    facce della stessa domanda ("cosa sta succedendo / cos'è successo") e tenerle
    separate avrebbe voluto dire una colonna in più per un dato che vive quanto l'altro.
    """
    if is_generating(week):
        return None
    return (week.generation_progress or {}).get("error")


def record_generation_failure(db: Session, week: WeekPlan, reason: str) -> None:
    """Scrive sulla settimana perché la generazione è fallita, e sblocca la settimana.

    Serve perché la risposta HTTP quasi mai arriva a destinazione: una generazione dura
    minuti e la richiesta muore molto prima, tagliata dal proxy che sta davanti (nginx
    a 300 s, e un proxy davanti può chiudere anche prima). Il messaggio d'errore finiva così in una risposta che
    nessuno leggeva, e da fuori restava solo una settimana vuota senza spiegazioni —
    mentre il frontend, che segue il polling e non la risposta, annunciava pure
    "Settimana pronta ✓". Il motivo resta scritto qui finché non si riprova.

    Il rollback prima di scrivere è deliberato: una generazione interrotta a metà non
    si salva (le ricette già create senza il resto del piano sarebbero peggio di
    niente), l'errore sì.
    """
    db.rollback()
    payload = {"error": reason, "failed_at": datetime.now(timezone.utc).isoformat()}
    week.generation_started_at = None
    week.generation_progress = payload
    # Come sopra: il diario lo scrive un'altra sessione, quindi la UPDATE va esplicita.
    db.query(WeekPlan).filter(WeekPlan.id == week.id).update(
        {WeekPlan.generation_started_at: None, WeekPlan.generation_progress: payload},
        synchronize_session=False,
    )
    db.commit()


def _failure_reason(exc: BaseException) -> str:
    """Il messaggio da mostrare all'utente per un'eccezione della generazione.

    Gli `AIError` sono già scritti per essere letti da lui (dicono anche cosa fare);
    per tutto il resto si tiene il tipo, che a quel punto è l'informazione utile.
    """
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return f"{type(exc).__name__}: {exc}".strip()


def ensure_not_generating(week: WeekPlan) -> None:
    """Una generazione alla volta per settimana.

    Non è pignoleria: ogni chiamata si paga, e senza questo controllo bastava
    ricaricare la pagina e ripremere il pulsante per farne partire una seconda.
    """
    if is_generating(week):
        raise HTTPException(
            409,
            "C'è già una generazione in corso per questa settimana: aspetta che finisca.",
        )


def claim_generation(db: Session, week: WeekPlan) -> None:
    """Segna la settimana "in generazione", ma solo se non lo è già: atomico.

    `ensure_not_generating` legge, e fra la lettura e questo punto passano il contesto
    e il prompt: un doppio clic (o due schede) passava il controllo due volte e si
    pagavano due generazioni sulla stessa settimana. La UPDATE condizionata la vince
    una sola richiesta; l'altra riceve 409 prima di chiamare il modello.
    """
    adesso = datetime.now(timezone.utc)
    presa = (
        db.query(WeekPlan)
        .filter(
            WeekPlan.id == week.id,
            or_(
                WeekPlan.generation_started_at.is_(None),
                WeekPlan.generation_started_at < adesso - GENERATION_TIMEOUT,
            ),
        )
        .update({"generation_started_at": adesso}, synchronize_session=False)
    )
    if not presa:
        db.rollback()
        raise HTTPException(
            409,
            "C'è già una generazione in corso per questa settimana: aspetta che finisca.",
        )
    week.generation_started_at = adesso
