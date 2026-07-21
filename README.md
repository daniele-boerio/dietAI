# DietAI

La dieta del nutrizionista diventa un piano settimanale di ricette vere e una lista
della spesa che si compila da sola.

Carichi il PDF della dieta, un modello ne estrae pasti e macro, e ogni settimana genera
ricette che stanno dentro quei numeri — italiane, di stagione, senza gli ingredienti
che hai escluso, pensate per non farti buttare mezza zucchina. Quando fai la spesa il
piano si blocca per sette giorni: il cibo è comprato, cambiare le ricette
significherebbe sprecarlo.

## Cosa fa

- **Legge la dieta dal PDF** e ne ricava pasti, calorie e macro (correggibili a mano).
- **Modello a scelta tua**: via OpenRouter puoi usare Claude, GLM, DeepSeek o altro, con
  un modello diverso per pianificazione, chat e lettura della dieta.
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
- Una API key di [OpenRouter](https://openrouter.ai/keys) — la inserisci nell'app, non nei file di configurazione

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

Girano su SQLite in memoria col modello sostituito da una risposta finta: verificano la
struttura della settimana, l'aggregazione della spesa, la dispensa, il blocco, i pasti
fissi e le conversioni di unità — senza spendere un centesimo di API.

## Deploy

`docker-compose.yml` è pensato per Coolify: due servizi (frontend con Nginx, backend
FastAPI) e un PostgreSQL come risorsa separata. Solo il frontend ha un dominio pubblico;
il backend è raggiungibile solo dalla rete Docker interna.

Variabili obbligatorie nelle Environment Variables: `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
`DB_PORT`, `DB_NAME`, `SECRET_KEY`, `ENCRYPTION_KEY`, `SEED_USER_EMAIL`,
`SEED_USER_PASSWORD`, `COOKIE_SECURE=true`. Facoltative (hanno un default nel compose):
`AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL_PLANNING`, `AI_MODEL_CHAT`, `AI_MODEL_DIET`,
`AI_MAX_RETRIES`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`.

All'avvio il container backend esegue migrazioni e seed da solo: entrambi sono
idempotenti, quindi ogni redeploy allinea lo schema e l'anagrafica ingredienti senza
toccare i dati. L'utente viene creato solo la prima volta — cambiare
`SEED_USER_PASSWORD` dopo non cambia la password (si usa *Impostazioni → Account*).

⚠️ `ENCRYPTION_KEY` non va più cambiata dopo il primo avvio: la API key del provider
salvata diventerebbe indecifrabile e andrebbe reinserita.

## Password dimenticata

Non c'è recupero via email: l'app non manda posta e non espone endpoint pubblici non
autenticati. La password si cambia da *Impostazioni → Account*, e se l'hai persa si
reimposta dal terminale del container (su Coolify: Terminal sul servizio backend):

```bash
python -m app.reset_password 'nuova-password-lunga'
```

Revoca anche tutte le sessioni aperte. **Non cancellare la riga dell'utente** per farla
ricreare dal seed: le foreign key sono in CASCADE e si porterebbero via dieta, ricette,
settimane e lista della spesa.

## Modelli e costi

Di default l'app parla con **OpenRouter**: una chiave sola dà accesso ai modelli di
tutti i fornitori — Claude, GLM, DeepSeek, Qwen, Gemini — e si sceglie quale usare
**per ogni ruolo** da *Impostazioni → Modelli AI*, pescandoli da una lista con prezzo
e finestra di contesto (niente slug da digitare a memoria).

I tre ruoli non hanno lo stesso peso, ed è lì che si risparmia davvero:

| Ruolo | Quando | Quanto conta il modello |
|---|---|---|
| Pianificazione settimanale | una volta a settimana | molto: incastrare i pasti nei macro è la parte difficile |
| Chat e modifiche | tante volte al giorno | poco: sono compiti brevi |
| Lettura della dieta | due o tre volte l'anno | irrilevante come costo |

Con Opus la generazione settimanale sta sui 0,60–0,90 €; un modello economico sulla
sola chat taglia la spesa quotidiana senza toccare la qualità del piano.

**Come capire se un modello economico regge:** genera una settimana e guarda la
percentuale di aderenza in *Andamento* — è la quota di pasti entro il ±10% dei macro.
È una misura oggettiva, non un'impressione.

Per usare l'SDK Anthropic diretto invece di OpenRouter: `AI_PROVIDER=anthropic` e una
chiave `sk-ant-`. È l'unico modo per far leggere al modello un PDF **scansionato**.

Gli endpoint AI hanno un limite di 20 chiamate al minuto per non prosciugare la chiave
in caso di loop.

## Sicurezza

- La API key del provider è cifrata in database (Fernet) e decifrata solo al momento della
  chiamata: non compare mai in una risposta HTTP o in un log.
- I token di sessione stanno in cookie `httpOnly`, non in `localStorage`.
- Il refresh token ruota a ogni uso; il riuso di un token vecchio revoca tutta la catena.
- Il PDF della dieta non viene conservato: resta solo la struttura estratta.
