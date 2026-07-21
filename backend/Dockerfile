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

# Le migrazioni girano all'avvio: il container si allinea da solo allo schema.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
