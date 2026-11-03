"""Chat contestuale su un pasto e sulla spesa: qui solo HTTP, il resto in `services/chat.py`."""

import json
import logging
import queue
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker

from ..auth import get_current_user
from ..database import get_db
from ..models import DayPlan, MealChatMessage, PlannedMeal, ShoppingChatMessage, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import ChatMessageRequest
from ..services import chat
from ..services.ai_client import get_client
from ..services.ownership import own_meal, own_week

router = APIRouter(prefix="/api/chat", tags=["Chat"])
logger = logging.getLogger(__name__)

# Il controllo di proprietà sta in `services/ownership.py`.
_get_meal = own_meal
_get_week = own_week


@router.get("/meals/{meal_id}/messages")
def get_history(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_meal(db, user.id, meal_id)
    rows = (
        db.query(MealChatMessage)
        .filter(MealChatMessage.planned_meal_id == meal_id)
        .order_by(MealChatMessage.id)
        .all()
    )
    return [chat.serialize_message(m) for m in rows]


@router.post("/meals/{meal_id}/messages")
@limiter.limit(AI_LIMIT)
def send_message(
    request: Request,
    meal_id: int,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manda un messaggio a DietAI a proposito di questo pasto (`chat.send_meal_message`)."""
    meal, day, _week = _get_meal(db, user.id, meal_id)
    client = get_client(db, user, "chat")
    return chat.send_meal_message(db, client, user, meal, day, body.content)


def _streamed(bind, work) -> StreamingResponse:
    """La risposta della chat a pezzi, una riga JSON per evento (NDJSON).

    `{"delta": "..."}` mentre il modello scrive la prosa, poi `{"done": <la stessa
    risposta della POST normale>}` oppure `{"error": "..."}`. Prima la pagina guardava
    i tre puntini per tutto il tempo della risposta (mezzo minuto, a volte di più);
    ora il testo compare mentre esce.

    Il lavoro gira in un thread con una sessione sua: quella della richiesta non è
    garantita viva mentre la risposta si sta ancora scrivendo. I controlli (pasto
    tuo, AI accesa, chiave presente) li ha già fatti la rotta, prima di cominciare:
    quegli errori restano risposte HTTP normali.
    """
    eventi: queue.Queue = queue.Queue()

    def corpo():
        session = sessionmaker(bind=bind)()
        try:
            result = work(session, lambda testo: eventi.put({"delta": testo}))
            eventi.put({"done": jsonable_encoder(result)})
        except HTTPException as exc:
            eventi.put({"error": exc.detail})
        except Exception:  # noqa: BLE001 — l'utente deve vedere che è finita
            logger.exception("Chat in streaming fallita")
            eventi.put({"error": "Qualcosa è andato storto, riprova."})
        finally:
            session.close()
            eventi.put(None)

    threading.Thread(target=corpo, name="chat-stream", daemon=True).start()

    def righe():
        while (evento := eventi.get()) is not None:
            yield json.dumps(evento, ensure_ascii=False) + "\n"

    # `X-Accel-Buffering: no`: senza, Nginx raccoglie tutta la risposta e la manda in
    # blocco alla fine — lo streaming ci sarebbe, ma nessuno lo vedrebbe.
    return StreamingResponse(
        righe(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/meals/{meal_id}/messages/stream")
@limiter.limit(AI_LIMIT)
def stream_message(
    request: Request,
    meal_id: int,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Come `send_message`, ma la risposta arriva mentre il modello la scrive."""
    meal, day, _week = _get_meal(db, user.id, meal_id)
    client = get_client(db, user, "chat")
    ids = (user.id, meal.id, day.id)

    def work(session, on_delta):
        return chat.send_meal_message(
            session, client, session.get(User, ids[0]), session.get(PlannedMeal, ids[1]),
            session.get(DayPlan, ids[2]), body.content, on_delta=on_delta,
        )

    return _streamed(db.get_bind(), work)


@router.delete("/meals/{meal_id}/messages", status_code=204)
def clear_history(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_meal(db, user.id, meal_id)
    db.query(MealChatMessage).filter(MealChatMessage.planned_meal_id == meal_id).delete()
    db.commit()


@router.get("/shopping/{week_id}/messages")
def get_shopping_history(
    week_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_week(db, user.id, week_id)
    rows = (
        db.query(ShoppingChatMessage)
        .filter(ShoppingChatMessage.week_plan_id == week_id)
        .order_by(ShoppingChatMessage.id)
        .all()
    )
    return [chat.serialize_message(m) for m in rows]


@router.post("/shopping/{week_id}/messages")
@limiter.limit(AI_LIMIT)
def send_shopping_message(
    request: Request,
    week_id: int,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat "da supermercato" (`chat.send_shopping_message`)."""
    week = _get_week(db, user.id, week_id)
    client = get_client(db, user, "chat")
    return chat.send_shopping_message(db, client, user, week, body.content)


@router.post("/shopping/{week_id}/messages/stream")
@limiter.limit(AI_LIMIT)
def stream_shopping_message(
    request: Request,
    week_id: int,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Come `send_shopping_message`, ma la risposta arriva mentre il modello la scrive."""
    week = _get_week(db, user.id, week_id)
    client = get_client(db, user, "chat")
    ids = (user.id, week.id)

    def work(session, on_delta):
        return chat.send_shopping_message(
            session, client, session.get(User, ids[0]), session.get(WeekPlan, ids[1]),
            body.content, on_delta=on_delta,
        )

    return _streamed(db.get_bind(), work)


@router.delete("/shopping/{week_id}/messages", status_code=204)
def clear_shopping_history(
    week_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_week(db, user.id, week_id)
    db.query(ShoppingChatMessage).filter(
        ShoppingChatMessage.week_plan_id == week_id
    ).delete()
    db.commit()
