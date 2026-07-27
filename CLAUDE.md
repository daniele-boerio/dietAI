# DietAI — Dieta, ricette e lista della spesa

## Cos'è questo progetto

Webapp **single-user** che prende la dieta del nutrizionista (PDF), la fa leggere a un
modello linguistico e genera ogni settimana un piano di ricette che rispetta i macro, con la lista
della spesa già compilata. La lista dice sempre **quello che il piano chiede da oggi
in avanti e che in dispensa non c'è**: quando la spesa è fatta si svuota da sé (la
roba è passata in dispensa) e si riempie di nuovo appena generi altre ricette.

Spec di riferimento: `.claude/DietAI_Technical_Spec.md`.

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
│       ├── seed.py             # `python -m app.seed`: utente + anagrafica ingredienti
│       ├── reset_password.py   # `python -m app.reset_password '...'`: unica via di rientro
│       ├── merge_ingredients.py # `python -m app.merge_ingredients`: fonde i doppioni di anagrafica
│       ├── routers/            # auth, diet, config, planning, recipes, chat, shopping, tracking
│       ├── services/
│       │   ├── ai_client.py    # due backend (openrouter/anthropic) dietro una interfaccia
│       │   ├── catalog.py      # catalogo modelli del provider (per il selettore)
│       │   ├── pdf.py          # estrazione testo dal PDF della dieta
│       │   ├── prompts.py      # TUTTI i prompt stanno qui
│       │   ├── planner.py      # settimane, generazione, ricorrenti, contesto
│       │   ├── recipes.py      # creazione/serializzazione ricette
│       │   ├── ingredients.py  # normalizzazione nomi, anagrafica
│       │   ├── shopping.py     # aggregazione lista, costo, spesa fatta
│       │   └── tracking.py     # pianificato vs target
│       └── utils/
│           ├── units.py        # conversione unità (g/ml/unità)
│           ├── seasonality.py  # stagionalità prodotti italiani
│           └── pricing.py      # catalogo ingredienti: categoria + prezzo medio
└── frontend/src/
    ├── App.jsx                 # layout, routing, gate onboarding, AppContext (toast)
    ├── AuthContext.jsx         # useAuth(): user, login, logout, refreshUser
    ├── api.js                  # TUTTE le fetch + refresh automatico sul 401
    ├── index.css               # design system completo (variabili CSS, tema chiaro/scuro)
    ├── lib/macros.js           # ripartizione calorie/macro tra i pasti (+ test)
    ├── components/             # WeekGrid, MealCard, MealChat, RecipeView, MacroBar...
    └── pages/                  # Dashboard, Planning, MealDetail, Shopping, Pantry,
                                # Recipes, Tracking, Diet, Settings, Onboarding, Login
