"""Login, sessione e gestione della API key di Claude.

Niente registrazione: l'app è per una persona sola e l'utente nasce dal comando di
seed. Quello che si protegge qui non è "un profilo", è la API key di Anthropic
salvata nel database.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..auth import (
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    consume_refresh_token,
    create_access_token,
    get_current_user,
    get_password_hash,
    issue_refresh_token,
    revoke_all_sessions,
    revoke_session,
    set_access_cookie,
    set_refresh_cookie,
    verify_password,
)
from ..crypto import encrypt_api_key
from ..database import get_db
from ..models import DietPlan, User, UserPreferences
from ..rate_limit import limiter
from ..schemas import ApiKeyRequest, ChangePasswordRequest, LoginRequest

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _serialize_user(db: Session, user: User) -> dict:
    """Il profilo che il frontend usa per decidere cosa mostrare (onboarding incluso).

    La API key non esce mai da qui: solo il fatto che ci sia o no.
    """
    has_diet = (
        db.query(DietPlan)
        .filter(DietPlan.user_id == user.id, DietPlan.is_active.is_(True))
        .first()
        is not None
    )
    return {
        "id": user.id,
        "email": user.email,
        "has_api_key": bool(user.claude_api_key_enc),
        "has_active_diet": has_diet,
    }


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    # Messaggio identico per email inesistente e password sbagliata: non diciamo a
    # un attaccante quale delle due ha indovinato.
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Credenziali non valide")

    access = create_access_token({"user_id": user.id, "token_version": user.token_version})
    refresh = issue_refresh_token(db, user.id, request.headers.get("user-agent"))
    db.commit()

    set_access_cookie(response, access)
    set_refresh_cookie(response, refresh)
    return _serialize_user(db, user)


@router.post("/refresh")
async def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Sessione assente")

    db_token = consume_refresh_token(db, raw)
    user = db.get(User, db_token.user_id)
    if not user:
        raise HTTPException(401, "Sessione non valida")

    access = create_access_token({"user_id": user.id, "token_version": user.token_version})
    new_refresh = issue_refresh_token(
        db, user.id, request.headers.get("user-agent"), family_id=db_token.family_id
    )
    db.commit()

    set_access_cookie(response, access)
    set_refresh_cookie(response, new_refresh)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
        revoke_session(db, raw)
        db.commit()
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize_user(db, user)


@router.put("/api-key")
async def set_api_key(
    body: ApiKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Salva la API key di Claude, cifrata."""
    key = body.api_key.strip()
    if not key.startswith("sk-ant-"):
        raise HTTPException(400, "La API key di Anthropic inizia con 'sk-ant-'.")

    user.claude_api_key_enc = encrypt_api_key(key)
    db.commit()
    return {"detail": "API key salvata"}


@router.delete("/api-key")
async def delete_api_key(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user.claude_api_key_enc = None
    db.commit()
    return {"detail": "API key rimossa"}


@router.post("/change-password")
async def change_password(
    response: Response,
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Password attuale non corretta")

    user.password_hash = get_password_hash(body.new_password)
    # Cambiare password deve buttare fuori ogni altra sessione: se la vecchia era
    # trapelata, chi ce l'aveva perde l'accesso subito e non alla scadenza del token.
    user.token_version += 1
    revoke_all_sessions(db, user.id)
    db.commit()

    clear_auth_cookies(response)
    return {"detail": "Password aggiornata: rifai il login"}


@router.get("/preferences-exist")
async def preferences_exist(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Usato dall'onboarding per sapere se le preferenze sono già state impostate."""
    exists = (
        db.query(UserPreferences).filter(UserPreferences.user_id == user.id).first() is not None
    )
    return {"exists": exists}
