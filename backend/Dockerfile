# Python 3.12: ha wheel precompilate per tutte le dipendenze (niente toolchain di build)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Prima i requirements da soli, così la cache di Docker regge tra un deploy e l'altro
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

# All'avvio: migrazioni, poi seed, poi il server.
#
# Il seed è idempotente (crea l'utente solo se manca, riallinea l'anagrafica
# ingredienti) e non deve poter impedire l'avvio: se SEED_USER_PASSWORD non è
# impostata esce con codice 1, e senza il `||` l'intero container non partirebbe.
# Farlo qui evita il caso peggiore: app deployata e nessun utente per entrarci.
CMD ["sh", "-c", "alembic upgrade head && (python -m app.seed || echo 'Seed saltato: controlla SEED_USER_PASSWORD') && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
