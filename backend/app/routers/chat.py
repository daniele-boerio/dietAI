"""Chat contestuale su un pasto e sulla spesa: qui solo HTTP, il resto in `services/chat.py`."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import MealChatMessage, ShoppingChatMessage, User
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import ChatMessageRequest
from ..services import chat
from ..services.ai_client import get_client
from ..services.ownership import own_meal, own_week

router = APIRouter(prefix="/api/chat", tags=["Chat"])

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


@router.delete("/shopping/{week_id}/messages", status_code=204)
def clear_shopping_history(
    week_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_week(db, user.id, week_id)
    db.query(ShoppingChatMessage).filter(
        ShoppingChatMessage.week_plan_id == week_id
    ).delete()
    db.commit()
