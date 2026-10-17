"""DietAI — Backend API.

Lo schema del database è gestito da Alembic (`alembic upgrade head`), non
dall'applicazione: all'avvio non si crea nessuna tabella.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .rate_limit import limiter
from .database import SessionLocal
from .routers import admin, auth, chat, diet, planning, push, recipes, shopping, tracking
from .routers import config as config_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DietAI API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Applica i default_limits del limiter a tutte le rotte (i limiti a mano restano in più).
app.add_middleware(SlowAPIMiddleware)

# Frontend e backend sono same-origin (nginx in prod, il proxy di Vite in dev), quindi
# i cookie di sessione non dipendono da questo. Niente allow_credentials: una pagina di
# terzi non deve poter chiamare l'API con i cookie dell'utente.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Le scritture partite da un altro sito si rifiutano. I cookie sono SameSite=Lax, che
# ferma le POST da domini estranei ma non da un sottodominio dello stesso dominio
# (qui `spassocasa.it` ospita anche altre app): `Sec-Fetch-Site` lo scrive il browser
# e non si può falsificare da una pagina. Chi non lo manda (curl, i test, browser
# vecchi) passa: resta la protezione di SameSite.
_SCRITTURE = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def _solo_dallo_stesso_sito(request: Request, call_next):
    sito = request.headers.get("sec-fetch-site")
    if request.method in _SCRITTURE and sito in ("cross-site", "same-site"):
        return JSONResponse({"detail": "Richiesta da un altro sito rifiutata"}, status_code=403)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(diet.router)
app.include_router(config_router.router)
app.include_router(planning.router)
app.include_router(recipes.router)
app.include_router(chat.router)
app.include_router(shopping.router)
app.include_router(tracking.router)
app.include_router(push.router)


# Il giro dei promemoria serali: un thread che controlla ogni minuto chi ha un
# promemoria arrivato all'ora (vedi `services/push.py`). Parte con l'app e muore con
# lei; i test lo spengono con DIETAI_SCHEDULER=0.
@app.on_event("startup")
def _avvia_promemoria() -> None:
    from .services.push import start_scheduler

    start_scheduler(SessionLocal)


# I log dell'app (`app.*`) a livello info, sull'output del container. Uvicorn configura
# solo i suoi logger: senza questo, per i moduli dell'app valeva il default di Python
# (solo avvisi ed errori), e un «pasto inviato a healthAI» o un «healthAI spento» non
# si vedevano mai — funzionante e spento sembravano la stessa cosa.
_log_app = logging.getLogger("app")
if not _log_app.handlers:
    _gestore = logging.StreamHandler()
    _gestore.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    _log_app.addHandler(_gestore)
    _log_app.setLevel(logging.INFO)


# Il giro di healthAI: ogni minuto porta i pasti consumati dell'amministratore al server
# dei suoi dati di salute (vedi `services/healthai.py`). Senza HEALTHAI_URL e
# HEALTHAI_TOKEN non parte; i test lo spengono come i promemoria.
@app.on_event("startup")
def _avvia_healthai() -> None:
    from .services.healthai import start_scheduler as start_healthai

    start_healthai(SessionLocal)


# Tutte le rotte sono `def`, non `async def`: il lavoro dell'app è sincrono e
# bloccante (SQLAlchemy, chiamate al modello che durano minuti), e su una rotta
# async bloccherebbe l'intero event loop. Così FastAPI le manda in un threadpool.
# La regola è senza eccezioni — la verifica tests/test_concurrency.py.
@app.get("/api/health", tags=["Servizio"])
def health():
    return {"status": "ok"}
