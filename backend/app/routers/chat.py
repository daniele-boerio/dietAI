"""Chat contestuale su un pasto: si parla della ricetta e, se serve, la si modifica."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    DayPlan,
    MealChatMessage,
    MealSlot,
    PlannedMeal,
    Recipe,
    ShoppingChatMessage,
    User,
    WeekPlan,
)
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import ChatMessageRequest
from ..services import prompts
from ..services.ai_client import _extract_json, get_client
from ..services.planner import DAY_NAMES, build_context, meal_context_for_chat, week_meals
from ..services.recipes import ingredients_of, serialize_recipe, update_recipe_from_ai
from ..services.shopping import (
    get_or_create_list,
    rebuild_shopping_list,
    serialize_shopping_list,
    shopping_list_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# Marcatore concordato nel prompt: quello che segue è la ricetta aggiornata in JSON.
UPDATE_MARKER = "[RECIPE_UPDATE]"

# Come sopra, ma per la chat della spesa: quello che segue è una lista di ricette da
# aggiornare, ciascuna con il suo meal_id.
RECIPES_UPDATE_MARKER = "[RECIPES_UPDATE]"

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
    return [_serialize_message(m) for m in rows]


@router.post("/meals/{meal_id}/messages")
@limiter.limit(AI_LIMIT)
def send_message(
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

    # Un giorno saltato è passato senza spesa: come a piano bloccato, la chat può
    # commentare ma non riscrivere niente.
    frozen = week.is_locked or day.is_skipped
    if week.is_locked:
        lock_note = (
            "- IMPORTANTE: il piano di questa settimana è BLOCCATO (spesa già fatta). "
            "Non proporre modifiche alla ricetta: dai consigli su come cucinarla con quello "
            "che è già stato comprato."
        )
    elif day.is_skipped:
        lock_note = (
            "- IMPORTANTE: questo giorno è già passato senza che la spesa fosse fatta. "
            "Non proporre modifiche alla ricetta: non verrebbero applicate."
        )
    else:
        lock_note = (
            "- Il piano è modificabile: se l'utente chiede una modifica sensata, applicala."
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
        if frozen:
            visible += (
                "\n\n(Il piano è bloccato: la modifica non è stata applicata.)"
                if week.is_locked
                else "\n\n(Giorno già passato: la modifica non è stata applicata.)"
            )
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
def clear_history(
    meal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_meal(db, user.id, meal_id)
    db.query(MealChatMessage).filter(MealChatMessage.planned_meal_id == meal_id).delete()
    db.commit()


# ── Chat della spesa: cambia un ingrediente in tutte le ricette della settimana ─


def _get_week(db: Session, user_id: int, week_id: int) -> WeekPlan:
    week = (
        db.query(WeekPlan)
        .filter(WeekPlan.id == week_id, WeekPlan.user_id == user_id)
        .first()
    )
    if not week:
        raise HTTPException(404, "Settimana non trovata")
    return week


def _editable_meals(db: Session, week: WeekPlan) -> dict[int, tuple[PlannedMeal, DayPlan, MealSlot]]:
    """I pasti della settimana che la chat può toccare: quelli con una ricetta, non su
    un giorno saltato e non saltati a mano — cioè esattamente quelli che pesano sulla
    lista della spesa."""
    out = {}
    for day, meal, slot in week_meals(db, week):
        if meal.recipe_id and not day.is_skipped and not meal.is_skipped:
            out[meal.id] = (meal, day, slot)
    return out


def _week_index(db: Session, meals: dict[int, tuple[PlannedMeal, DayPlan, MealSlot]]) -> str:
    """Elenco compatto dei pasti per il prompt: id, giorno, target e ingredienti.

    Bastano i nomi degli ingredienti perché il modello capisca quali ricette toccare;
    le porzioni aiutano a rifare i conti dei macro dopo il cambio.
    """
    lines = []
    for meal_id, (meal, day, slot) in sorted(
        meals.items(), key=lambda kv: (kv[1][1].day_of_week, kv[1][2].order_index)
    ):
        recipe = db.get(Recipe, meal.recipe_id)
        ingredients = ", ".join(
            f"{i['name']} {i['quantity']:g} {i['unit']}" for i in ingredients_of(db, recipe.id)
        )
        lines.append(
            f"- meal_id {meal_id} · {DAY_NAMES[day.day_of_week]} / {slot.name} — "
            f"target {slot.target_calories} kcal (P {slot.target_protein_g:g} "
            f"C {slot.target_carbs_g:g} G {slot.target_fat_g:g}) — "
            f'"{recipe.title}" — ingredienti: {ingredients}'
        )
    return "\n".join(lines) if lines else "(nessuna ricetta in settimana)"


def _apply_recipes_update(
    db: Session,
    user: User,
    meals: dict[int, tuple[PlannedMeal, DayPlan, MealSlot]],
    data: dict,
) -> list[str]:
    """Applica le ricette aggiornate dalla chat. Ritorna le etichette dei pasti cambiati."""
    changed = []
    for entry in data.get("meals") or []:
        try:
            meal_id = int(entry.get("meal_id"))
        except (TypeError, ValueError):
            continue
        target = meals.get(meal_id)
        recipe_data = entry.get("recipe")
        if not target or not isinstance(recipe_data, dict):
            # Il modello ha citato un pasto che non è tra quelli modificabili (o l'ha
            # inventato): meglio ignorarlo che scrivere una ricetta a caso.
            continue
        meal, day, slot = target
        recipe = db.get(Recipe, meal.recipe_id)
        update_recipe_from_ai(db, recipe, recipe_data)
        meal.is_followed = None  # la ricetta è cambiata: il tracking riparte da zero
        changed.append(f"{DAY_NAMES[day.day_of_week]} / {slot.name}")
    return changed


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
    return [_serialize_message(m) for m in rows]


@router.post("/shopping/{week_id}/messages")
@limiter.limit(AI_LIMIT)
def send_shopping_message(
    request: Request,
    week_id: int,
    body: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chat "da supermercato": cambia un ingrediente in tutte le ricette che lo usano.

    Se la risposta contiene ricette aggiornate (marcatore [RECIPES_UPDATE]) vengono
    riscritte e la lista della spesa ricalcolata — ma solo se la spesa non è già stata
    fatta: a piano bloccato il cibo è comprato e la chat resta informativa.
    """
    week = _get_week(db, user.id, week_id)
    meals = _editable_meals(db, week)
    lst = get_or_create_list(db, week)

    lock_note = (
        "- IMPORTANTE: la spesa di questa settimana è già stata fatta e il piano è "
        "BLOCCATO. Non cambiare le ricette: il cibo è già comprato. Puoi solo dare "
        "consigli su come arrangiarsi con quello che c'è."
        if week.is_locked
        else "- Il piano è modificabile: applica pure i cambi richiesti."
    )

    system = prompts.render(
        prompts.SHOPPING_CHAT_SYSTEM,
        context=build_context(db, user.id),
        shopping_list=shopping_list_summary(db, lst),
        week_index=_week_index(db, meals),
        lock_note=lock_note,
    )

    history = (
        db.query(ShoppingChatMessage)
        .filter(ShoppingChatMessage.week_plan_id == week_id)
        .order_by(ShoppingChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    messages = [{"role": m.role, "content": m.content} for m in reversed(history)]
    messages.append({"role": "user", "content": body.content})

    db.add(ShoppingChatMessage(week_plan_id=week_id, role="user", content=body.content))
    db.flush()

    client = get_client(db, user, "chat")
    # Budget più largo della chat sul pasto: qui una risposta può contenere più ricette
    # complete in una volta.
    answer = client.chat(system, messages, max_tokens=16000)

    changed: list[str] = []
    visible = answer

    if RECIPES_UPDATE_MARKER in answer:
        head, _, tail = answer.partition(RECIPES_UPDATE_MARKER)
        visible = head.strip() or "Ho aggiornato le ricette."
        if week.is_locked:
            visible += "\n\n(La spesa è già fatta: le modifiche non sono state applicate.)"
        else:
            try:
                data = _extract_json(tail)
                if isinstance(data, dict):
                    changed = _apply_recipes_update(db, user, meals, data)
            except ValueError:
                logger.warning("Chat spesa: [RECIPES_UPDATE] senza JSON valido (settimana %s)", week_id)
                visible += "\n\n(Non sono riuscito ad applicare le modifiche, riprova.)"
            if not changed and RECIPES_UPDATE_MARKER in answer and "non sono riuscito" not in visible.lower():
                visible += "\n\n(Nessuna ricetta corrispondeva: non ho cambiato niente.)"

    db.add(ShoppingChatMessage(week_plan_id=week_id, role="assistant", content=visible))
    db.commit()

    if changed:
        rebuild_shopping_list(db, user.id, week)
        db.commit()

    return {
        "role": "assistant",
        "content": visible,
        "changed_meals": changed,
        "list_updated": bool(changed),
        "shopping_list": serialize_shopping_list(db, week, lst) if changed else None,
    }


@router.delete("/shopping/{week_id}/messages", status_code=204)
def clear_shopping_history(
    week_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    _get_week(db, user.id, week_id)
    db.query(ShoppingChatMessage).filter(
        ShoppingChatMessage.week_plan_id == week_id
    ).delete()
    db.commit()
