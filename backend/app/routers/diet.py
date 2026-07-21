"""La dieta del nutrizionista: caricamento del PDF, lettura e correzione dei macro."""

import base64
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import DietPlan, MealSlot, User
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import DietMealsUpdate
from ..services import prompts
from ..services.ai_client import AIError, get_client
from ..services.pdf import extract_text, looks_scanned
from ..services.planner import get_active_diet, meal_slots_of

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diet", tags=["Dieta"])

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB: un piano alimentare non pesa di più


def _serialize_diet(db: Session, diet: DietPlan) -> dict:
    slots = meal_slots_of(db, diet.id)
    return {
        "id": diet.id,
        "filename": diet.filename,
        "total_daily_calories": diet.total_daily_calories,
        "notes": diet.notes,
        "created_at": diet.created_at.isoformat() if diet.created_at else None,
        "meals": [
            {
                "id": s.id,
                "name": s.name,
                "order": s.order_index,
                "calories": s.target_calories,
                "protein_g": s.target_protein_g,
                "carbs_g": s.target_carbs_g,
                "fat_g": s.target_fat_g,
                "notes": s.notes,
                "auto_generate": s.auto_generate,
            }
            for s in slots
        ],
    }


def _replace_meals(db: Session, diet: DietPlan, meals: list[dict]) -> None:
    """Riscrive i pasti della dieta.

    Cancellare e ricreare (invece di aggiornare) fa cascatare via i PlannedMeal che
    puntavano a pasti non più esistenti: la griglia settimanale si ricostruisce da
    sola alla lettura successiva.
    """
    db.query(MealSlot).filter(MealSlot.diet_plan_id == diet.id).delete()
    db.flush()

    for index, meal in enumerate(sorted(meals, key=lambda m: m.get("order", 0))):
        db.add(
            MealSlot(
                diet_plan_id=diet.id,
                name=(meal.get("name") or f"Pasto {index + 1}").strip()[:100],
                order_index=index,
                target_calories=int(meal.get("calories") or 0),
                target_protein_g=float(meal.get("protein_g") or 0),
                target_carbs_g=float(meal.get("carbs_g") or 0),
                target_fat_g=float(meal.get("fat_g") or 0),
                notes=(meal.get("notes") or None),
                auto_generate=bool(meal.get("auto_generate", True)),
            )
        )
    db.flush()


@router.post("/upload")
@limiter.limit(AI_LIMIT)
def upload_diet(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Carica il PDF della dieta e lo fa leggere al modello.

    Prima si prova a estrarre il testo (services/pdf.py): quasi tutte le diete sono
    PDF generati da un gestionale, l'estrazione è gratis e funziona con qualunque
    modello. Solo se il PDF è una scansione serve un modello che veda la pagina.

    Il PDF non viene conservato: quello che serve è la struttura estratta (pasti e
    macro), e tenerne una copia significherebbe custodire un documento sanitario.
    """
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(400, "Serve un file PDF.")

    # `file.file` è il file temporaneo sottostante: si legge in modo sincrono,
    # come tutto il resto di questa rotta (che gira già in un thread).
    content = file.file.read()
    if not content:
        raise HTTPException(400, "Il file è vuoto.")
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(400, "Il PDF è troppo grande (massimo 10 MB).")

    client = get_client(db, user, "diet")
    text = extract_text(content)

    if looks_scanned(text):
        if not client.supports_native_pdf:
            raise HTTPException(
                400,
                "Questo PDF sembra una scansione o una foto: non contiene testo da "
                "leggere, e il modello configurato non può guardarne le pagine. "
                "Inserisci i pasti a mano dalla schermata della dieta — sono pochi "
                "campi e li correggi una volta sola.",
            )
        logger.info("PDF senza testo: passo al modello il documento originale")
        data = client.parse_pdf(
            prompts.DIET_PARSE_SYSTEM,
            base64.standard_b64encode(content).decode(),
            prompts.DIET_PARSE_PROMPT,
        )
    else:
        logger.info("PDF con testo: %s caratteri estratti", len(text))
        data = client.generate_json(
            prompts.DIET_PARSE_SYSTEM,
            prompts.render(prompts.DIET_PARSE_TEXT_PROMPT, text=text[:120_000]),
            max_tokens=8000,
        )

    if not isinstance(data, dict) or not isinstance(data.get("meals"), list) or not data["meals"]:
        raise AIError("Nel PDF non ho trovato pasti riconoscibili. Inseriscili a mano.")

    meals = data["meals"]
    daily = int(data.get("daily_calories") or sum(int(m.get("calories") or 0) for m in meals))

    # Una sola dieta attiva: la precedente resta in archivio, disattivata.
    db.query(DietPlan).filter(
        DietPlan.user_id == user.id, DietPlan.is_active.is_(True)
    ).update({"is_active": False})

    diet = DietPlan(
        user_id=user.id,
        filename=file.filename,
        parsed_data=data,
        total_daily_calories=daily,
        notes=(data.get("notes") or None),
        is_active=True,
    )
    db.add(diet)
    db.flush()
    _replace_meals(db, diet, meals)
    db.commit()

    logger.info("Dieta caricata per utente %s: %s pasti, %s kcal", user.id, len(meals), daily)
    return _serialize_diet(db, diet)


@router.post("/manual")
def create_diet_manually(
    body: DietMealsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea la dieta a mano, senza PDF (o quando il parsing non ha funzionato)."""
    meals = [m.model_dump() for m in body.meals]

    db.query(DietPlan).filter(
        DietPlan.user_id == user.id, DietPlan.is_active.is_(True)
    ).update({"is_active": False})

    diet = DietPlan(
        user_id=user.id,
        filename=None,
        parsed_data={"meals": meals, "source": "manuale"},
        total_daily_calories=sum(m["calories"] for m in meals),
        is_active=True,
    )
    db.add(diet)
    db.flush()
    _replace_meals(db, diet, meals)
    db.commit()
    return _serialize_diet(db, diet)


@router.get("/current")
def get_current_diet(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    diet = get_active_diet(db, user.id)
    if not diet:
        raise HTTPException(404, "Nessuna dieta attiva")
    return _serialize_diet(db, diet)


@router.put("/{diet_id}/meals")
def update_diet_meals(
    diet_id: int,
    body: DietMealsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Corregge a mano i pasti letti dal PDF (l'AI sbaglia, i PDF sono brutti)."""
    diet = (
        db.query(DietPlan)
        .filter(DietPlan.id == diet_id, DietPlan.user_id == user.id)
        .first()
    )
    if not diet:
        raise HTTPException(404, "Dieta non trovata")

    meals = [m.model_dump() for m in body.meals]
    _replace_meals(db, diet, meals)
    diet.total_daily_calories = sum(m["calories"] for m in meals)
    db.commit()
    return _serialize_diet(db, diet)
