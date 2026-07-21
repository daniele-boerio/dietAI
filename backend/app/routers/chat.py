"""Chat contestuale su un pasto: si parla della ricetta e, se serve, la si modifica."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import DayPlan, MealChatMessage, PlannedMeal, User, WeekPlan
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import ChatMessageRequest
from ..services import prompts
from ..services.ai_client import _extract_json, get_client
from ..services.planner import DAY_NAMES, build_context, meal_context_for_chat
from ..services.recipes import serialize_recipe, update_recipe_from_ai
from ..services.shopping import rebuild_shopping_list

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Marcatore concordato nel prompt: quello che segue è la ricetta aggiornata in JSON.
UPDATE_MARKER = "[RECIPE_UPDATE]"

# Quanti messaggi passati rimandare al modello. Oltre non serve: la conversazione su
# un singolo pasto è corta, e ogni messaggio in più è contesto pagato a ogni turno.
HISTORY_LIMIT = 20


def _get_meal(db: Session, user_id: int, meal_id: int) -> tuple[PlannedMeal, DayPlan, WeekPlan]:
    row = (
        db.query(PlannedMeal, DayPlan, WeekPlan)
        .join(DayPlan, DayPlan.id == PlannedMeal.day_plan_id)
        .join(WeekPlan, WeekPlan.id == DayPlan.week_plan_id)
        .filter(PlannedMeal.id == meal_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Pasto non trovato")
    return row


def _serialize_message(message: MealChatMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.get("/meals/{meal_id}/messages")
async def get_history(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_meal(db, user.id, meal_id)
    rows = (
        db.query(MealChatMessage)
        .filter(MealChatMessage.planned_meal_id == meal_id)
        .order_by(MealChatMessage.id)
        .all()
    )
    return [_serialize_message(m) for m in rows]


@router.post("/meals/{meal_id}/messages")
@limiter.limit(AI_LIMIT)
async def send_message(
    request: Request,
    meal_id: int,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manda un messaggio a DietAI a proposito di questo pasto.

    Se la risposta contiene una ricetta aggiornata (marcatore [RECIPE_UPDATE]) la
    ricetta viene riscritta e la lista della spesa ricalcolata — ma solo se la
    settimana non è bloccata: a spesa fatta la chat resta informativa.
    """
    meal, day, week = _get_meal(db, user.id, meal_id)
    ctx = meal_context_for_chat(db, meal)
    slot = ctx["slot"]
    recipe = ctx["recipe"]

    lock_note = (
        "- IMPORTANTE: il piano di questa settimana è BLOCCATO (spesa già fatta). "
        "Non proporre modifiche alla ricetta: dai consigli su come cucinarla con quello "
        "che è già stato comprato."
        if week.is_locked
        else "- Il piano è modificabile: se l'utente chiede una modifica sensata, applicala."
    )

    system = prompts.render(
        prompts.MEAL_CHAT_SYSTEM,
        context=build_context(db, user.id),
        slot_name=slot.name,
        day_name=DAY_NAMES[day.day_of_week],
        target_calories=slot.target_calories,
        target_protein=f"{slot.target_protein_g:g}",
        target_carbs=f"{slot.target_carbs_g:g}",
        target_fat=f"{slot.target_fat_g:g}",
        current_recipe=ctx["recipe_json"],
        lock_note=lock_note,
    )

    history = (
        db.query(MealChatMessage)
        .filter(MealChatMessage.planned_meal_id == meal_id)
        .order_by(MealChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in reversed(history)]
    messages.append({"role": "user", "content": body.content})

    db.add(MealChatMessage(planned_meal_id=meal_id, role="user", content=body.content))
    db.flush()

    client = get_client(db, user, "chat")
    # Budget largo: sui modelli che ragionano una parte se ne va in ragionamento
    # prima ancora che comincino a scrivere.
    answer = client.chat(system, messages, max_tokens=8000)

    recipe_updated = False
    visible = answer

    if UPDATE_MARKER in answer:
        head, _, tail = answer.partition(UPDATE_MARKER)
        visible = head.strip() or "Ho aggiornato la ricetta."
        if week.is_locked:
            visible += "\n\n(Il piano è bloccato: la modifica non è stata applicata.)"
        elif not recipe:
            visible += "\n\n(Non c'è ancora una ricetta da aggiornare per questo pasto.)"
        else:
            try:
                data = _extract_json(tail)
                if isinstance(data, dict):
                    update_recipe_from_ai(db, recipe, data)
                    db.flush()
                    recipe_updated = True
            except ValueError:
                logger.warning("Chat: [RECIPE_UPDATE] senza JSON valido (pasto %s)", meal_id)
                visible += "\n\n(Non sono riuscito ad applicare la modifica, riprova.)"

    db.add(MealChatMessage(planned_meal_id=meal_id, role="assistant", content=visible))
    db.commit()

    if recipe_updated:
        rebuild_shopping_list(db, user.id, week)
        db.commit()

    return {
        "role": "assistant",
        "content": visible,
        "recipe_updated": recipe_updated,
        "recipe": serialize_recipe(db, recipe, full=True) if recipe_updated else None,
    }


@router.delete("/meals/{meal_id}/messages", status_code=204)
async def clear_history(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_meal(db, user.id, meal_id)
    db.query(MealChatMessage).filter(MealChatMessage.planned_meal_id == meal_id).delete()
    db.commit()
