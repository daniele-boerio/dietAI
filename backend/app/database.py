"""Engine, sessione e dipendenza FastAPI per il database."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

# pool_pre_ping: il Postgres può stare su un altro host, le connessioni inattive
# possono essere chiuse dalla rete. Senza, la prima query dopo una pausa esplode.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
