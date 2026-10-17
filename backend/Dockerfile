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
# `--host ::` e non 0.0.0.0: la rete di Coolify è dual-stack, `backend` risolve
# anche in IPv6 e nginx provava prima quello. Col solo IPv4 la connessione veniva
# rifiutata ("upstream server temporarily disabled") e nginx ripiegava sull'altro
# indirizzo. `::` ascolta su IPv6 e, su Linux, anche su IPv4.
CMD ["sh", "-c", "alembic upgrade head && (python -m app.seed || echo 'Seed saltato: controlla SEED_USER_PASSWORD') && uvicorn app.main:app --host :: --port 8000 --proxy-headers --forwarded-allow-ips=*"]
