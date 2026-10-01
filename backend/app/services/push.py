"""Notifiche push: il promemoria serale «com'è andata oggi?».

Il problema che risolve è un buco nei dati. Un giorno passato e mai segnato finisce
rosso nel grafico della settimana — per l'app non c'è modo di distinguerlo da un «no» —
e il motivo quasi sempre non è un giorno andato male, è un giorno in cui ci si è
dimenticati di aprire l'app. Una notifica all'ora scelta, solo se oggi c'è ancora
qualcosa da segnare, costa un tocco.

Tre pezzi:

- **Le chiavi VAPID** che firmano le notifiche. Se `VAPID_PRIVATE_KEY` non c'è si
  ricavano da `SECRET_KEY` (`_private_key`): niente da configurare su Coolify, e restano
  le stesse a ogni riavvio, che è l'unica cosa che conta — chiavi nuove renderebbero
  inutili tutte le iscrizioni dei telefoni.
- **Le iscrizioni** (`PushSubscription`): una per dispositivo. Quelle che il servizio
  di push dichiara morte (404/410) si cancellano al primo invio fallito.
- **Il giro dei promemoria** (`send_due_reminders`), che un thread chiama ogni minuto
  (`start_scheduler`). Non c'è uno scheduler esterno, come per le settimane archiviate:
  il backend gira in un processo solo (vedi il `CMD` del Dockerfile), e il thread vive
  con lui. Se il processo si riavvia nel minuto del promemoria lo si perde: è un
  promemoria, non una scadenza.
"""

import base64
import hashlib
import json
import logging
import os
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..config import SECRET_KEY
from ..models import DayPlan, MealSlot, PlannedMeal, PushSubscription, UserPreferences, WeekPlan

logger = logging.getLogger(__name__)

# L'ora del promemoria è quella dell'utente, e gli utenti sono in Italia. Il container
# gira in UTC: senza questa riga «21:00» arriverebbe alle 23.
FUSO = ZoneInfo("Europe/Rome")

_VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:dietai@localhost")

# L'ordine della curva P-256: la chiave privata è un intero in [1, n-1].
_P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _private_key():
    from cryptography.hazmat.primitives.asymmetric import ec

    raw = os.getenv("VAPID_PRIVATE_KEY")
    if raw:
        pad = "=" * (-len(raw) % 4)
        valore = int.from_bytes(base64.urlsafe_b64decode(raw + pad), "big")
    else:
        # Derivata, non generata: la stessa SECRET_KEY dà sempre la stessa chiave.
        seme = hashlib.sha256(b"dietai-vapid:" + SECRET_KEY.encode()).digest()
        valore = int.from_bytes(seme, "big") % (_P256_N - 1) + 1
    return ec.derive_private_key(valore, ec.SECP256R1())


def public_key() -> str:
    """La chiave pubblica in base64url, come la vuole `pushManager.subscribe`."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    punto = _private_key().public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return _b64url(punto)


def _vapid():
    from py_vapid import Vapid02

    return Vapid02(private_key=_private_key())


# ── Invio ──────────────────────────────────────────────────────────────────────


def send(db: Session, user_id: int, payload: dict) -> int:
    """Manda una notifica a tutti i dispositivi dell'utente. Restituisce quanti l'hanno
    ricevuta. Le iscrizioni morte si cancellano strada facendo."""
    from pywebpush import WebPushException, webpush

    consegnate = 0
    for sub in db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all():
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=_vapid(),
                vapid_claims={"sub": _VAPID_SUBJECT},
                ttl=3600,
            )
            consegnate += 1
        except WebPushException as exc:
            stato = getattr(exc.response, "status_code", None)
            if stato in (404, 410):
                # Il telefono ha revocato il permesso, o l'app è stata disinstallata.
                db.delete(sub)
            else:
                logger.warning("Notifica non consegnata (%s): %s", stato, exc)
        except Exception:  # noqa: BLE001 — una notifica non vale un'eccezione
            logger.warning("Notifica non consegnata", exc_info=True)
    db.commit()
    return consegnate


# ── Il promemoria ──────────────────────────────────────────────────────────────


def meals_to_answer(db: Session, user_id: int, giorno: date) -> int:
    """Quanti pasti di quel giorno aspettano ancora una risposta."""
    return (
        db.query(PlannedMeal)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .join(MealSlot, MealSlot.id == PlannedMeal.meal_slot_id)
        .filter(
            WeekPlan.user_id == user_id,
            DayPlan.date == giorno,
            DayPlan.is_skipped.is_(False),
            PlannedMeal.is_skipped.is_(False),
            PlannedMeal.is_followed.is_(None),
            # Una casella vuota non ha niente da segnare, a meno che quel pasto non
            # lo prepari l'utente: quello si segna come gli altri.
            (PlannedMeal.recipe_id.isnot(None)) | (MealSlot.auto_generate.is_(False)),
        )
        .count()
    )


def reminder_payload(quanti: int) -> dict:
    return {
        "title": "Com'è andata oggi?",
        "body": (
            "Hai un pasto da segnare: un tocco e hai finito."
            if quanti == 1
            else f"Hai {quanti} pasti da segnare: un tocco ciascuno e hai finito."
        ),
        "url": "/",
        "tag": "promemoria-serale",
    }


def send_due_reminders(db: Session, adesso: datetime | None = None) -> int:
    """Manda i promemoria arrivati all'ora. Restituisce a quanti utenti.

    Arrivato vuol dire: l'ora scelta è passata, oggi non è ancora partito, e c'è
    qualcosa da segnare. Chi ha già risposto a tutto non riceve niente — una notifica
    che non chiede niente insegna a ignorare le notifiche. Il segno `last_reminder_on`
    si mette anche quando non si manda, così il giro non ricontrolla ogni minuto fino a
    mezzanotte la stessa persona.
    """
    adesso = adesso or datetime.now(FUSO)
    oggi = adesso.date()
    ora = adesso.strftime("%H:%M")
    inviati = 0
    righe = (
        db.query(UserPreferences)
        .filter(UserPreferences.reminder_time.isnot(None))
        .all()
    )
    for prefs in righe:
        if prefs.reminder_time > ora or prefs.last_reminder_on == oggi:
            continue
        prefs.last_reminder_on = oggi
        db.commit()
        quanti = meals_to_answer(db, prefs.user_id, oggi)
        if quanti and send(db, prefs.user_id, reminder_payload(quanti)):
            inviati += 1
    return inviati


# ── Il thread ──────────────────────────────────────────────────────────────────

_avviato = False


def start_scheduler(session_factory, intervallo: float = 60.0) -> None:
    """Fa girare `send_due_reminders` ogni minuto, per tutta la vita del processo.

    Spento con `DIETAI_SCHEDULER=0` (lo fanno i test, che altrimenti avrebbero un
    thread che prova a parlare con un Postgres che non c'è).
    """
    global _avviato
    if _avviato or os.getenv("DIETAI_SCHEDULER", "1") == "0":
        return
    _avviato = True

    def giro():
        while True:
            try:
                db = session_factory()
                try:
                    send_due_reminders(db)
                finally:
                    db.close()
            except Exception:  # noqa: BLE001 — il giro dopo ci riprova
                logger.warning("Giro dei promemoria fallito", exc_info=True)
            time.sleep(intervallo)

    threading.Thread(target=giro, name="promemoria", daemon=True).start()
