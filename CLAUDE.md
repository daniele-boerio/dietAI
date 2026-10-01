# DietAI — Dieta, ricette e lista della spesa

## Cos'è questo progetto

Webapp **a pochi account** (l'amministratore e chi invita lui) che prende la dieta —
il PDF del nutrizionista, oppure un questionario quando una dieta scritta non c'è — la
fa leggere a un modello linguistico e genera ogni settimana un piano di ricette che
rispetta i macro, con la lista della spesa già compilata. La lista dice sempre **quello che il piano chiede da oggi
in avanti e che in dispensa non c'è**: quando la spesa è fatta si svuota da sé (la
roba è passata in dispensa) e si riempie di nuovo appena generi altre ricette.

La spec originale (`.claude/DietAI_Technical_Spec.md`) è storica: dove non coincide
con questo file e con `docs/`, valgono questi.

## Stack

- **Backend:** Python 3.12 · FastAPI · PostgreSQL (SQLAlchemy + Alembic)
- **Frontend:** React 18 · Vite · React Router 6 · Lucide icons (JSX, nessun TypeScript)
- **Auth:** bcrypt · JWT (python-jose) · refresh token con rotazione · cookie httpOnly
- **AI:** provider a scelta — OpenRouter (default, API OpenAI-compatibile) o SDK
  Anthropic — con la **API key dell'utente**, cifrata in DB. Modello configurabile per ruolo
- **Infra:** Docker Compose · Nginx (reverse proxy) · Coolify

## Architettura

```
Traefik (Coolify) → Nginx (container frontend, :80)
                        ├─ /          → build React statica
                        └─ /api/*     → proxy_pass → backend:8000 (FastAPI)
                                                        ├─ PostgreSQL (risorsa Coolify separata)
                                                        └─ provider AI (OpenRouter o Anthropic, con la key dell'utente)
```

Frontend e backend sono **same-origin** (Nginx in prod, il proxy di Vite in dev): è ciò
che permette di tenere i token in cookie `httpOnly`, irraggiungibili da JavaScript.

Il PostgreSQL **non** è nel `docker-compose.yml`: è una risorsa Coolify a sé, e il
backend ci arriva tramite le `DB_*`. In locale c'è `docker-compose.dev.yml` col solo db.

## Struttura

```
├── docker-compose.yml          # Coolify (frontend + backend, NO db)
├── docker-compose.dev.yml      # solo Postgres, per lo sviluppo
├── docs/                       # il perché di ogni area (vedi "Dove sta il perché")
├── .claude/skills/, agents/    # procedure e revisore del progetto
├── backend/
│   ├── alembic/versions/       # migrazioni (l'URL viene da app.config)
│   ├── tests/                  # pytest su SQLite, modello mockato
│   └── app/
│       ├── main.py             # app FastAPI, CORS, include_router
│       ├── config.py           # env var + load_dotenv()
│       ├── database.py         # engine, SessionLocal, get_db
│       ├── models.py           # tutte le tabelle (17)
│       ├── schemas.py          # Pydantic (input; le risposte sono dict espliciti)
│       ├── auth.py             # hashing, JWT, cookie, get_current_user
│       ├── crypto.py           # Fernet per la API key del provider
│       ├── rate_limit.py       # slowapi (AI_LIMIT = 20/minuto)
│       ├── seed.py             # `python -m app.seed`: amministratore + anagrafica ingredienti
│       ├── reset_password.py   # `python -m app.reset_password '...'`: unica via di rientro
│       ├── make_admin.py       # `python -m app.make_admin`: rialza il flag di amministratore
│       ├── delete_user.py      # `python -m app.delete_user --email ...`: cancella un account
│       ├── merge_ingredients.py # `python -m app.merge_ingredients`: fonde i doppioni di anagrafica
│       ├── merge_recipes.py    # `python -m app.merge_recipes`: fonde le ricette identiche
│       ├── recompute_macros.py # `python -m app.recompute_macros`: ricalcola i macro dell'archivio
│       ├── routers/            # auth, admin, diet, config, planning, recipes, chat, shopping, tracking, push
│       ├── services/
│       │   ├── accounts.py     # chi è l'amministratore, creazione di un account
│       │   ├── ai_client.py    # due backend (openrouter/anthropic) dietro una interfaccia
│       │   ├── catalog.py      # catalogo modelli del provider (per il selettore)
│       │   ├── pdf.py          # estrazione testo dal PDF della dieta
│       │   ├── prompts.py      # TUTTI i prompt stanno qui
│       │   ├── planner.py      # settimane, generazione, ricorrenti, contesto
│       │   ├── recipes.py      # creazione/serializzazione ricette
│       │   ├── ingredients.py  # normalizzazione nomi, anagrafica
│       │   ├── shopping.py     # aggregazione lista, costo, spesa fatta
│       │   ├── macros.py       # macro calcolati dagli ingredienti, ritocco grammature
│       │   ├── push.py         # notifiche push e promemoria serale (thread ogni minuto)
│       │   ├── weight.py       # storico del peso, proposta di ricalcolo
│       │   ├── usage.py        # registro delle chiamate AI e conto per utente
│       │   └── tracking.py     # pianificato vs target
│       └── utils/
│           ├── units.py        # conversione unità (g/ml/unità)
│           ├── seasonality.py  # stagionalità prodotti italiani
│           ├── nutrition.py    # questionario → calorie e macro (Mifflin-St Jeor)
│           ├── pricing.py      # catalogo ingredienti: categoria + prezzo medio
│           ├── frequencies.py  # frequenze settimanali per gruppo: assegnazione e conto
│           └── composition.py  # composizione per 100 g degli alimenti del catalogo
└── frontend/src/
    ├── App.jsx                 # layout, routing, gate onboarding, AppContext (toast)
    ├── AuthContext.jsx         # useAuth(): user, login, logout, refreshUser
    ├── api.js                  # TUTTE le fetch + refresh automatico sul 401
    ├── index.css               # design system completo (variabili CSS, tema scuro/chiaro)
    ├── lib/macros.js           # ripartizione calorie/macro tra i pasti (+ test)
    ├── lib/generation.js       # cosa c'è da generare in settimana: la conta della dialog (+ test)
    ├── components/             # WeekGrid, WeekGenerateDialog, MealCard, DayDots, MealChat, RecipeView, MacroBar,
    │                           # Questionnaire (dieta calcolata, onboarding + /diet)...
    └── pages/                  # Dashboard, Planning, MealDetail, Shopping, Pantry,
                                # Recipes, Tracking, Diet, Settings, Altro (la quinta
                                # scheda del telefono), Onboarding, Login
```


