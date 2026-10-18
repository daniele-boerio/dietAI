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

# Il server non gira come root: se qualcuno trovasse il modo di eseguire codice nel
# container, non avrebbe i permessi per riscriverlo. L'app non scrive su disco
# (PYTHONDONTWRITEBYTECODE, niente upload salvati), quindi /app può restare di root.
RUN useradd --system --uid 10001 dietai
USER dietai

# All'avvio: migrazioni, poi seed, poi il server.
#
# Il seed è idempotente (crea l'utente solo se manca, riallinea l'anagrafica
# ingredienti) e non deve poter impedire l'avvio: se SEED_USER_PASSWORD non è
# impostata esce con codice 1, e senza il `||` l'intero container non partirebbe.
# Farlo qui evita il caso peggiore: app deployata e nessun utente per entrarci.
#
# `app.serve` e non `uvicorn` dalla riga di comando: la rete di Coolify è dual-stack
# e il server deve ascoltare su IPv4 (il controllo di salute, 127.0.0.1) e su IPv6
# (nginx, che prova prima quello). `--host` ne accetta uno solo; il perché è in
# app/serve.py.
CMD ["sh", "-c", "alembic upgrade head && (python -m app.seed || echo 'Seed saltato: controlla SEED_USER_PASSWORD') && python -m app.serve"]