```

## Concetti da avere in testa

**La settimana esiste sempre.** `GET /api/planning/weeks/current` crea al volo
`WeekPlan` + 7 `DayPlan` + una `PlannedMeal` per ogni incrocio giorno × pasto, anche
vuota. Generare vuol dire riempire le caselle libere. Se la dieta cambia,
`ensure_week_structure` riallinea le settimane esistenti.

**Il piano si sfoglia, e il passato è di sola lettura.** Non ci sono più due schede
fisse (questa settimana / la prossima): `GET /api/planning/weeks/by-date/{data}`
apre qualunque lunedì e `/plan/:weekStart` è la pagina, con `/plan` e `/plan/next`
lasciati validi perché sono linkati in giro. Avanti vale la regola di sopra —
la settimana nasce appena la si apre, e quanto pianificare lo decide l'utente, come
per la spesa. Indietro no: una settimana passata che non c'è **non** viene creata
adesso (arriverebbe con i pasti fissi ricopiati in giorni già passati, e l'archivio
si riempirebbe di settimane mai vissute), quindi l'endpoint risponde con una
settimana vuota, `id` a `None` e la stessa forma delle altre. `is_past` dice
soltanto dove ci si trova mentre si sfoglia: una settimana archiviata si modifica come
tutte le altre, e quello che ci cambi non tocca la spesa — che guarda da oggi in
avanti.

**La lista della spesa è una funzione, non un documento.** Dice sempre la stessa cosa
— *quello che le ricette da oggi in avanti chiedono e che in dispensa non c'è* — e da
quella frase discende tutto il resto senza regole aggiuntive: "ho fatto la spesa"
sposta gli articoli spuntati in dispensa e la lista si svuota da sé; una ricetta nuova
aggiunge quello che le serve, perché in dispensa non c'è; quello che non hai spuntato
resta, perché non l'hai comprato.

`meals_to_buy` è il cuore: pasti con una ricetta, da oggi in avanti, non su un giorno
saltato, non saltati e **non già segnati come seguiti** — quel piatto è stato
cucinato, ricomprarlo sarebbe comprarlo due volte. Nessun tetto in avanti: se hai
generato tre settimane la spesa le comprende tutte, ed è l'anti-spreco portato oltre
il lunedì (una confezione sola invece di due mezze). Di liste ce n'è una sola
(`current_list`, agganciata alla settimana corrente solo perché la riga deve stare da
qualche parte) e non si chiude mai: `completed_at` dice quand'è stato l'ultimo giro.
Chi tocca il piano chiama `rebuild_shopping_list(db, user_id)` — la dashboard legge la
lista senza ricostruirla.

**I prezzi veri battono il catalogo.** `utils/pricing.py` porta medie nazionali: nel
negozio dove l'utente fa la spesa valgono poco, ed è per questo che un totale stimato
non dice quasi niente. `PUT /api/shopping/items/{id}/price` chiede la cifra che si ha
sotto gli occhi — quanto è costato *quel* pacco — e `unit_price_from` (l'inverso di
`price_for`) ne ricava il prezzo al kg/l/unità, che finisce su `Ingredient` e da lì in
poi vale per tutte le liste. Come per il reparto serve un flag (`price_by_user`) che
protegga il numero dal seed, che gira a ogni avvio del container. Il prezzo si segna
anche a spesa fatta — lo scontrino si guarda a casa — e la lista espone `priced_items`
perché il totale possa dire su cosa si regge invece di spacciarsi per un preventivo.

**Il reparto di un ingrediente lo decide chi fa la spesa.** `Ingredient.category`
serve a girare il supermercato una volta sola, e il catalogo non può sapere che gli
il seitan sta con la carne (`guess_category` non lo riconosce e finisce in
"altro"). `PUT /api/config/ingredients/{id}/category` li sposta per tutte le liste,
presenti e future, e alza `category_by_user`: senza quel flag il seed — che gira **a
ogni avvio del container** e riallinea l'anagrafica al catalogo — se la riprenderebbe
al primo deploy. Il raggruppamento avviene alla lettura (`serialize_shopping_list`),
quindi non serve ricostruire niente.

**"Ho fatto la spesa" non blocca niente: riempie la dispensa.**
`POST /api/shopping/current/complete` prende gli articoli **spuntati** (senza nemmeno
uno risponde 400: confermare a vuoto svuoterebbe la lista senza mettere niente in
casa), li mette in dispensa nella quantità presa davvero e rifà la lista, che si
accorcia da sé perché adesso la dispensa copre il piano.

Il piano resta modificabile sempre: passato, presente e futuro, spesa fatta o no. Se
cambi una ricetta già comprata l'app **non tocca la dispensa** — quello che è in casa
resta in casa, e la scorta la corregge chi apre il frigo. È una scelta esplicita:
indovinare cosa è rimasto sarebbe peggio che lasciar fare all'utente.
`refresh_week_statuses` archivia le settimane passate a ogni lettura, senza scheduler,
ma "archiviata" è un'etichetta, non un lucchetto.

**Il piano segue il calendario, la spesa segue il piano.** I giorni che passano non si
saltano da soli e le ricette non slittano: quello che era di lunedì resta di lunedì. A
dire cos'è successo è l'utente, pasto per pasto — "l'ho seguito" (che scala la
dispensa e toglie quel pasto dalla lista) oppure "ho mangiato altro" (che accoda il
piatto più avanti). Dalla spesa esce il *giorno passato*, non la ricetta: se il piatto
si è accodato, si compra dove è finito.

**"Ho mangiato altro" accoda il piatto, non lo perde.** `is_followed = False` su un pasto (dalla home, dalla
griglia della settimana, dal dettaglio o dalla chat) mette `PlannedMeal.is_skipped` e sposta la sua ricetta sulla prima casella
libera di quello stesso pasto — più avanti in settimana, o sulla prossima se la
settimana è piena (`skip_meal`). Non si sposta nient'altro: gli altri giorni restano
dove sono. La casella saltata **conserva la `recipe_id` come memoria** di cosa c'era in
programma, ma smette di contare ovunque — spesa, totali del giorno (cala anche il
target, non è un buco da colmare), tracking e generazione la filtrano tutti su
`is_skipped`. Il totale della spesa però non cala: la ricetta si compra dove si è
accodata, che è il punto (il piatto si cucina lo stesso, un altro giorno).
`is_followed = True` annulla il rinvio (`unskip_meal`): la ricetta torna e la casella
dove si era accodata si svuota. `skip_day` fa lo stesso per l'intera giornata (weekend
fuori), un pasto alla volta, e solo da oggi in avanti: un giorno già passato lo si
racconta pasto per pasto. **Due flag da non confondere:** `DayPlan.is_skipped`
(giornata intera saltata a mano) e `PlannedMeal.is_skipped` (singolo pasto accodato
altrove).

**La dispensa si riempie con la spesa e si svuota mangiando.** La prima metà la fa
`complete_shopping` (gli articoli spuntati diventano scorta, nella quantità presa
davvero: `ShoppingListItem.bought_quantity`, NULL = quella della lista — le confezioni
non si tagliano a misura, e per 140 g di tacchino si porta a casa il pacco da 400);
la seconda `is_followed = True`, che scala dalla dispensa gli ingredienti della ricetta — ma solo quelli che
in dispensa ci sono davvero. Sale e olio restano fuori da soli, senza un elenco di
eccezioni: non sono scorte, sono ingredienti di base. Senza questa metà, a fine
settimana la dispensa direbbe che è ancora tutto in casa e la spesa successiva
salterebbe mezzo carrello. `PlannedMeal.pantry_used` ricorda **cosa** è stato tolto
(non cosa pesa la ricetta): serve a non scalare due volte se si ripreme il pulsante e
a rimettere l'esatta quantità se il pasto viene corretto in "ho mangiato altro" —
c'erano 40 g e la ricetta ne voleva 100, tornano 40, altrimenti l'app inventerebbe
del cibo. Le scorte senza quantità ("ce l'ho ma non so quanto") non si toccano.
Quando non si scala niente `pantry_used` resta **NULL, non lista vuota**: è la stessa
colonna a fare da guardia contro il doppio scalo, e segnarci `[]` vorrebbe dire "già
fatto" per sempre — un pasto spuntato prima della spesa non si scalerebbe più nemmeno
a dispensa piena. E il perché si dice: `consume_from_pantry` restituisce anche gli
scartati col motivo (`assente`, `senza_quantita`, `unita`, `quantita_ricetta`) e la
risposta li porta in `pantry_skipped`, che il frontend rende con
`nonScalatiDallaDispensa`. Una dispensa che resta ferma senza spiegazioni sembra un
pulsante rotto, mentre il motivo è quasi sempre correggibile in dieci secondi — di
solito lo yogurt contato a vasetti contro una ricetta che pesa in grammi.

**L'aderenza dell'anno è un calendario a colpo d'occhio.** `GET /api/tracking/year`
(`year_adherence`) classifica ogni giorno da `PlannedMeal.is_followed`: tutti "sì" →
`full`, tutti "no" → `missed`, misto → `partial`; un giorno senza nessun pasto tracciato
resta **fuori** (non è un fallimento, è un buco di dati, e contarlo punirebbe chi non
annota). È la stessa lettura del riepilogo settimanale (`entry["is_followed"]`) estesa a
tre stati. Lo `score_pct` pesa full=1, partial=0.5, missed=0 sui soli giorni tracciati.
Il frontend (`YearHeatmap`, scheda "Anno" in Andamento) lo disegna come griglia
settimane×giorni riusando le tinte del tracking (`--success/--warning/--danger`).

**"Lo faccio io" è un flag della dieta, non della settimana.** `MealSlot.auto_generate`
a False significa che l'utente quel pasto lo prepara da sé: l'AI non lo genera mai e i
suoi ingredienti non entrano in lista della spesa, **ma i suoi macro contano lo stesso**
nel totale del giorno e nel tracking, dati per centrati sul target. Scordarsi la seconda
metà è l'errore facile: si vedrebbe un buco di 400 kcal al giorno e l'aderenza a picco
per un pasto che invece rispetta la dieta. Vedi `_is_fixed`, `serialize_week` e
`weekly_tracking`.

**I pasti fissi non si rigenerano.** `is_recurring` o `source == 'user_custom'` →
`_is_fixed()` li salta nella generazione e la settimana successiva se li ricopia
(`apply_recurring_meals`, con `copy_recipe`: copia, non riferimento).

**La chat della spesa cambia un ingrediente in tutta la lista.** Oltre alla chat
sul singolo pasto (`/api/chat/meals/...`, marcatore `[RECIPE_UPDATE]`) c'è la chat "da
supermercato" (`/api/chat/shopping/{week_id}/...`, marcatore `[RECIPES_UPDATE]`): serve a
quando non trovi o vuoi cambiare un alimento, e riscrive in un colpo solo **tutte** le
ricette che lo usano, poi rifà la lista. Vive sulla settimana (`ShoppingChatMessage`,
non sul pasto) ma non si ferma lì: passa al modello un indice compatto dei pasti
modificabili (`_editable_meals`: quelli con ricetta, non su giorno/pasto saltato — cioè
quelli che pesano sulla spesa, su tutte le settimane che la spesa copre) con i loro
`meal_id`, e applica solo gli aggiornamenti che citano un `meal_id` valido. Le
etichette dei pasti portano la data proprio perché "Lunedì / Pranzo" con due settimane
in lista sarebbe ambiguo. Il prompt (`SHOPPING_CHAT_SYSTEM`) sta in `prompts.py` con gli altri.

**In chat la ricetta va dopo il marcatore, mai dentro il messaggio.** `[RECIPE_UPDATE]`
(o `[RECIPES_UPDATE]`) è l'unico modo che ha il backend di sapere che c'è una modifica
da applicare. Un modello che riempie lo schema a mano in markdown — con i nomi dei
campi come titoletti e i dizionari degli ingredienti in chiaro — produce il fallimento
peggiore: l'utente legge un piatto pronto e nel piano non è cambiato niente. I prompt
lo vietano esplicitamente ("il messaggio che legge l'utente è solo prosa") con un
esempio di risposta corretta, e `_needs_marker_retry` riconosce il caso (pezzi di JSON
o nomi di campi nel testo) e richiede la risposta una volta sola, spiegando l'errore:
la prima chiamata è già pagata, la seconda costa meno che perderla. Non si ritenta su
un pasto saltato, dove non ci sarebbe niente da applicare. Le bolle passano da
`ChatText`, che rende il minimo di markdown che i modelli usano davvero (grassetto,
elenchi, paragrafi) costruendo elementi React — nessuna libreria, nessun HTML grezzo.

**Il modello si sceglie per ruolo.** `planning`, `chat`, `diet` hanno pesi diversi:
incastrare trenta pasti nei macro è difficile, rispondere in chat no. `get_client(db,
user, role)` costruisce il client col modello scelto dall'utente (`user_preferences`)
o col default d'ambiente. Aggiungendo un ruolo, aggiornare `ROLES` in `ai_client.py`,
`_DEFAULTS` in `config.py` e `ROLE_LABELS` in `routers/config.py`.

**Il PDF passa prima da `pypdf`.** Estrarre il testo rende la lettura della dieta
indipendente dal modello (funziona anche senza vista) ed è gratis. Solo se il PDF è una
scansione (`looks_scanned`) serve il backend Anthropic, che lo legge nativamente.

**Il ragionamento va tenuto a bada.** Su OpenRouter i modelli che ragionano lo fanno
di default, spesso a effort alto, e i token di ragionamento si scalano da `max_tokens`:
un modello può bruciare l'intero budget pensando e restituire contenuto vuoto. Il
backend manda sempre `reasoning.effort` — `high` solo per la pianificazione, `low` per
chat, rigenerazione e lettura della dieta — e su risposta vuota diagnostica il
`finish_reason` invece di dire genericamente "riprova".

**Generare di default riempie solo i buchi.** `generate_week(..., only_missing=True)`
è il default perché ogni chiamata si paga e quella sulla settimana intera è la più
cara dell'app; `regenerate_all=true` rifà tutto e la UI lo fa confermare. Quello che
conserva la ricetta va comunque nel prompt come `PASTI GIÀ ASSEGNATI`, altrimenti il
modello ripropone un piatto che è già in settimana.

**La generazione in corso è stato del server, non della pagina.**
`WeekPlan.generation_started_at` viene valorizzato prima della chiamata al modello e
azzerato alla fine (anche in caso di errore); `serialize_week` lo espone come
`is_generating` e il frontend ci si riaggancia con un polling. Serve a ritrovare il
caricamento dopo un cambio pagina o un F5, ma soprattutto a rifiutare con 409 una
seconda generazione in parallelo — che sarebbe una spesa doppia. Dopo
`GENERATION_TIMEOUT` (15 minuti) il segno si considera morto, così un processo
riavviato a metà non blocca la settimana per sempre.

**La generazione si può guardare mentre succede.** Dura minuti e si paga: una
schermata ferma non permette di distinguere un modello che ragiona da uno piantato.
`ai_client` accetta un `on_progress(kind, delta)` che riceve i pezzi già in streaming
(`kind` = `reasoning` o `content`; il ragionamento arriva fra i campi extra, che
OpenRouter chiama `reasoning` e altri `reasoning_content`), e `GenerationProgress`
ne scrive coda e contatori in `WeekPlan.generation_progress` ogni due secondi, letti
da `GET /api/planning/weeks/{id}/progress`. Due dettagli non ovvi: le scritture vanno
su una **sessione a parte** (quella della richiesta ha in mano la settimana a metà e
non si può committare per un log), e proprio per questo azzerare il diario a fine
corsa richiede `clear_generation_progress` — assegnare `None` all'attributo non
emetterebbe nessuna UPDATE, visto che quella sessione non sa che il valore sia mai
cambiato. Il numero di ricette scritte si conta dalle chiavi `"title"` nel testo:
parsare un JSON a metà non si può, contare sì. Se il diario non si scrive non
succede niente — ogni errore lì viene ingoiato, sarebbe assurdo perdere una
generazione pagata per un log.

**Una sola chiamata AI per settimana.** L'anti-spreco (mezza zucchina lunedì, l'altra
metà giovedì) funziona solo se il modello vede tutti i pasti insieme. Sopra gli 8.000
token di output `ai_client` passa in streaming da solo.

**Le regole dell'utente sono testo libero, di proposito.** `UserPreferences.notes`
finisce in `CONTEXT_TEMPLATE` così com'è: il destinatario è un modello linguistico,
quindi trasformare "carne rossa al massimo due volte a settimana" in caselle
perderebbe sfumature senza guadagnare niente. Vale per generazione, rigenerazione e
chat, perché tutte e tre passano da `build_context`.

**Il totale giornaliero è invariante.** Aggiungere o togliere un pasto dall'editor
della dieta non cambia quanto si mangia in un giorno, cambia come lo si divide:
`lib/macros.js` ridistribuisce calorie e macro sugli altri pasti in proporzione a
quanto pesavano, con l'ultimo arrotondamento aggiustato perché la somma torni esatta.
Il backend non impone la regola — riceve i pasti e li salva — perché l'editor è un
foglio di lavoro locale e l'utente deve poter correggere prima di salvare.

**I nomi degli ingredienti si normalizzano.** `services/ingredients.normalize_name`
mette in minuscolo e toglie i qualificatori: senza, la lista della spesa avrebbe tre
righe di zucchine e la dispensa non ne coprirebbe nessuna. La linea di taglio è **come
è messo** l'alimento contro **cos'è**: via conservazione (fresco, surgelato,
sgusciato), taglio (a lamelle, grattugiato, a fettine), calibro (medie, grandi, bio) e
le glosse fra parentesi ("pasta corta (penne)"); restano integrale, magro, light,
intero, al naturale, sott'olio — cambiano i macro, quindi cambiano l'alimento — e
"pelati", che è una conserva e non lo stato di un pomodoro. Di conseguenza "surgelato"
non decide più il reparto: la parola sparisce prima di arrivare a `guess_category`, e
il banco giusto lo sceglie l'utente dalla lista (dove la scelta resta).

Oltre a togliere parole, `normalize_name` **unisce** quello che per la dieta e per la
spesa è lo stesso alimento: i formati della pasta (`_PASTA_TYPES`: penne, fusilli,
spaghetti → `pasta`), i pesci bianchi (`_PESCE_MAGRO` → `filetto di pesce magro`) e i
formaggi da grattugia (`_DA_GRATTUGIA` → `formaggio grattugiato`). Sono liste da
allargare col bilancino, perché **unire due alimenti diversi è un danno che si disfa a
mano**: `riso`, `cous cous`, `farro`, `orzo` finiti dentro `_PASTA_TYPES` hanno reso
"pasta" mezzo ricettario, e la fusione cancella la riga di anagrafica — il nome
originale resta solo nel testo della ricetta. Le unificazioni confrontano il **nome
intero** e non una parola in mezzo, o "grana padano" diventa "formaggio padano". I
nomi fabbricati così vanno aggiunti a `utils/pricing.py`, o restano senza prezzo.

Cambiata una regola, le righe già in tabella vanno riallineate a mano:
`python -m app.merge_ingredients` fonde i doppioni spostando ricette, dispensa, liste
e preferenze sulla riga buona. Se la fusione ha unito troppo,
`python -m app.repair_cereals` rimette al loro posto le ricette che nel testo dicono
ancora cous cous o riso; la dispensa no, perché le scorte sommate non si dividono.

**Niente email, in tutta l'app.** Nessun SMTP, nessuna registrazione, nessun recupero
password via link: l'utente nasce dal seed e l'unico endpoint pubblico è `/auth/login`.
Se la password si perde si usa `python -m app.reset_password` dal container. Cancellare
la riga utente per farla ricreare dal seed **distrugge tutti i dati** (FK in CASCADE).

**Le rotte sono `def`, mai `async def`.** Il lavoro dell'app è sincrono e bloccante
(SQLAlchemy senza async, chiamate al modello che durano minuti): su una rotta `async`
girerebbe sull'event loop e congelerebbe l'intero server — durante una generazione
perfino `GET /api/auth/me` restava appeso. Con `def`, FastAPI le esegue in un
threadpool. La regola non ha eccezioni e `tests/test_concurrency.py` la fa rispettare.

## Convenzioni

- **Ogni query su dati personali va filtrata per `user_id`.** L'app è single-user ma lo
  schema no: un endpoint che dimentica il filtro è un bug di sicurezza, non di stile.
  Per i pasti si passa da `_get_meal()`, che risale la catena pasto → giorno → settimana.
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
- Un solo file CSS (`index.css`) con custom properties. Niente CSS modules, niente Tailwind.
- **Il telefono è il caso normale** (lista della spesa al supermercato, "l'ho seguito"
  dopo cena): tre regole che si dimenticano scrivendo su un monitor. Le altezze a
  schermo pieno vanno in `dvh` — `100vh` su iOS comprende la barra degli indirizzi e
  manda l'ultima riga (di solito il campo della chat) sotto il bordo. Tutto ciò che è
  `fixed` o incollato a un bordo somma `env(safe-area-inset-*)`, perché
  `viewport-fit=cover` lascia passare la pagina sotto la tacca. E ciò che compare solo
  `:hover` col dito non compare mai: le correzioni per il touch stanno nel blocco
  `@media (pointer: coarse)` in fondo al foglio, bersagli da 44px compresi.
- **Indietro non deve mai uscire dall'app**, e va sempre da `useGoBack(fallback)`
  (`lib/navigation.js`), mai `navigate(-1)` da solo. Sulla prima pagina della
  sessione dietro non c'è niente, e su iPhone — dove DietAI si apre a schermo intero
  dalla home — "niente" è uno schermo nero da cui si esce solo chiudendo l'app. Il
  caso non è raro: iOS chiude le app in background e le riapre sull'ultimo indirizzo,
  che diventa l'unica voce di cronologia. `key === 'default'` riconosce quella voce.
- **Nessuna pagina renderizza il vuoto.** Se il caricamento fallisce si mostra
  `LoadError` (messaggio + Riprova), mai `return null`: col tema scuro il vuoto è uno
  schermo nero, e il toast dell'errore dopo tre secondi non c'è più. Per lo stesso
  motivo le rotte stanno dentro un `ErrorBoundary`: un errore in un componente
  staccherebbe l'intero albero React lasciando la finestra nera.
- La griglia settimanale (≥1100px) allinea le righe sciogliendo `.day-column` con
  `display: contents`, e **ogni cella dichiara riga e colonna** (inline, da `WeekGrid`).
  Non affidarsi al posizionamento automatico: il cursore di CSS Grid non torna
  indietro fra colonne e manderebbe l'intestazione del secondo giorno in fondo.
- **Testo UI in italiano.** Codice, commenti e nomi in inglese solo dove è già così.
- **Una voce di menu, un posto.** Nelle impostazioni ci va quello che si imposta una
  volta e poi resta. Quello che cambia di continuo ha una pagina sua: la dieta
  (`/diet`), da cui nasce tutto il resto, e la dispensa (`/pantry`), che si riempie da
  sé a ogni spesa e sta accanto alla lista perché ne è l'altra metà. Prima le due voci
  "La mia dieta" e "Impostazioni" aprivano la stessa pagina su schede diverse, e si
  accendevano a vicenda a seconda della scheda aperta. `/settings` rimanda alla prima
  scheda (`/settings/preferences`) così quella aperta è sempre nell'indirizzo; i vecchi
  `/settings/diet` e `/settings/pantry` rimandano alle pagine nuove.
- I prompt stanno tutti in `services/prompts.py`: i vincoli devono essere identici tra
  generazione, rigenerazione e chat, altrimenti l'AI si contraddice da una schermata all'altra.
- **I segnaposto dei prompt si riempiono con `prompts.render()`, mai con `str.format()`**:
  i prompt contengono esempi JSON, e per format() ogni graffa del JSON è un campo da
  sostituire (la chat è rimasta morta così, con un KeyError su `{
 "title"`).
  `tests/test_chat.py` ha una guardia che rende il template su tutti i prompt.

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
.venv/Scripts/python.exe -m app.seed                    # utente + ~180 ingredienti
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000

# Frontend (altro terminale)
cd frontend && npm install && npm run dev               # http://localhost:3000

# Test (SQLite in memoria, nessuna chiamata al modello, "oggi" fissato a lunedì)
cd backend && .venv/Scripts/python.exe -m pytest tests -q
```

Al primo login parte l'onboarding: API key del provider → PDF della dieta → ingredienti
→ preferenze. Senza API key le funzioni AI rispondono 400 con un messaggio esplicito.

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
- **Cambiare il comportamento dell'AI:** `services/prompts.py`. Se cambia la forma del
  JSON atteso, aggiornare anche chi lo consuma (`planner.generate_week`, `recipes.create_recipe`).
- **Cambiare modello:** dalla UI (Impostazioni → Modelli AI, per ruolo) oppure
  `AI_MODEL_PLANNING` / `AI_MODEL_CHAT` / `AI_MODEL_DIET` per il default d'ambiente.
- **Cambiare provider:** `AI_PROVIDER` + `AI_BASE_URL`; la API key salvata va reinserita.
- **Aggiungere ingredienti al catalogo:** `utils/pricing.py` (categoria + prezzo), poi
  `python -m app.seed` per riallineare l'anagrafica.