## Dove sta il perché

Questo file tiene le **regole**, una riga ciascuna. La storia che le giustifica — cosa
si rompeva prima, quale test le guarda — sta in `docs/`, un file per area. Prima di
toccare una parte, leggi il suo documento: le regole qui sotto sono il riassunto, non
il ragionamento.

| Area | Documento |
|---|---|
| Account, amministratore, accesso | `docs/account.md` |
| Dieta: questionario, editor, lucchetto | `docs/dieta.md` |
| Piano: settimane, caselle, saltati, fissi, ricette condivise | `docs/piano.md` |
| Spesa, prezzi, reparti, dispensa | `docs/spesa.md` |
| Andamento e aderenza | `docs/andamento.md` |
| Generazione, modelli, ragionamento, stato | `docs/generazione.md` |
| Macro delle ricette: calcolo e ritocco | `docs/macro.md` |
| Chat e regole libere | `docs/chat.md` |
| Cucine del mondo e sorteggio | `docs/cucine.md` |
| Nomi degli ingredienti e catalogo | `docs/ingredienti.md` |
| Interfaccia e convenzioni visive | `docs/interfaccia.md` |

Le procedure (avviare, migrare, cambiare un prompt, rilasciare...) stanno nelle skill
di `.claude/skills/`; prima di un commit c'è l'agente `revisore-dietai`.

Quando una regola cambia, si aggiornano **tutte e due** le cose: la riga qui e il
paragrafo nel documento, scrivendo anche cosa non andava con la versione di prima.

## Regole in breve

**Account** (`docs/account.md`)
- La API key la mette solo l'amministratore (`User.is_admin`); gli altri generano con
  la sua chiave e i suoi modelli (`ai_owner`, `get_client`). Le rotte riservate
  rispondono 403 da sole: nascondere la scheda non è la difesa.
- `has_api_key` in `/me` dice con che chiave genererà quell'utente; l'onboarding pesa
  la chiave solo per chi la gestisce. I messaggi d'errore non mandano l'ospite in
  schermate che non ha.
- `is_active` toglie l'accesso subito (sessioni revocate, `token_version`);
  `ai_enabled` spegne solo l'AI. L'admin non si sospende, cancella o resetta da solo.
- Ogni chiamata al modello lascia una riga in `AIUsage` (token e costo, a chi ha premuto
  il pulsante): il client la scrive da sé se è stato costruito da `get_client`.
