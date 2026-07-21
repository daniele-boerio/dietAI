"""Hashing, token, cookie e dipendenza di autenticazione.

L'app è single-user e non ha registrazione: l'utente nasce da `python -m app.seed`.
L'autenticazione serve comunque, ed è la parte più importante della sicurezza qui:
dietro il login c'è la API key Claude dell'utente, cioè soldi spendibili da chiunque
riesca a entrare.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    COOKIE_DOMAIN,
    COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from .database import get_db
from .models import RefreshToken, User

logger = logging.getLogger(__name__)

# Meglio morire all'avvio con un messaggio chiaro che firmare token con chiave vuota.
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY non configurata. Impostala nell'ambiente (o in backend/.env)."
    )

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"

# L'access token serve a tutte le /api/*; il refresh solo agli endpoint di sessione,
# così non viene nemmeno allegato alle altre chiamate.
ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/auth"


# --- Password ----------------------------------------------------------------


def get_password_hash(password: str) -> str:
    # bcrypt lavora su massimo 72 byte e da bcrypt 5 solleva se lo superi: tronchiamo
    # noi, come faceva passlib storicamente.
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8")
        )
    except ValueError:
        # hash malformato in DB: non è un match, ma non deve buttare giù la richiesta
        return False


# --- Access token (JWT) ------------------------------------------------------


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# --- Refresh token (opaco, in DB solo l'hash) --------------------------------


def _hash_refresh_token(raw_token: str) -> str:
    """SHA-256, non bcrypt: il token è già 256 bit di entropia casuale, quindi non è
    attaccabile a dizionario come una password e non serve un hash lento."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_refresh_token(
    db: Session,
    user_id: int,
    user_agent: str | None = None,
    family_id: str | None = None,
) -> str:
    """Crea il token e ne salva solo l'hash. Restituisce il valore in chiaro — unico
    momento in cui esiste — da mettere nel cookie httpOnly.

    `family_id` si passa in rotazione, per restare nella stessa catena.
    """
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash_refresh_token(raw_token),
            family_id=family_id or secrets.token_urlsafe(32),
            expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    return raw_token


def revoke_token_family(db: Session, user_id: int, family_id: str) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.family_id == family_id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc)})


def revoke_all_sessions(db: Session, user_id: int) -> None:
    """Revoca ogni sessione dell'utente. Va abbinata a un bump di token_version, così
    anche gli access token già emessi smettono subito di valere."""
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    ).update({"revoked_at": datetime.now(timezone.utc)})


def revoke_session(db: Session, raw_token: str) -> bool:
    """Revoca la sessione del dispositivo. Non solleva se il token è ignoto: un
    logout deve riuscire comunque."""
    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == _hash_refresh_token(raw_token))
        .first()
    )
    if not db_token:
        return False
    revoke_token_family(db, db_token.user_id, db_token.family_id)
    return True


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def consume_refresh_token(db: Session, raw_token: str) -> RefreshToken:
    """Valida un refresh token e lo marca come usato (rotazione).

    Se risulta già usato siamo davanti a un replay: qualcuno ha copiato il cookie.
    Non possiamo sapere se a presentarlo sia la vittima o l'attaccante, quindi
    revochiamo l'intera famiglia e obblighiamo entrambi a rifare il login.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessione non valida o scaduta"
    )

    db_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == _hash_refresh_token(raw_token))
        .first()
    )

    if not db_token or db_token.revoked_at is not None:
        raise invalid

    if db_token.used_at is not None:
        logger.warning(
            "Riuso di un refresh token già ruotato (user_id=%s, family=%s): "
            "revoco l'intera famiglia",
            db_token.user_id,
            db_token.family_id,
        )
        revoke_token_family(db, db_token.user_id, db_token.family_id)
        db.commit()
        raise invalid

    if _as_utc(db_token.expires_at) < datetime.now(timezone.utc):
        raise invalid

    db_token.used_at = datetime.now(timezone.utc)
    db.add(db_token)
    return db_token


# --- Cookie ------------------------------------------------------------------


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path=ACCESS_COOKIE_PATH,
        domain=COOKIE_DOMAIN,
    )


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        domain=COOKIE_DOMAIN,
    )


def clear_auth_cookies(response: Response) -> None:
    for name, path in (
        (ACCESS_COOKIE_NAME, ACCESS_COOKIE_PATH),
        (REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH),
    ):
        response.delete_cookie(
            key=name,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            path=path,
            domain=COOKIE_DOMAIN,
        )


# --- Dipendenza di autenticazione --------------------------------------------


def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> int:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Non autenticato"
    )

    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise credentials_exception

    user_id = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    # La token_version rende revocabile un token altrimenti stateless.
    user = db.get(User, user_id)
    if not user or user.token_version != payload.get("token_version", 1):
        raise credentials_exception

    return user_id


def get_current_user(
    user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)
) -> User:
    """Come get_current_user_id ma restituisce l'oggetto: serve dove ci vuole la
    API key cifrata (tutte le rotte AI)."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "Non autenticato")
    return user
