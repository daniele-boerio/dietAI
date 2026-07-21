# DietAI

La dieta del nutrizionista diventa un piano settimanale di ricette vere e una lista
della spesa che si compila da sola.

Carichi il PDF della dieta, Claude ne estrae pasti e macro, e ogni settimana genera
ricette che stanno dentro quei numeri — italiane, di stagione, senza gli ingredienti
che hai escluso, pensate per non farti buttare mezza zucchina. Quando fai la spesa il
piano si blocca per sette giorni: il cibo è comprato, cambiare le ricette
significherebbe sprecarlo.

## Cosa fa

- **Legge la dieta dal PDF** e ne ricava pasti, calorie e macro (correggibili a mano).
- **Genera la settimana** in un'unica passata, così può distribuire gli avanzi tra i giorni.
- **Chat su ogni pasto**: "sostituisci il pollo", "rendilo più proteico", "come lo preparo
  la sera prima?" — e la ricetta si aggiorna davvero.
- **Lista della spesa automatica**: aggrega le quantità, converte le unità, toglie quello
  che hai in dispensa e quello che hai sempre in casa, raggruppa per reparto e stima il costo.
- **Blocco settimanale** dopo la spesa, con la settimana successiva già modificabile.
- **Pasti fissi** (la colazione di sempre, la pizza del sabato) che non vengono mai rigenerati.
- **Ricettario** con voti e preferiti: i voti rientrano nel contesto delle generazioni future.
- **Andamento**: pianificato vs prescritto, giorno per giorno.

## Requisiti

- Python 3.12 (su 3.13+ `pydantic-core` non ha wheel e prova a compilare da sorgente)
- Node 20+
- PostgreSQL 16 (in locale: `docker-compose.dev.yml`)
- Una API key di Anthropic — la inserisci nell'app, non nei file di configurazione

## Avvio in locale

```bash
# 1. Database
docker compose -f docker-compose.dev.yml up -d

# 2. Configurazione
cp .env.example backend/.env
#    poi genera i due segreti e mettili nel file:
#    python -c "import secrets; print(secrets.token_urlsafe(48))"                        → SECRET_KEY
#    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  → ENCRYPTION_KEY
#    imposta anche SEED_USER_EMAIL, SEED_USER_PASSWORD e COOKIE_SECURE=false

# 3. Backend
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# 4. Frontend (altro terminale)
cd frontend
npm install
npm run dev
```

Apri http://localhost:3000, entra con le credenziali del seed e segui l'onboarding:
API key → PDF della dieta → ingredienti di base ed esclusi → preferenze. Poi vai su
**Settimana** e premi *Genera*.

## Test

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q
```

Girano su SQLite in memoria con Claude sostituito da una risposta finta: verificano la
struttura della settimana, l'aggregazione della spesa, la dispensa, il blocco, i pasti
fissi e le conversioni di unità — senza spendere un centesimo di API.

## Deploy

`docker-compose.yml` è pensato per Coolify: due servizi (frontend con Nginx, backend
FastAPI) e un PostgreSQL come risorsa separata. Solo il frontend ha un dominio pubblico;
il backend è raggiungibile solo dalla rete Docker interna.

Variabili da impostare nelle Environment Variables: `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
`DB_PORT`, `DB_NAME`, `SECRET_KEY`, `ENCRYPTION_KEY`, `SEED_USER_EMAIL`,
`SEED_USER_PASSWORD`, `COOKIE_SECURE=true`.

Le migrazioni girano da sole all'avvio del container; il seed dell'utente va lanciato
una volta: `docker exec <container-backend> python -m app.seed`.

## Costi

Ogni generazione settimanale è una chiamata a Claude con tutte le ricette in un colpo
solo (indicativamente qualche decina di centesimi con Opus 4.8); rigenerare un singolo
pasto o scrivere in chat costa molto meno. Il modello si cambia con `AI_MODEL_PLANNING`
e `AI_MODEL_CHAT`. Gli endpoint AI hanno un limite di 20 chiamate al minuto per non
prosciugare la chiave in caso di loop.

## Sicurezza

- La API key di Claude è cifrata in database (Fernet) e decifrata solo al momento della
  chiamata: non compare mai in una risposta HTTP o in un log.
- I token di sessione stanno in cookie `httpOnly`, non in `localStorage`.
- Il refresh token ruota a ogni uso; il riuso di un token vecchio revoca tutta la catena.
- Il PDF della dieta non viene conservato: resta solo la struttura estratta.
