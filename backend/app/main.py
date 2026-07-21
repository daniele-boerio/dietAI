"""DietAI — Backend API.

Lo schema del database è gestito da Alembic (`alembic upgrade head`), non
dall'applicazione: all'avvio non si crea nessuna tabella.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .rate_limit import limiter
from .routers import auth, chat, diet, planning, recipes, shopping, tracking
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

app.include_router(auth.router)
app.include_router(diet.router)
app.include_router(config_router.router)
app.include_router(planning.router)
app.include_router(recipes.router)
app.include_router(chat.router)
app.include_router(shopping.router)
app.include_router(tracking.router)


@app.get("/api/health", tags=["Servizio"])
async def health():
    return {"status": "ok"}
