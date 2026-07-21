"""Rate limiting.

Serve soprattutto sugli endpoint che chiamano Claude: ogni chiamata costa soldi
veri sulla API key dell'utente, quindi un loop impazzito nel frontend (o una
scheda lasciata aperta a ricaricare) non deve poterla prosciugare. Su /auth/login
il limite è invece contro il brute force.

L'IP del client arriva corretto perché uvicorn gira con --proxy-headers dietro nginx.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# default_limits: rete di sicurezza su TUTTI gli endpoint (via SlowAPIMiddleware in
# main.py). I limiti stretti sulle rotte AI stanno a mano sui singoli endpoint.
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])

# Limite condiviso da tutte le rotte che chiamano Claude (spec: max 20/minuto).
AI_LIMIT = "20/minute"