- Niente email: l'unico endpoint pubblico è `/auth/login`. Cancellare un utente porta
  via tutto (CASCADE); il seed ricrea solo l'amministratore.

**Dieta** (`docs/dieta.md`)
- Il questionario produce una `DietPlan` identica alle altre; il conto lo fa
  `utils/nutrition.py`, mai il modello, con i pavimenti (metabolismo basale, minimo per
  sesso). `/questionnaire/preview` calcola senza salvare.
- I pasti si dividono con l'aritmetica di `lib/macros.js` (resto sulla quota più
  grande): la somma è esattamente il totale.
- Col lucchetto chiuso il totale del giorno è invariante e le modifiche si
  ridistribuiscono, saltando i pasti «lo faccio io». Il riallineamento aspetta il blur.
- Le frequenze settimanali («pesce 2-3 volte») stanno su `DietPlan.frequencies`, gruppi
  di `utils/frequencies.FOODS`. Python assegna le proteine ai pasti principali prima di
  chiamare il modello (`freq.assign`) e conta dopo cosa c'è davvero
  (`frequency_report`). Una dieta nuova senza frequenze eredita quelle di prima.

**Piano** (`docs/piano.md`)
- La settimana esiste sempre: aprirla crea le caselle (in avanti). Una settimana
  passata che non c'è **non** si crea: si risponde vuota con `id: None`.
- Cambiare dieta sposta le caselle sul pasto omonimo (`realign_to_diet`), non le somma.
- «Ho mangiato altro» (`PlannedMeal.is_skipped`) conserva la ricetta come memoria e la
  accoda (`skipped_to_meal_id`); la casella saltata non conta più da nessuna parte.
  Non confonderlo con `DayPlan.is_skipped` né con il cestino (`clear_meal_cell`).
- «Lo faccio io» (`auto_generate=False`): mai generato, mai in spesa, ma i macro
  **contano**. I pasti fissi (`_is_fixed`) non si rigenerano; togliere il fisso svuota
  le copie future (`stop_recurring_forward`).
- Lo stesso piatto è una ricetta sola (`find_twin`); chi modifica da un pasto stacca
  prima una copia (`fork_recipe_for_meal`) e poi si riaccorpa (`settle_recipe`).

**Spesa e dispensa** (`docs/spesa.md`)
- La lista è una funzione: quello che le ricette da oggi a domenica otto
  (`shopping_horizon`) chiedono e la dispensa non ha. Chi tocca il piano chiama
  `rebuild_shopping_list(db, user_id)`.
- Il prezzo scritto a mano (`paid_price`) è un fatto e non si ricalcola; il prezzo al
  kg che se ne ricava vale per tutti. Reparto e prezzo corretti a mano sono protetti
  dal seed (`category_by_user`, `price_by_user`).
- «Ho fatto la spesa» sposta gli spuntati in dispensa; «l'ho seguito» scala la
  dispensa e scrive `pantry_used` (NULL, non `[]`, se non scala niente) e spiega gli
  scarti (`pantry_skipped`). Cambiare una ricetta non tocca la dispensa.
- Le scorte possono avere una scadenza (`PantryItem.expires_on`): nel contesto della
  generazione la dispensa va in ordine di scadenza, con la data per quello che scade
  entro una settimana.
- Il tetto di spesa settimanale (`weekly_budget_eur`) arriva al modello come cifra e il
  conto lo confronta col totale **scalato sui giorni che la lista copre**.
- La foto dello scontrino la legge il modello del ruolo `diet` e abbina lui le righe
  agli id degli articoli in lista; da lì è un prezzo scritto a mano come gli altri.

**Andamento** (`docs/andamento.md`)
- Un giorno senza pasti tracciati resta fuori dalle medie; nel grafico della settimana
  il colore è l'aderenza, non lo scarto dal target.
- Le pesate (`WeightEntry`, una per giorno) danno lo storico; oltre `max(2 kg, 3%)` dal
  peso del questionario si **propone** il ricalcolo dei target, mai lo si fa da soli, e
  mai per la dieta di un nutrizionista.
- «Ho mangiato altro: cosa?» si stima (`PlannedMeal.eaten_nutrition`) solo su un pasto
  segnato così; il «mangiato davvero» del giorno si dice solo se si sa di tutti i pasti.
- Il promemoria serale (push) parte all'ora italiana scelta, una volta al giorno e solo
  se oggi c'è qualcosa da segnare. Lo manda un thread del backend (`push.start_scheduler`,
  spento nei test); le chiavi VAPID si ricavano da `SECRET_KEY`.

