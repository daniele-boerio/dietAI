"""Impianto dei test.

I test girano su SQLite in memoria: le tabelle nascono da `Base.metadata`, non dalle
migrazioni, e i modelli usano una variante JSON che su Postgres diventa JSONB (vedi
app/models.py). Serve a poter provare la logica — piano, spesa, blocco — senza un
database vero e senza chiamare Claude.
"""

import os
from datetime import date

import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("SECRET_KEY", "chiave-di-test-non-usata-in-produzione")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("COOKIE_SECURE", "false")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import get_password_hash  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.services import planner  # noqa: E402

# Ogni test fa login da "testclient": con il limite reale (10 al minuto) dall'undicesimo
# test in poi arriverebbe un 429 che non c'entra niente con quello che si sta provando.
limiter.enabled = False

TEST_EMAIL = "test@dietai.local"
TEST_PASSWORD = "password-di-test"


@pytest.fixture(autouse=True)
def oggi_e_lunedi(monkeypatch):
    """La suite gira come se fosse sempre lunedì.

    Da martedì in poi i giorni già passati vengono saltati e le ricette slittano: la
    settimana non avrebbe più sette giorni pieni e gli stessi test darebbero risultati
    diversi a seconda del giorno in cui li lanci. Chi lo slittamento lo prova davvero
    (`test_giorni_saltati.py`) sposta questa data per conto suo.
    """
    monkeypatch.setattr(planner, "today", lambda: planner.monday_of(date.today()))


@pytest.fixture()
def db():
    # StaticPool + una sola connessione: senza, ogni sessione aprirebbe un database
    # in memoria diverso e i test non vedrebbero i propri dati.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    """Client già autenticato: l'utente esiste e il login è fatto."""
    db.add(User(email=TEST_EMAIL, password_hash=get_password_hash(TEST_PASSWORD)))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        res = test_client.post(
            "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert res.status_code == 200, res.text
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def diet(client):
    """Una dieta a tre pasti, creata a mano (niente PDF, niente AI)."""
    res = client.post(
        "/api/diet/manual",
        json={
            "meals": [
                {"name": "Colazione", "order": 0, "calories": 400, "protein_g": 20,
                 "carbs_g": 50, "fat_g": 12},
                {"name": "Pranzo", "order": 1, "calories": 700, "protein_g": 40,
                 "carbs_g": 80, "fat_g": 20},
                {"name": "Cena", "order": 2, "calories": 600, "protein_g": 45,
                 "carbs_g": 50, "fat_g": 22},
            ]
        },
    )
    assert res.status_code == 200, res.text
    return res.json()
