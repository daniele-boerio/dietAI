"""La dieta: qui solo HTTP (il file, il client, la proprietà), il resto in `services/diet.py`."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..rate_limit import AI_LIMIT, limiter
from ..schemas import DietFrequenciesUpdate, DietMealsUpdate, QuestionnaireRequest
from ..services import diet as diets
from ..services.ai_client import get_client
from ..services.planner import get_active_diet
from ..utils import frequencies as freq
from ..utils import nutrition

router = APIRouter(prefix="/api/diet", tags=["Dieta"])

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB: un piano alimentare non pesa di più


@router.post("/upload")
@limiter.limit(AI_LIMIT)
def upload_diet(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Carica il PDF della dieta e lo fa leggere al modello (`diets.read_pdf`).

    Il PDF non viene conservato: quello che serve è la struttura estratta (pasti e
    macro), e tenerne una copia significherebbe custodire un documento sanitario.
    """
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(400, "Serve un file PDF.")

    # `file.file` è il file temporaneo sottostante: si legge in modo sincrono,
    # come tutto il resto di questa rotta (che gira già in un thread).
    # Al massimo un byte oltre il limite: leggere tutto e poi misurare caricava in
    # memoria qualunque cosa arrivasse.
    content = file.file.read(MAX_PDF_BYTES + 1)
    if not content:
        raise HTTPException(400, "Il file è vuoto.")
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(400, "Il PDF è troppo grande (massimo 10 MB).")
    # Il tipo dichiarato lo scrive il client: conta quello che c'è dentro.
    if not content.startswith(b"%PDF-"):
        raise HTTPException(400, "Il file non è un PDF.")

    client = get_client(db, user, "diet")
    data = diets.read_pdf(client, content)
    diet = diets.create_from_pdf(db, user.id, file.filename, data)
    db.commit()
    return diets.serialize_diet(db, diet)


@router.post("/manual")
def create_diet_manually(
    body: DietMealsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea la dieta a mano, senza PDF (o quando il parsing non ha funzionato)."""
    diet = diets.create_manual(db, user.id, [m.model_dump() for m in body.meals])
    db.commit()
    return diets.serialize_diet(db, diet)


@router.get("/questionnaire/options")
def questionnaire_options(_user: User = Depends(get_current_user)):
    """Le scelte del questionario, con le loro spiegazioni.

    Le tiene il backend perché è lì che vengono usate per calcolare: due elenchi che
    si allontanano fra loro sono un 400 in faccia all'utente ("livello di attività non
    valido") per una parola cambiata da una parte sola.
    """
    return nutrition.options()


@router.post("/questionnaire/preview")
def preview_questionnaire(
    body: QuestionnaireRequest,
    _user: User = Depends(get_current_user),
):
    """Gli stessi numeri, senza salvare niente.

    Il questionario si fa in due tempi: prima i dati della persona, poi *quali* pasti
    si fanno e come si dividono le calorie. In mezzo servono i totali, e crearli come
    dieta per poi sostituirla al passo dopo vorrebbe dire archiviare una dieta mai
    vista da nessuno a ogni ripensamento.
    """
    return diets.compute(body)


@router.post("/questionnaire")
def create_diet_from_questionnaire(
    body: QuestionnaireRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Calcola la dieta dai dati della persona (`diets.create_from_questionnaire`)."""
    diet = diets.create_from_questionnaire(db, user.id, body)
    db.commit()
    return diets.serialize_diet(db, diet)


@router.get("/frequencies/options")
def frequency_options(_user: User = Depends(get_current_user)):
    """I gruppi di alimenti e le frequenze consigliate (linee guida CREA)."""
    return freq.options()


@router.put("/{diet_id}/frequencies")
def update_frequencies(
    diet_id: int,
    body: DietFrequenciesUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Le frequenze settimanali della dieta, scritte o corrette a mano."""
    diet = diets.own_diet(db, user.id, diet_id)
    diets.set_frequencies(diet, [f.model_dump() for f in body.frequencies])
    db.commit()
    return diets.serialize_diet(db, diet)


@router.get("/current")
def get_current_diet(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    diet = get_active_diet(db, user.id)
    if not diet:
        raise HTTPException(404, "Nessuna dieta attiva")
    return diets.serialize_diet(db, diet)


@router.put("/{diet_id}/meals")
def update_diet_meals(
    diet_id: int,
    body: DietMealsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Corregge a mano i pasti letti dal PDF (l'AI sbaglia, i PDF sono brutti)."""
    diet = diets.own_diet(db, user.id, diet_id)
    diets.correct_meals(db, diet, [m.model_dump() for m in body.meals])
    db.commit()
    return diets.serialize_diet(db, diet)
