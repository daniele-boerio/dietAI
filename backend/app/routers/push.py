"""Notifiche push: iscrizione del dispositivo, ora del promemoria, prova."""

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models import PushSubscription, UserPreferences
from ..schemas import PushSubscribeRequest, PushUnsubscribeRequest, ReminderUpdate
from ..services import push

router = APIRouter(prefix="/api/push", tags=["Notifiche"])

_ORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _state(db: Session, user_id: int) -> dict:
    prefs = db.query(UserPreferences).filter_by(user_id=user_id).first()
    return {
        "public_key": push.public_key(),
        "reminder_time": prefs.reminder_time if prefs else None,
        "devices": db.query(PushSubscription).filter_by(user_id=user_id).count(),
    }


@router.get("")
def get_push(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """La chiave pubblica per iscriversi, l'ora del promemoria e quanti dispositivi."""
    return _state(db, user_id)


@router.post("/subscribe")
def subscribe(
    body: PushSubscribeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    sub = db.query(PushSubscription).filter_by(endpoint=body.endpoint).first()
    if sub:
        # Lo stesso dispositivo con un altro account loggato: l'iscrizione lo segue.
        sub.user_id = user_id
        sub.p256dh = body.keys.p256dh
        sub.auth = body.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=user_id,
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
            )
        )
    db.commit()
    return _state(db, user_id)


@router.post("/unsubscribe")
def unsubscribe(
    body: PushUnsubscribeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    db.query(PushSubscription).filter_by(user_id=user_id, endpoint=body.endpoint).delete()
    db.commit()
    return _state(db, user_id)


@router.put("/reminder")
def set_reminder(
    body: ReminderUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """L'ora del promemoria serale («HH:MM», ora italiana), o null per spegnerlo."""
    if body.time is not None and not _ORA.match(body.time):
        raise HTTPException(400, "Ora non valida: scrivila come 21:00.")
    prefs = db.query(UserPreferences).filter_by(user_id=user_id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user_id, prefer_seasonal=True)
        db.add(prefs)
    prefs.reminder_time = body.time
    # Spostare l'ora a più tardi oggi deve poter far partire il promemoria di oggi.
    prefs.last_reminder_on = None
    db.commit()
    return _state(db, user_id)


@router.post("/test")
def test_notification(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
):
    """Una notifica di prova: è il modo di sapere che il telefono la riceve davvero."""
    consegnate = push.send(
        db,
        user_id,
        {
            "title": "DietAI",
            "body": "Le notifiche funzionano: il promemoria arriverà all'ora scelta.",
            "url": "/settings/preferences",
            "tag": "prova",
        },
    )
    if not consegnate:
        raise HTTPException(
            400,
            "Nessun dispositivo ha ricevuto la notifica: riattiva le notifiche da qui.",
        )
    return {"delivered": consegnate}