**Generazione** (`docs/generazione.md`)
- Una chiamata sola per settimana (anti-spreco); di default riempie solo i buchi, e la
  selezione di giorni e pasti (`days`, `slot_ids`) filtra senza spezzarla. La conta in
  `lib/generation.js` deve dare lo stesso numero del server.
- Il ragionamento si chiede in token (un quarto di `max_tokens`), mai `effort: high`.
- Stato, diario ed errore della generazione stanno sul `WeekPlan`, non nella pagina:
  ciò che può fallire sta dentro il `try` e il fallimento si registra e si logga.
- La generazione della settimana gira in un thread con una sessione sua
  (`_in_background`): la POST risponde 202 e l'esito lo dice il polling. La suite la
  fa in primo piano (`generazione_in_primo_piano` in `conftest.py`).
- Il singolo pasto con `user_request`: comanda l'utente, tranne macro ed esclusi.

**Macro** (`docs/macro.md`)
- I macro di una ricetta si **calcolano** dalla composizione degli ingredienti
  (`services/macros.py`), non si prendono dal modello. Se un ingrediente non si sa
  contare restano quelli dichiarati e `Recipe.nutrition_source` lo dice.
- Fuori dal ±10% si ritoccano le grammature delle tre leve (proteine, carboidrati,
  grassi), mai le altre righe, mai oltre i limiti. Le ricette dell'utente non si toccano.
- La suite gira coi macro dichiarati (`macro_dichiarati` in `conftest.py`).

**Chat** (`docs/chat.md`)
- La ricetta va dopo il marcatore (`[RECIPE_UPDATE]`, `[RECIPES_UPDATE]`), il messaggio
  è solo prosa; `_needs_marker_retry` ritenta una volta.
- La chat della spesa riscrive tutte le ricette che usano l'ingrediente, solo sui
  `meal_id` che ha ricevuto.

**Cucine** (`docs/cucine.md`)
- Le cucine sono un catalogo chiuso con quote che sommano a 100 (`clean()`); il
  sorteggio per giorno lo fa Python (`draw`), non il modello.
- La base della spesa è italiana, i condimenti si chiamano col loro nome
  (`INGREDIENTI_LOCALI`); resta fuori solo il fresco introvabile.

**Ingredienti** (`docs/ingredienti.md`)
- Ogni nome passa da `normalize_name` (con `load_rules(db)` se c'è una sessione):
  via com'è messo, resta cos'è. Unire due alimenti diversi è un danno che si disfa a
  mano. Ogni voce del catalogo deve uscire identica dalla normalizzazione.

## Convenzioni

**Le rotte sono `def`, mai `async def`.** Il lavoro dell'app è sincrono e bloccante
(SQLAlchemy senza async, chiamate al modello che durano minuti): su una rotta `async`
girerebbe sull'event loop e congelerebbe l'intero server — durante una generazione
perfino `GET /api/auth/me` restava appeso. Con `def`, FastAPI le esegue in un
threadpool. La regola non ha eccezioni e `tests/test_concurrency.py` la fa rispettare.

- **Ogni query su dati personali va filtrata per `user_id`.** Gli account sono due e
  non devono vedersi: un endpoint che dimentica il filtro è un bug di sicurezza, non di
  stile. Per i pasti si passa da `_get_meal()`, che risale la catena pasto → giorno →
  settimana. Le rotte da amministratore passano da `get_current_admin`.
- **Lo schema lo gestisce Alembic**, non l'app: nessun `create_all` all'avvio. Cambiato
  un modello, serve `alembic revision --autogenerate -m "..."` e la migrazione va **riletta**.
- I modelli usano `JSONType` (`JSON` con variante `JSONB` su Postgres): serve a far
  girare i test su SQLite senza duplicare le tabelle.
- Le risposte dell'API sono **dict costruiti a mano** nei router/servizi: le entità sono
  aggregate (pasto + ricetta + ingredienti + target) e dieci schemi annidati sarebbero
  meno leggibili. Pydantic valida gli input.
- **Chi restituisce un'entità la restituisce sempre intera**, anche dalle rotte di
  modifica: il frontend ridisegna la pagina con la risposta del pulsante appena
  premuto, non ricarica. Una risposta più povera della GET rompe la schermata — è
  successo con `week`, che stava nel router invece che in `serialize_meal(full=True)`,
  e il primo clic su "L'ho seguito" spegneva il dettaglio del pasto. Guardia in
  `tests/test_dettaglio_pasto.py`.
- Tutte le chiamate del frontend passano da `api.js` — mai `fetch` nei componenti.
- **Testo UI in italiano.** Codice, commenti e nomi in inglese solo dove è già così.
- I prompt stanno tutti in `services/prompts.py`: i vincoli devono essere identici tra
  generazione, rigenerazione e chat, altrimenti l'AI si contraddice da una schermata all'altra.
- **I segnaposto dei prompt si riempiono con `prompts.render()`, mai con `str.format()`**:
  i prompt contengono esempi JSON, e per format() ogni graffa del JSON è un campo da
  sostituire (la chat è rimasta morta così, con un KeyError su `{
 "title"`).
  `tests/test_chat.py` ha una guardia che rende il template su tutti i prompt.

- **Interfaccia:** un solo `index.css` con custom properties; app scura; `--accent` si
  scrive e `--accent-fill` si riempie; ogni pulsante ha il bordo da 1px; chi chiama il
  modello usa il lime e `Sparkles`; il telefono è il caso normale (`dvh`, safe-area,
  niente solo-hover); nessuna pagina renderizza il vuoto (`LoadError`); indietro con
  `useGoBack`. Il dettaglio di tutto in `docs/interfaccia.md`.

## Sviluppo in locale

Serve Python **3.12** (su 3.13+ `pydantic-core` prova a compilare da sorgente Rust).
Il `.env` sta in `backend/.env` e lo carica `config.py` da solo.

```bash
# Database
docker compose -f docker-compose.dev.yml up -d

# Backend
cd backend && py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m alembic upgrade head        # crea lo schema
.venv/Scripts/python.exe -m app.seed                    # amministratore + ~180 ingredienti
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend (altro terminale)
cd frontend && npm install && npm run dev               # http://localhost:3000

# Test (SQLite in memoria, nessuna chiamata al modello, "oggi" fissato a lunedì)
cd backend && .venv/Scripts/python.exe -m pytest tests -q
```

Al primo login parte l'onboarding: API key del provider → dieta (PDF **o**
questionario) → ingredienti → preferenze. Senza API key le funzioni AI rispondono 400
con un messaggio esplicito. Per chi non è amministratore il primo passo non c'è: genera
con la chiave dell'admin, e il percorso comincia dalla dieta.

