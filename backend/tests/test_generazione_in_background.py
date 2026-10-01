"""La generazione della settimana non vive dentro la richiesta HTTP.

La POST risponde subito 202 con la settimana «in generazione», e il lavoro prosegue in
un thread con una sessione sua. L'esito lo dice la settimana: è la stessa strada che il
frontend seguiva già, perché la risposta della POST arrivava di rado a destinazione.

La suite intera genera in primo piano (`generazione_in_primo_piano` in `conftest.py`):
qui si riaccende il background.
"""

import pytest

from app.models import WeekPlan
from app.services import planner
from tests.test_flow import FakeModel


@pytest.fixture()
def lavori(monkeypatch, client, diet):
    """Il thread non parte: il lavoro si mette da parte e lo si esegue quando serve.

    SQLite in memoria ha una connessione sola, e due thread che ci parlano insieme
    proverebbero il driver invece dell'app. Il thread vero lo prova il test in fondo.
    """
    monkeypatch.setattr(planner, "GENERATION_IN_BACKGROUND", True)
    monkeypatch.setattr(planner, "get_client", lambda db, user, role: FakeModel(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta-per-i-test"})

    in_coda = []
    monkeypatch.setattr(
        planner, "_in_background", lambda bind, name, work: in_coda.append((bind, work))
    )
    return in_coda


def esegui(in_coda):
    from sqlalchemy.orm import sessionmaker

    for bind, work in in_coda:
        session = sessionmaker(bind=bind)()
        try:
            work(session)
        except Exception:  # come `_in_background`: l'errore è già sulla settimana
            pass
        finally:
            session.close()
    in_coda.clear()


def test_la_post_risponde_subito_e_la_settimana_dice_che_sta_generando(client, lavori):
    week = client.get("/api/planning/weeks/current").json()

    res = client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert res.status_code == 202, res.text
    assert res.json()["is_generating"] is True
    assert res.json()["generation"]["status"] == "started"
    assert len(lavori) == 1


def test_finito_il_lavoro_la_settimana_e_piena(client, lavori, db):
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    esegui(lavori)
    db.expire_all()

    dopo = client.get("/api/planning/weeks/current").json()
    assert dopo["is_generating"] is False
    assert all(m["recipe"] for d in dopo["days"] for m in d["meals"])


def test_una_seconda_post_durante_la_generazione_e_rifiutata(client, lavori):
    """Due generazioni in parallelo sarebbero una spesa doppia: il segno sul database
    vale anche adesso che la prima non tiene più occupata la richiesta."""
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    assert client.post(f"/api/planning/weeks/{week['id']}/generate").status_code == 409


def test_un_fallimento_nel_thread_finisce_sulla_settimana(client, lavori, db, monkeypatch):
    class ModelloRotto(FakeModel):
        def generate_json(self, *a, **k):
            raise RuntimeError("provider giù")

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloRotto(user))
    week = client.get("/api/planning/weeks/current").json()
    client.post(f"/api/planning/weeks/{week['id']}/generate")

    esegui(lavori)
    db.expire_all()

    dopo = client.get("/api/planning/weeks/current").json()
    assert dopo["is_generating"] is False
    assert dopo["generation_error"]


def test_il_thread_vero_lavora_con_una_sessione_sua(tmp_path):
    """`_in_background` senza finzioni, su un database tutto suo."""
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{tmp_path / 'thread.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE segni (v TEXT)"))

    def lavoro(session):
        session.execute(text("INSERT INTO segni VALUES ('fatto')"))
        session.commit()

    planner._in_background(engine, "prova", lavoro).join(timeout=5)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT v FROM segni")).scalar() == "fatto"


def test_un_eccezione_nel_thread_vero_non_esce(tmp_path):
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'vuoto.db'}")

    def lavoro(session):
        raise RuntimeError("boom")

    thread = planner._in_background(engine, "prova", lavoro)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert WeekPlan  # il modulo resta importabile: nessun effetto collaterale
