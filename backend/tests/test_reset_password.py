"""Il reset da riga di comando: unica via di rientro se la password si perde."""

import pytest

from app.auth import verify_password
from app.models import RefreshToken, User
from app.reset_password import reset_password
from tests.conftest import TEST_EMAIL, TEST_PASSWORD

NEW_PASSWORD = "nuova-password-lunga"


def test_reset_cambia_la_password(client, db):
    user = db.query(User).filter(User.email == TEST_EMAIL).one()

    reset_password(db, NEW_PASSWORD)

    db.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(TEST_PASSWORD, user.password_hash)


def test_reset_butta_fuori_le_sessioni_aperte(client, db):
    """Il login del fixture ha creato una sessione: dopo il reset non deve più valere."""
    assert client.get("/api/auth/me").status_code == 200

    user = db.query(User).filter(User.email == TEST_EMAIL).one()
    before = user.token_version

    reset_password(db, NEW_PASSWORD)

    db.refresh(user)
    assert user.token_version == before + 1
    assert all(
        t.revoked_at is not None
        for t in db.query(RefreshToken).filter(RefreshToken.user_id == user.id)
    )
    # Il cookie in mano al client è ora inutilizzabile, e il refresh non lo salva.
    assert client.get("/api/auth/me").status_code == 401

    # Con la nuova password si rientra.
    res = client.post(
        "/api/auth/login", json={"email": TEST_EMAIL, "password": NEW_PASSWORD}
    )
    assert res.status_code == 200


def test_password_troppo_corta_rifiutata(client, db):
    with pytest.raises(ValueError, match="almeno 8 caratteri"):
        reset_password(db, "corta")


def test_email_inesistente_rifiutata(client, db):
    with pytest.raises(ValueError, match="Nessun utente"):
        reset_password(db, NEW_PASSWORD, email="chi@boh.it")