## Deploy (Coolify)

Push sul branch principale → Coolify ricostruisce via Docker Compose. Variabili da
impostare: `DB_*`, `SECRET_KEY`, `ENCRYPTION_KEY`, `SEED_USER_EMAIL`,
`SEED_USER_PASSWORD`, `COOKIE_SECURE=true`. Solo il frontend ha un dominio pubblico.

⚠️ `ENCRYPTION_KEY` non va più cambiata dopo il primo avvio: la API key salvata
diventerebbe indecifrabile e andrebbe reinserita.

## Operazioni frequenti

- **Nuovo endpoint:** rotta nel router giusto sotto `routers/`, funzione in `api.js`,
  chiamata dalla pagina.
- **Nuova pagina:** file in `pages/`, `<Route>` in `App.jsx`, voce nella sidebar.
- **Nuovo account:** Impostazioni → Utenti (solo amministratore). Da lì si sospende, si
  rimette la password e si spengono le funzioni AI. Cancellare porta via tutti i dati.
- **Cambiare il comportamento dell'AI:** `services/prompts.py`. Se cambia la forma del
  JSON atteso, aggiornare anche chi lo consuma (`planner.generate_week`, `recipes.create_recipe`).
- **Cambiare modello:** dalla UI (Impostazioni → Modelli AI, per ruolo) oppure
  `AI_MODEL_PLANNING` / `AI_MODEL_CHAT` / `AI_MODEL_DIET` per il default d'ambiente.
- **Cambiare provider:** `AI_PROVIDER` + `AI_BASE_URL`; la API key salvata va reinserita.
- **Aggiungere ingredienti al catalogo:** `utils/pricing.py` (categoria + prezzo), poi
  `python -m app.seed` per riallineare l'anagrafica.
- **Accorpare un nome nuovo** (un formato di pasta che il modello si è inventato, un
  taglio che non era in elenco): Impostazioni → Nomi e accorpamenti, che salva la
  regola e rifà l'anagrafica. Nel codice si scende solo per cambiare le regole di
  serie, che sono quelle su cui poggiano il catalogo dei prezzi e i test.
- **Ricettario pieno di doppioni** (archivio di prima che le ricette si condividessero):
  `python -m app.merge_recipes` per vedere cosa fonderebbe, `--yes` per fonderlo.
