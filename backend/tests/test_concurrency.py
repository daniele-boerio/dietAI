"""Le rotte non devono bloccare il server.

Il lavoro qui dentro è tutto sincrono e bloccante: SQLAlchemy senza async, e la
chiamata al modello che può durare minuti. Una rotta dichiarata `async def` gira
sull'event loop, quindi mentre genera una settimana **congela l'intera applicazione**:
anche un GET /api/auth/me resta appeso finché non ha finito. Dichiarata `def`, FastAPI
la esegue in un threadpool e il resto continua a rispondere.

È successo davvero, e si vede solo in produzione sotto carico: da qui la guardia.
"""

import inspect
import threading
import time

from fastapi.routing import APIRoute

from app.main import app


def test_nessuna_rotta_gira_sull_event_loop():
    coroutines = [
        f"{sorted(r.methods - {'HEAD', 'OPTIONS'})[0]} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/api")
        and inspect.iscoroutinefunction(r.endpoint)
    ]

    assert not coroutines, (
        "Queste rotte sono `async def` ma fanno lavoro bloccante: bloccherebbero "
        f"tutto il server mentre girano → {coroutines}"
    )


def test_una_rotta_lenta_non_blocca_le_altre(client, diet, monkeypatch):
    """Prova sul campo: mentre una generazione è in corso, /auth/me deve rispondere."""
    from app.services import planner
    from tests.test_flow import FakeModel

    class ModelloLento(FakeModel):
        def generate_json(self, system, prompt, **kwargs):
            time.sleep(1.5)  # sta al posto della chiamata vera al modello
            return super().generate_json(system, prompt, **kwargs)

    monkeypatch.setattr(planner, "get_client", lambda db, user, role: ModelloLento(user))
    client.put("/api/auth/api-key", json={"api_key": "sk-or-chiave-finta"})
    week = client.get("/api/planning/weeks/current").json()

    esito = {}

    def genera():
        esito["generate"] = client.post(
            f"/api/planning/weeks/{week['id']}/generate"
        ).status_code

    thread = threading.Thread(target=genera)
    thread.start()
    time.sleep(0.4)  # la generazione è partita ed è dentro la finta chiamata

    inizio = time.monotonic()
    res = client.get("/api/auth/me")
    durata = time.monotonic() - inizio

    thread.join(timeout=15)

    assert res.status_code == 200
    # Se le rotte girassero sull'event loop, questa attesa sarebbe ~1,1 s (il resto
    # della sleep) invece che immediata.
    assert durata < 0.5, f"/auth/me ha aspettato {durata:.2f}s: il server era bloccato"
    assert esito["generate"] == 200
