"""Gli altri account, visti dall'amministratore.

L'app resta senza registrazione: nessuno si crea un account da sé, li crea chi ha la
chiave. Qui ci sono le quattro cose che servono davvero — farne uno, sospenderlo,
rimettergli la password, cancellarlo — e niente di più.

Perché una schermata invece di un comando nel container: la password si perde di
martedì sera, e per rimetterla non si apre un terminale su Coolify dal telefono.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth import get_current_admin, get_password_hash, revoke_all_sessions
from ..database import get_db
from ..models import DietPlan, User
from ..schemas import UserCreateRequest, UserFlagsUpdate, UserPasswordResetRequest
from ..services.accounts import create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Amministrazione"])


def _serialize(db: Session, user: User) -> dict:
    has_diet = (
        db.query(DietPlan)
        .filter(DietPlan.user_id == user.id, DietPlan.is_active.is_(True))
        .first()
        is not None
    )
    return {
        "id": user.id,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "ai_enabled": user.ai_enabled,
        "has_own_api_key": bool(user.claude_api_key_enc),
        "has_active_diet": has_diet,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _target(db: Session, user_id: int, admin: User) -> User:
    """L'utente su cui si sta agendo, con i due paletti che valgono per tutte le rotte.

    Un amministratore non si sospende, non si cancella e non si resetta da solo: sono
    tutti modi per restare chiusi fuori dalla propria app, e da lì si torna soltanto
    con `python -m app.reset_password` dal container.
    """
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Utente non trovato")
    if target.id == admin.id:
        raise HTTPException(400, "Su te stesso no: usa Impostazioni → Account.")
    if target.is_admin:
        raise HTTPException(400, "Non si tocca un altro amministratore da qui.")
    return target


@router.get("/users")
def list_users(
    admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.id).all()
    return [_serialize(db, u) for u in users]


@router.post("/users", status_code=201)
def add_user(
    body: UserCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Crea un account. La password iniziale la scegli tu e gliela dici a voce.

    Niente email di invito: l'app non manda posta, non ha SMTP e non ne vuole uno.
    """
    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, f"Esiste già un account con l'email {email}.")

    user = create_user(db, email, body.password)
    db.commit()
    logger.info("Utente %s creato dall'amministratore %s", email, admin.email)
    return _serialize(db, user)


@router.put("/users/{user_id}/flags")
def update_flags(
    user_id: int,
    body: UserFlagsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Sospende l'accesso o spegne le funzioni AI. I dati non si toccano mai."""
    target = _target(db, user_id, admin)

    if body.ai_enabled is not None:
        target.ai_enabled = body.ai_enabled
    if body.is_active is not None and body.is_active != target.is_active:
        target.is_active = body.is_active
        if not body.is_active:
            # Sospendere deve avere effetto adesso, non alla scadenza del token: si
            # alza token_version (invalida gli access token già emessi) e si revocano
            # le sessioni (invalida i refresh). Senza, l'utente resterebbe dentro
            # ancora mezz'ora e potrebbe rinnovare per novanta giorni.
            target.token_version += 1
            revoke_all_sessions(db, target.id)

    db.commit()
    return _serialize(db, target)


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    body: UserPasswordResetRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Rimette la password di un altro account: è l'unica via, non c'è recupero via mail."""
    target = _target(db, user_id, admin)

    target.password_hash = get_password_hash(body.new_password)
    target.token_version += 1
    revoke_all_sessions(db, target.id)
    db.commit()
    logger.info("Password di %s reimpostata dall'amministratore", target.email)
    return {"detail": f"Password di {target.email} aggiornata. Le sue sessioni sono chiuse."}


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Cancella l'account **e tutto ciò che contiene**: ricette, piani, spesa, dispensa.

    Le FK sono in CASCADE, quindi non resta niente e non si torna indietro. Se serve
    solo togliere l'accesso, sospendere è la mossa giusta.
    """
    target = _target(db, user_id, admin)
    email = target.email
    db.delete(target)
    db.commit()
    logger.warning("Utente %s cancellato con tutti i suoi dati", email)
    return Response(status_code=204)
