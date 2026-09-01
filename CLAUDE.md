# DietAI — Dieta, ricette e lista della spesa

## Cos'è questo progetto

Webapp **a pochi account** (l'amministratore e chi invita lui) che prende la dieta —
il PDF del nutrizionista, oppure un questionario quando una dieta scritta non c'è — la
fa leggere a un modello linguistico e genera ogni settimana un piano di ricette che
rispetta i macro, con la lista della spesa già compilata. La lista dice sempre **quello che il piano chiede da oggi
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
│       ├── seed.py             # `python -m app.seed`: amministratore + anagrafica ingredienti
│       ├── reset_password.py   # `python -m app.reset_password '...'`: unica via di rientro
│       ├── make_admin.py       # `python -m app.make_admin`: rialza il flag di amministratore
│       ├── delete_user.py      # `python -m app.delete_user --email ...`: cancella un account
│       ├── merge_ingredients.py # `python -m app.merge_ingredients`: fonde i doppioni di anagrafica
│       ├── merge_recipes.py    # `python -m app.merge_recipes`: fonde le ricette identiche
│       ├── routers/            # auth, admin, diet, config, planning, recipes, chat, shopping, tracking
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
│       │   └── tracking.py     # pianificato vs target
│       └── utils/
│           ├── units.py        # conversione unità (g/ml/unità)
│           ├── seasonality.py  # stagionalità prodotti italiani
│           ├── nutrition.py    # questionario → calorie e macro (Mifflin-St Jeor)
│           └── pricing.py      # catalogo ingredienti: categoria + prezzo medio
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

## Concetti da avere in testa

**Gli account sono più d'uno, ma la API key la mette una persona sola.**
`User.is_admin` è chi paga: l'unico che vede la schermata della chiave
(`PUT /api/auth/api-key` è `get_current_admin`), l'unico che sceglie i modelli
(`/api/config/ai/models`, GET e PUT) e l'unico che crea account
(`/api/admin/*`). Gli altri **generano con la sua chiave e con i suoi modelli**:
`ai_owner(db, user)` restituisce l'admin per chi non lo è, e `get_client` costruisce
il client su quello — chiave, modello e conto sono suoi. Nascondere la scheda nel
frontend non basta e non è la difesa: le rotte rispondono 403 da sole
(`tests/test_due_account.py`).

Due conseguenze che si dimenticano scrivendo il codice. La prima: `has_api_key` in
`/api/auth/me` dice **la chiave con cui quell'utente genererà**, non "ne possiede
una" — e il gate dell'onboarding pesa la chiave solo per chi la gestisce
(`can_manage_api_key`), altrimenti l'ospite resterebbe chiuso nel percorso guidato
per sempre, con tutti i passi fatti. La seconda: i messaggi d'errore non possono
mandare in "Impostazioni → Account" chi quella schermata non ce l'ha.

Il flag arriva da tre parti, in ordine di quanto è probabile: la migrazione `0015` lo
dà all'utente più vecchio, il seed lo dà a `SEED_USER_EMAIL` **quando in tabella non c'è
nessun amministratore** (gira a ogni avvio del container, quindi si ripara da sé al
primo deploy), e `python -m app.make_admin [--email ...]` lo alza a mano. Serve un
comando perché da qui non si esce dalla UI: le rotte che rimetterebbero il flag sono
proprio quelle riservate all'amministratore, e un database senza admin è chiuso a
chiave dall'interno.

Due interruttori, che sono due problemi diversi: `is_active` toglie l'accesso
(login 403, `get_current_user_id` 403, sessioni revocate e `token_version` alzata,
perché sospendere deve avere effetto adesso e non fra mezz'ora) e `ai_enabled` spegne
solo le funzioni AI — l'app resta in piedi, i dati non si toccano, ed è il freno sulla
bolletta di chi mette la chiave. Cancellare un account porta via tutto (FK in
CASCADE): è proprio il motivo per cui esiste la sospensione. L'amministratore non si
sospende, non si cancella e non si resetta da solo (`_target` in `routers/admin.py`):
da lì si tornerebbe soltanto con `python -m app.reset_password` dal container. Un
**altro** amministratore il pannello non lo tocca affatto, e per quello c'è
`python -m app.delete_user --email ...`: senza `--yes` stampa solo l'inventario di cosa
sparirebbe, e si rifiuta di lasciare l'app senza amministratori o di cancellare
l'utente di `SEED_USER_EMAIL`, che il seed ricreerebbe al riavvio successivo.

Quello che **non** è per-utente è l'anagrafica ingredienti (`Ingredient`): è un
dizionario di nomi, reparti e prezzi al kg, non un dato personale. Se un utente
corregge il prezzo del pane, il pane costa quello per tutti.

**Chi non ha una dieta scritta la calcola.** `POST /api/diet/questionnaire` prende
sesso, età, altezza, peso, attività e obiettivo, e ne ricava una
`DietPlan` **identica alle altre** — stessi `MealSlot`, stessi target, stessa
modificabilità: da lì in poi l'app non sa e non deve sapere da dove vengono i numeri.
Il conto lo fa una formula (`utils/nutrition.py`: Mifflin-St Jeor → fattore di
attività → scarto dell'obiettivo → proteine sul peso, grassi in percentuale,
carboidrati per differenza), non il modello: è gratis, istantaneo, riproducibile e
verificabile, mentre chiedere gli stessi numeri a un modello costerebbe una chiamata e
darebbe risposte diverse a parità di risposte. Due pavimenti che non si tolgono: non
si scende mai sotto il metabolismo basale né sotto il minimo per sesso, perché un
calcolo automatico che sbaglia in difetto fa danno. Le risposte restano in
`parsed_data["profile"]` (esposto come `profile` da `_serialize_diet`): il peso
cambia, e riaprire il questionario già compilato deve costare tre secondi.

**Il questionario si fa in due tempi, e il secondo è "quali pasti".** Prima i dati
della persona, che danno i totali del giorno; poi si spuntano i pasti che si fanno
davvero — chi la colazione la salta non deve ritrovarsela in griglia tutti i giorni —
e i totali si dividono su quelli. In mezzo serve `POST
/api/diet/questionnaire/preview`, che calcola **senza salvare**: creare la dieta al
primo passo per sostituirla al secondo vorrebbe dire archiviare una dieta mai vista da
nessuno a ogni ripensamento. Il peso di ogni pasto sta in `MEAL_CATALOG`, **uno solo
per pasto e non per combinazione**: `_share_out` normalizza sulla somma di quelli
scelti, quindi togliere la colazione manda il suo 20% sugli altri in proporzione senza
una tabella per ciascuna delle 63 combinazioni. Le chiavi scelte finiscono nel profilo
anche quando la richiesta diceva solo `meals_count`, così riaprendo il questionario le
caselle sono già quelle di prima. La divisione usa la stessa aritmetica di
`lib/macros.js` — quote arrotondate e resto sulla più grande — così la somma dei pasti
è **esattamente** il totale del giorno; il frontend divide in locale mentre si spunta
(`splitByWeights`, coi pesi serviti da `/questionnaire/options`) invece di chiamare il
server a ogni clic, e quello che si vede è quello che verrà salvato.

**La settimana esiste sempre.** `GET /api/planning/weeks/current` crea al volo
`WeekPlan` + 7 `DayPlan` + una `PlannedMeal` per ogni incrocio giorno × pasto, anche
vuota. Generare vuol dire riempire le caselle libere. Se la dieta cambia,
`ensure_week_structure` riallinea le settimane esistenti.

**Cambiare dieta sposta le caselle, non le somma.** Ricalcolare i macro dal
questionario o caricare un altro PDF non modifica i `MealSlot`: ne crea di nuovi e
lascia i vecchi attaccati alla dieta archiviata. Le caselle già in griglia puntano a
quelli, e `ensure_week_structure` aggiunge le sue per i pasti nuovi: senza altro la
settimana finiva **con due colazioni, due pranzi e due cene** — le vecchie piene, le
nuove vuote — e la doppia riga si portava dietro totali del giorno, spesa e aderenza.
Perciò prima di creare il mancante si passa da `realign_to_diet`, che sposta ogni
casella sul pasto **omonimo** della dieta attiva (`_slot_key`: stesso nome a meno di
maiuscole e spazi). Si sposta invece di ricominciare da capo perché la ricetta che c'è
dentro è costata una chiamata al modello e quello che l'utente ha già segnato è storia
sua: cambiano solo i target. Sparisce solo ciò che nella dieta nuova non ha più un
posto — chi la colazione smette di farla non se la ritrova in piano tutti i giorni — e,
se la casella nuova esiste già, sopravvive quella che ha qualcosa da dire
(`_casella_vissuta`: una ricetta, un "l'ho seguito", un rinvio). Due dettagli:
`uq_planned_meal` vieta due caselle sullo stesso (giorno, pasto), quindi si cancella e
si fa `flush()` **prima** di spostare, o la UPDATE arriverebbe prima della DELETE; e il
riallineamento sta nella lettura, non nella rotta della dieta, così le settimane già
sdoppiate si rimettono a posto da sole appena le si apre. Guardia in
`tests/test_cambio_dieta.py`.

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

La schermata è a due colonne: a sinistra i reparti (in due colonne loro, `columns: 2`
con `break-inside: avoid` — i reparti hanno da due a dodici voci l'uno e il
multi-colonna le altezze le bilancia da sé, mentre una griglia a due celle lascerebbe
«frutta e verdura» da sola a sinistra); a destra il **conto**, appiccicato in alto
perché il totale cambia a ogni spunta ed è quello che si guarda mentre si spunta,
e sotto la chat. Sul telefono la chat torna a essere il cassetto di prima
(`useDueColonne`), perché al supermercato lo schermo è uno solo.

`meals_to_buy` è il cuore: pasti con una ricetta, da oggi in avanti, non su un giorno
saltato, non saltati e **non già segnati come seguiti** — quel piatto è stato
cucinato, ricomprarlo sarebbe comprarlo due volte. In avanti si arriva a **domenica
otto** (`shopping_horizon`, `SHOPPING_HORIZON_WEEKS = 2`): due settimane e non una,
perché il lunedì non è un muro e l'anti-spreco vive lì (una confezione sola invece di
due mezze); due e non "tutte", perché più in là il piano non è una previsione ma
un'ipotesi — le settimane future nascono appena le si sfoglia e ci si ricopiano dentro
i pasti fissi da sole (`apply_recurring_meals`), quindi senza tetto bastava guardare
avanti nel calendario per far crescere la lista all'infinito, e una lista che comprende
marzo non dice più cosa comprare oggi. Quello che resta fuori si dichiara
(`meals_beyond`): una lista più corta del piano, senza una riga che lo spieghi, sembra
una lista che ha perso dei pezzi. Di liste ce n'è una sola
(`current_list`, agganciata alla settimana corrente solo perché la riga deve stare da
qualche parte) e non si chiude mai: `completed_at` dice quand'è stato l'ultimo giro.
Chi tocca il piano chiama `rebuild_shopping_list(db, user_id)` — la dashboard legge la
lista senza ricostruirla.

**I prezzi veri battono il catalogo.** `utils/pricing.py` porta medie nazionali: nel
negozio dove l'utente fa la spesa valgono poco, ed è per questo che un totale stimato
non dice quasi niente. `PUT /api/shopping/items/{id}/price` chiede la cifra che si ha
sotto gli occhi — quanto è costato *quel* pacco — e `unit_price_from` (l'inverso di
`price_for`) ne ricava il prezzo al kg/l/unità, che finisce su `Ingredient` e da lì in
poi vale per tutte le liste.

**Ma la cifra scritta a mano è un fatto, e non si ricalcola.** Sta sulla riga
(`ShoppingListItem.paid_price`, migrazione `0019`) e il costo della riga è quello,
punto; il prezzo unitario che se ne ricava serve a stimare le righe che un prezzo
scritto non ce l'hanno. Prima si teneva solo il prezzo al chilo e la riga veniva
**ricalcolata** ogni volta da quello per la quantità del momento: bastava correggere
quanto se n'era preso davvero (il pacco da 1 kg invece dei 700 g che servivano), o
rigenerare una ricetta che di quell'ingrediente ne chiede di più, perché il numero
appena battuto ne diventasse un altro — e al supermercato sembrava che l'app cambiasse
i prezzi da sé. Tre corollari: `rebuild_shopping_list` si porta dietro `paid_price`
come già faceva con la spunta e la quantità presa, cambiare la quantità presa non
tocca la cifra ma **rifà** il prezzo unitario (lo stesso scontrino per 400 g invece di
140 vuol dire un altro prezzo al chilo, ed è quello che l'app impara), e togliere la
spunta la cancella — «non l'ho preso» vuol dire che non l'ho nemmeno pagato — mentre
il prezzo al chilo resta, perché quello lo si è visto davvero. Guardie in
`tests/test_dispensa.py`. Come per il reparto serve un flag (`price_by_user`) che
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

**Un articolo che è anche in dispensa dice perché è in lista lo stesso.** La quantità
che si legge è già netta della dispensa, e questo rende la nota gratis: se una voce è
in lista `net > 0`, quindi la scorta compatibile è stata scalata tutta e quella cifra
è quello che *manca*. Da lì `_pantry_note` distingue i due casi che senza una riga di
spiegazione sembrano un errore dell'app — la scorta c'era ma non bastava (`usable`:
niente da riparare, si toglie solo il dubbio che la dispensa non venga contata) e
**l'unità che non si parla** (30 ml di limone contro una ricetta che li conta a unità:
lì non si è potuto scalare niente, ed è l'unico caso in cui la lista chiede davvero una
cosa che in casa c'è). Il secondo è un link a `/pantry?fix=<ingredient_id>`, che apre
quella riga già in modifica: è riparabile in dieci secondi, ma solo se lo si vede — la
stessa ragione per cui "l'ho seguito" restituisce `pantry_skipped` col motivo. La nota
si calcola in `serialize_shopping_list` e non in `rebuild_shopping_list`, come il
reparto: è un dato derivato, e in una colonna vorrebbe dire una migrazione più un
valore da riallineare a ogni modifica della dispensa, cioè un modo per farlo mentire.

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

**Nel grafico della settimana il colore dice l'aderenza, non lo scarto dal target.**
Una barra per giorno: l'altezza sono le calorie in programma, il colore è **verde se
il giorno è stato seguito, rosso se no, grigio se non è ancora arrivato** (o se la
giornata è saltata). Prima erano due barre — quella grigia del target dietro, quella
colorata da `compliance_color` davanti — e il colore diceva quanto il *piano* si
scostava dalla dieta: su un giorno che non avevi ancora segnato si accendeva di giallo
come se fosse andato storto qualcosa, mentre la domanda che ci si fa guardando quel
grafico è un'altra. Lo scarto dal target resta scritto in chiaro, in lettere, nella
lista «Giorno per giorno» a fianco e nelle tre piastrelle sopra. `compliance_color`
resta in uso per i pallini di quella lista e per il riepilogo settimanale.

Un conto da tenere presente: un giorno **passato e mai segnato** finisce rosso, perché
per l'app quella giornata una risposta non ce l'ha e non c'è modo di distinguerla da un
«no». È l'opposto della regola del calendario dell'anno, dove un giorno non tracciato
resta fuori — lì il numero è una media e contarlo falserebbe il conto, qui è una barra
in un grafico di sette e toglierla lascerebbe un buco nella settimana.

**"Lo faccio io" è un flag della dieta, non della settimana.** `MealSlot.auto_generate`
a False significa che l'utente quel pasto lo prepara da sé: l'AI non lo genera mai e i
suoi ingredienti non entrano in lista della spesa, **ma i suoi macro contano lo stesso**
nel totale del giorno e nel tracking, dati per centrati sul target. Scordarsi la seconda
metà è l'errore facile: si vedrebbe un buco di 400 kcal al giorno e l'aderenza a picco
per un pasto che invece rispetta la dieta. Vedi `_is_fixed`, `serialize_week` e
`weekly_tracking`. E nell'editor della dieta i suoi numeri non li muove nessun altro:
la ridistribuzione del lucchetto lo salta (vedi *Ma la ridistribuzione salta i pasti «lo
faccio io»*).

**I pasti fissi non si rigenerano.** `is_recurring` o `source == 'user_custom'` →
`_is_fixed()` li salta nella generazione e la settimana successiva se li ripropone
(`apply_recurring_meals`, che assegna la **stessa** ricetta: vedi qui sotto).

**E togliendo la spunta se ne vanno anche le copie già fatte.** Un pasto fisso si
ricopia da sé sulle settimane che si aprono — e una settimana si apre anche solo
sfogliandola — quindi quando si toglie il «fisso» quelle copie sono già scritte in
giro: spegnere l'interruttore e trovarsi la luce accesa lo stesso è il motivo per cui
la spunta sembrava non funzionare. `stop_recurring_forward` svuota le caselle che
hanno **quella** ricetta su **quel** pasto e il segno di fisso addosso (una colazione
uguale scelta a mano non ce l'ha, e resta dov'è), e la rotta rifà la lista della spesa
e risponde con `cleared_forward`, che il frontend dice nel toast: sette caselle che si
svuotano in silenzio sembrano un guasto. Due limiti, per non cancellare fatti invece
di previsioni: solo **dopo** la casella da cui si toglie e mai prima di oggi, e mai
dove l'utente ha già segnato com'è andata. Quelle che restano perdono comunque il
**segno** di fisso, che è la parte che si propaga: `apply_recurring_meals` legge la
settimana precedente, quindi con la regola "daily" bastava una casella accesa il
lunedì per far ricomparire tutto la settimana dopo, e togliere la spunta dal mercoledì
sembrava non aver fatto niente. Guardie in `tests/test_pasti_fissi.py`.

**Eliminare una ricetta da un pasto non è «ho mangiato altro».** Sono le due cose che
si confondono, e fanno l'opposto: «ho mangiato altro» il piatto lo tiene (resta
scritto, si accoda più avanti, la spesa lo compra dove è finito), il cestino lo toglie
dal piano e la casella torna vuota come se non fosse mai stata riempita
(`clear_meal_cell`: via anche il fisso, che su una casella vuota non vuol dire niente,
e via la memoria del rinvio). La ricetta resta nel ricettario: si svuota il posto, non
si cancella il piatto. Sta nella card della griglia accanto a ✓ e ✗ — è lì che si
guarda la settimana — e passa da una conferma, perché a due centimetri c'è «l'ho
seguito». Toglie solo quella casella: le copie di un pasto fisso già messe nelle
settimane dopo si levano dal dettaglio, togliendo «Fisso», e la conferma lo dice.

**Lo stesso piatto è una ricetta sola.** Il ricettario è l'archivio dei piatti, non il
diario delle caselle: la colazione che si ripete sette giorni è un piatto. Prima ogni
casella si portava dietro la sua riga — `create_recipe` una per pasto generato,
`copy_recipe` una per settimana sui pasti fissi (per **giorno**, con la regola
"daily") — e l'archivio cresceva di una riga al giorno per lo stesso identico piatto,
con voti e preferiti sparpagliati su dieci copie che nessuno teneva allineate. Ora
`create_recipe` prima di inserire cerca un gemello (`find_twin`) e se lo trova
restituisce quello. Identico vuol dire **stesso nome, stessi macro, stessa spesa**
(l'insieme di ingrediente × quantità × unità, confrontato sull'`ingredient_id` cioè
dopo la normalizzazione del nome); procedimento e descrizione restano fuori dal
confronto, perché un modello che riscrive gli stessi passi con altre parole non ha
inventato un altro piatto — e includerli vorrebbe dire non deduplicare mai niente. Le
candidate si pescano per calorie, che sono un intero e tagliano l'archivio in un colpo
solo.

Una riga condivisa però non si può modificare come se fosse di uno solo, ed è qui che
sta il lavoro vero. **Quello che è già stato non si riscrive: modificare un giorno crea
una ricetta nuova.** `fork_recipe_for_meal` è la contropartita della riga condivisa:
chi modifica *da un pasto* — la chat del pasto, quella della spesa, la sostituzione di
un ingrediente con `meal_id` — se quel piatto è in programma anche altrove ne stacca
prima una copia, e la modifica finisce solo lì. È la stessa garanzia di quando le copie
si facevano subito ("modificare la colazione di questa settimana non riscrive quella
archiviata"), pagata solo quando serve davvero. Conta come uso **qualunque** altra
casella, comprese quelle saltate: la `recipe_id` di una casella saltata è la memoria di
cosa c'era in programma quel giorno, quindi è storia come il resto.
E **`settle_recipe`** è il ritorno: dopo la modifica, se il piatto è diventato uguale a
uno che c'è già si torna a una riga sola. Serve al caso che la chat della spesa produce
da sé — "le zucchine non le trovo" riscrive tutte le ricette che le usano, e due caselle
appena staccate ricevono la stessa identica modifica — e a quello, frequente, del
modello che rimanda la ricetta invariata. La riga lasciata indietro si cancella solo se
non la usa più nessuno **e** non porta un voto o un preferito: quello è un giudizio
dell'utente, non un residuo.

Un posto sfruttava "stessa ricetta" come identità e ora non regge più:
`unskip_meal` cercava la casella dove il piatto saltato si era accodato confrontando le
`recipe_id`, e con le ricette condivise avrebbe svuotato la prima colazione uguale che
incontrava. Per questo `PlannedMeal.skipped_to_meal_id` (migrazione `0018`, con
backfill della vecchia regola finché è ancora univoca) scrive **dove**, invece di
indovinarlo. Il puntatore è un indirizzo e basta: annullando il salto si svuota quella
casella senza confrontare le ricette, perché nel frattempo il piatto rimandato può
essere stato modificato in chat — e la modifica gliene ha staccata una copia sua. A
tenere onesto l'indirizzo è `forget_queued_meal`, che lo cancella appena in quella
casella si mette dentro qualcos'altro di proposito (rigenerata, riassegnata, svuotata):
da lì in poi quello che c'è l'ha scelto l'utente, e nessun "in realtà l'ho seguito"
deve portarselo via.

Per l'archivio già gonfio c'è `python -m app.merge_recipes`: senza `--yes` stampa solo
cosa fonderebbe, con `--yes` tiene la riga con più storia addosso (prima i preferiti,
poi il voto più alto, poi la più vecchia), ci sposta le caselle del piano e cancella le
gemelle. Va lanciato **dopo** la migrazione, mai prima: è la migrazione a leggere le
`recipe_id` ancora tutte diverse. Guardie in `tests/test_ricette_doppie.py`, dove il
modello finto propone lo stesso piatto tutti i giorni — come fa chiunque a colazione.

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

Il sostituto viene spesso dalla dispensa — è il posto giusto da cui prenderlo — e lì il
**nome conta quanto l'alimento**: "peperoni rossi" al posto dei "peperoni" che si hanno
in casa è un altro ingrediente per la lista, che li farà ricomprare. Per questo la regola
NOMI sta in `CONTEXT_TEMPLATE` (vale anche per la generazione, che la dispensa ce l'ha
davanti allo stesso modo) e la chat della spesa ci aggiunge di non consigliare l'acquisto
di quello che è già in casa. È una cintura sopra una bretella: se il modello scrive lo
stesso un nome suo, `normalize_name` lo riporta sulla riga giusta.

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
user, role)` costruisce il client col modello scelto dall'**amministratore**
(`user_preferences` della riga di `ai_owner`) o col default d'ambiente. Aggiungendo un ruolo, aggiornare `ROLES` in `ai_client.py`,
`_DEFAULTS` in `config.py` e `ROLE_LABELS` in `routers/config.py`.

**Il PDF passa prima da `pypdf`.** Estrarre il testo rende la lettura della dieta
indipendente dal modello (funziona anche senza vista) ed è gratis. Solo se il PDF è una
scansione (`looks_scanned`) serve il backend Anthropic, che lo legge nativamente.

**Il ragionamento si chiede in token, non in "effort".** Su OpenRouter i modelli che
ragionano lo fanno di default e i token di ragionamento **si scalano da `max_tokens`**:
un modello può bruciare l'intero budget pensando e restituire contenuto vuoto. Il freno
c'era già, ma era `reasoning.effort: high` per la pianificazione — ed è stata la
trappola: `high` riserva al ragionamento **circa l'80% di `max_tokens`**, mentre
`max_tokens` è calcolato sul solo contenuto (~2.000 token a ricetta). Su una settimana
da nove pasti — 24.000 token — al modello restavano ~4.800 per scriverne nove: ogni
generazione finiva con `finish_reason` "length" e contenuto vuoto, dopo minuti di
attesa e a chiamata pagata. Non era un modello sbagliato, era una richiesta
impossibile, e **non è una questione di scala**: spezzare la settimana in giorni
riproduce lo stesso rapporto più in piccolo (12.000 token → ~2.400 per tre ricette).
Ora `thinking=True` manda `reasoning.max_tokens` a un quarto del budget, così al
contenuto resta sempre la maggioranza; `thinking=False` resta `effort: low`, che sui
compiti brevi va bene. La garanzia sta in `tests/test_reasoning_budget.py`, che la
verifica sulla strada dello streaming — l'unica che la pianificazione prende davvero.
Su risposta vuota si diagnostica comunque il `finish_reason` invece di dire
genericamente "riprova".

**Generare di default riempie solo i buchi.** `generate_week(..., only_missing=True)`
è il default perché ogni chiamata si paga e quella sulla settimana intera è la più
cara dell'app; `regenerate_all=true` rifà tutto e la UI lo fa confermare. Quello che
conserva la ricetta va comunque nel prompt come `PASTI GIÀ ASSEGNATI`, altrimenti il
modello ripropone un piatto che è già in settimana.

**Ma prima si sceglie cosa generare.** Il pulsante non parte più: apre
`WeekGenerateDialog`, dove si spuntano **i giorni** (i sette della settimana come un
calendario, col numero di caselle da fare su ognuno) e **i pasti** (le colazioni e gli
spuntini se li prepara chi se li prepara, e pagarne sette è pagarli per niente). La
selezione viaggia nel corpo della POST — `days` (`day_of_week`) e `slot_ids` — e in
`generate_week` sono due filtri sopra i generabili, non una strada nuova: resta **una
chiamata sola**, perché l'anti-spreco vive lì, e quello che resta fuori dalla selezione
ma una ricetta ce l'ha finisce comunque nel prompt come `PASTI GIÀ ASSEGNATI`. Corpo
assente vuol dire tutta la settimana — è come chiamano ancora i test — mentre una lista
**vuota** è una scelta esplicita e si risponde che nella selezione non c'è niente da
fare, invece di rifare tutto per un campo che si è solo svuotato.

Tre cose che la dialog decide e il server no. I giorni **passati partono spenti**
(quel pasto è stato o non è stato, riempirlo adesso è una chiamata pagata per niente),
ma restano spuntabili e si accendono da soli se il da fare è tutto lì, o una settimana
archiviata aprirebbe la dialog col pulsante disattivato e nessuna spiegazione. La
scelta dei **pasti** si ricorda in `localStorage` — si ricordano gli **esclusi**, così
un pasto aggiunto alla dieta dopo nasce acceso — mentre i giorni no, che cambiano ogni
settimana. E "rifai anche i pasti già pronti" è una casella dentro la dialog invece di
un secondo pulsante: è la stessa domanda, e da lì si può rigenerare *solo le cene di
lunedì* invece che tutto.

La conta delle caselle sta in `lib/generation.js` (con `generation.test.js`) e non
dentro il componente perché deve dare **lo stesso risultato del server**: il numero
scritto sul pulsante ("Genera 9 pasti") è una promessa su quanto si sta per pagare, e
le due condizioni — giorno saltato, pasto rimandato, pasto «lo faccio io», pasto fisso
— sono le stesse di `generate_week`. Guardie in `tests/test_genera_selezione.py`.

**Generare un singolo pasto sono due cose, con lo stesso pulsante.** Senza indicazioni
sceglie il modello, col vincolo di proporre qualcosa di diverso dal piatto di prima e
dagli altri della settimana. Con indicazioni — `POST
/api/planning/meals/{id}/regenerate` con `user_request` nel corpo, che resta
**facoltativo** perché la griglia settimanale chiama la stessa rotta senza — decide
l'utente («ho del salmone da finire», «qualcosa con la zucca») e all'AI resta il
mestiere: scegliere e **pesare** gli ingredienti perché i macro del pasto tornino,
completare quello che manca e scrivere il procedimento. È il buco che la chat non
copriva: lì si parte da una ricetta e la si modifica, qui la casella può essere ancora
vuota. Nel prompt la richiesta arriva come `RICHIESTA DELL'UTENTE`, e
`SINGLE_MEAL_SYSTEM` dice che **comanda lei**: le regole di varietà decadono (chiedere
"come ieri ma col tacchino" è legittimo), i macro e gli ingredienti esclusi no — se il
piatto chiesto non ci sta nei target il modello aggiusta le quantità o
l'accompagnamento e lo scrive nella descrizione, invece di sfondare i numeri.
Dal frontend, a casella vuota, le vie per riempirla stanno **tutte e tre in fila** nello
stato vuoto, con tre nomi diversi perché sono tre cose diverse: *Scegli tu il piatto*
(genera e basta, un clic), *Genera da una mia idea* (apre `GenerateDialog`, il campo di
testo) e *Scegli dal ricettario*. Il pulsante primario in cima alla pagina compare solo
a casella piena, dov'è *Rigenera*: quando la casella è vuota sarebbe il gemello del
primo dei tre — stessa azione, nome quasi uguale, in un altro punto dello schermo.
Il campo lasciato vuoto nel dialogo ricade sulla generazione di sempre, e il pulsante
prende lo stesso nome dell'altra strada (*Scegli tu il piatto*) per dirlo. Guardie in
`tests/test_genera_su_richiesta.py`.

**Una card pasto è una riga, e lo stato si dice una volta sola.** La griglia della
settimana e la lista del telefono sono lo **stesso** markup (`MealCard`) in due versi:
in griglia la cella è incolonnata, sotto i 768px diventa una riga — testo a sinistra,
le due risposte a destra — e passa da 215px a ~90px, cioè da due pasti e mezzo per
schermata a una giornata intera. Il pezzo non ovvio è `.meal-main { flex: 1 1 0 }`:
con `flex-basis: auto` a decidere se i comandi ci stanno in riga è la larghezza che il
testo *vorrebbe* (max-content), quindi con un titolo lungo andavano a capo sempre.

Lo stato di una casella era detto in cinque modi contemporaneamente — pastiglia
SALTATO rossa piena, titolo barrato, bordo tratteggiato, filetto sul bordo, pulsante
✗ acceso — e su sette giorni la settimana sembrava un errore di sistema. Ne restano
due: il filetto colorato e **la parola** nel piede (`seguito`, `rimandato`), perché il
colore da solo non basta (daltonismo, schermo al sole). Il colore è il **terracotta**
della palette e non `--danger`: quel rosso nell'app vuol dire "azione distruttiva", e
aver mangiato altro è un fatto, non un guasto. Vale ovunque si dica la stessa cosa —
card della settimana, card di oggi (`.btn-moved`), barra del pasto.

Com'è *fatta* la casella (fissa, «lo prepari tu», scritta da te) sono tre segni
accanto al nome del pasto — puntina, cappello, matita — al posto di tre pastiglie in
fondo alla card: erano l'unica cosa uguale in tutte e ventotto le celle, e coprivano
l'unica cosa che cambia, il piatto. E i pasti fissi o gestiti dall'utente prendono
`.quiet` (fondo spento): sono già decisi e in griglia sono metà delle caselle, quindi
quello che si scorre davvero — pranzi e cene — viene avanti.

I comandi rari stanno dietro il `⋯`, che apre *dentro* la card (rigenera, elimina):
sempre a schermo erano quattro icone per cella, centoventi bersagli che nessuno cerca.
Una casella vuota non ne mostra nessuno e ha un solo pulsante «Genera», invece delle
stesse quattro icone di cui tre spente.

**Il piano si tiene la sua testata.** Sul telefono `.plan-head` è `sticky` in cima e
contiene titolo, frecce e la striscia dei sette giorni: arrivati a domenica erano una
settimana più su, e per cambiare settimana bisognava risalire tutto. Una barra dell'app
sopra non c'è — la navigazione sta in fondo (vedi *Sul telefono si naviga da sotto*) —
e questa è l'unica cosa ferma della pagina.

La striscia (`.day-strip`, con `DayDots`) è insieme indice e stato: una tessera per
giorno — nome in monospaziato, numero in serif, e sotto quattro pallini che dicono
com'è andata (verde seguito, terracotta rimandato, grigio ancora da vivere, vuoto da
riempire) — e un tocco salta al giorno, che era il problema di partenza. Il giorno che
si sta guardando è **pieno di lime**: un contorno acceso su una tessera da 51px non si
vede. Le frecce della settimana stanno nel titolo, come sul monitor, e quelle della
striscia sono sparite: erano le stesse due a tre centimetri di distanza. Dove fermarsi
lo misura `margineTestata()` sull'elemento vero, perché l'altezza della testata cambia
coi pulsanti che ci stanno dentro.

«Genera i N mancanti» scende in fondo, sopra le schede, e prende tutta la riga: è il
comando della pagina, si preme una volta e si paga, e in testata rubava metà riga al
titolo.

Nella griglia il totale del giorno e i pallini stanno nell'**intestazione** della
colonna: in fondo, dopo quattro card, finivano sotto la piega di qualunque schermo.

**La home mette i pasti sopra la piega, e il resto in colonna.** Quattro piastrelle di
statistiche occupavano tutto lo spazio sopra la piega e spingevano sotto «cosa si
mangia oggi», che è il motivo per cui si apre l'app. Adesso a sinistra c'è la giornata
in un numero (`.day-summary`: quanto si mangia oggi su quanto, coi macro accanto), poi
i pasti in riga (`.today-grid`), poi la barra lime della spesa (`.shop-bar`) — che non
è una statistica, è quello che si fa dopo aver guardato i pasti.

A destra (`.page-aside`) sta quello che accompagna: i pasti che **DietAI non genera**
(«lo prepari tu», i fissi), che una card non ce l'hanno perché non c'è niente da
generare, ma vanno scritti lo stesso — una giornata da cinque pasti che ne mostra tre
sembra una giornata a cui ne mancano due; la **spia dell'aderenza** delle ultime
quattro settimane; e i tre numeri che si guardano ogni tanto (`.mini-stats`).

La spia (`recent_adherence` in `services/tracking.py`, esposta dalla dashboard) è una
barra per giorno e dice **due cose con due canali**: l'altezza è quanto il piano di
quel giorno pesava sul suo target, il colore è com'è andata davvero. Tenerle separate
serve: una giornata pianificata benissimo e mai seguita è alta e spenta, ed è
esattamente quello che si vuol vedere da lontano. Un giorno senza nessun pasto
tracciato resta grigio e **fuori dal punteggio** — è un buco di dati, non un
fallimento, la stessa regola del calendario dell'anno.

Il pulsante «Genera N pasti» della testata porta alla settimana **con la dialog già
aperta** (`state: { genera: true }`, letto da `PlanningPage`): generare passa sempre da
lì, perché è la schermata dove si vede cosa si sta per pagare, e un pulsante che
promette sei pasti non può lasciare su una pagina in cui bisogna ancora cercare da dove
si comincia.

**Nel dettaglio del pasto le due risposte stanno sotto il pollice.** `.meal-bar` è
`sticky` in fondo sul telefono, dove «l'ho seguito» era in fondo a una pagina lunga un
metro — ricetta, ingredienti, procedimento — e la sera il pasto si apre proprio per
premerlo. Le stesse due dentro la card «com'è andata?» si nascondono lì
(`.andata-answers`), o sarebbero un doppione; il terzo pulsante porta alla chat, che
sul telefono sta sotto la ricetta invece che di fianco.

**La generazione in corso è stato del server, non della pagina.**
`WeekPlan.generation_started_at` viene valorizzato prima della chiamata al modello e
azzerato alla fine (anche in caso di errore); `serialize_week` lo espone come
`is_generating` e il frontend ci si riaggancia con un polling. Serve a ritrovare il
caricamento dopo un cambio pagina o un F5, ma soprattutto a rifiutare con 409 una
seconda generazione in parallelo — che sarebbe una spesa doppia. Dopo
`GENERATION_TIMEOUT` (15 minuti) il segno si considera morto, così un processo
riavviato a metà non blocca la settimana per sempre.

**E anche com'è finita è stato del server**, per la stessa ragione portata fino in
fondo: la risposta della POST quasi mai arriva a destinazione. Una generazione dura
minuti e davanti c'è un proxy che chiude molto prima — nginx a `proxy_read_timeout
300s`, Cloudflare a 100 secondi e basta — quindi il messaggio d'errore finiva scritto
su una connessione morta, e uvicorn non ne lasciava traccia nemmeno nell'access log
(salta la riga quando il client si è già disconnesso, `h11_impl.py`). Da fuori restava
una settimana vuota senza spiegazioni, e la pagina, che segue il polling e non la
risposta, annunciava pure "Settimana pronta ✓". Ora `record_generation_failure` scrive
il motivo nella stessa colonna del diario — che a generazione ferma è libera — e
`generation_error(week)` lo espone in `serialize_week` e nell'endpoint del progresso;
il frontend lo mostra al posto del ✓ e lo lascia in un riquadro finché non si riprova,
perché un toast di tre secondi scade quando davanti allo schermo non c'è nessuno. Si
cancella da sé all'inizio del tentativo dopo: racconta l'ultimo tentativo, non è una
macchia sulla settimana. Due corollari per chi tocca `generate_week`: **quello che può
fallire sta dentro il `try`**, applicazione della risposta compresa (una risposta
parsabile ma di forma sbagliata sollevava fuori di lì e lasciava la settimana ferma su
"sto generando" per un quarto d'ora), e il fallimento **si logga** — è l'unico posto
dove quel messaggio arriva a qualcuno che possa leggerlo.

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

**Il totale giornaliero è invariante finché il lucchetto è chiuso.** Sono due domande
diverse — *quanto* mangio in un giorno e *come* lo divido — e confonderle si paga:
togliendo la colazione perché non la si fa ci si ritroverebbe con 400 kcal in meno al
giorno, cioè con una dieta diversa da quella prescritta. Perciò i totali stanno chiusi
a chiave e i pasti no. Col lucchetto chiuso (il default, a ogni apertura della pagina)
aggiungere o togliere un pasto ridistribuisce calorie e macro sugli altri in
proporzione a quanto pesavano, e **anche correggere un singolo pasto** manda la
differenza sugli altri (`rebalanceField`), col valore scritto fermato al totale perché
gli altri non vadano in negativo. Aperto, i campi sono liberi ed è il totale a
cambiare: è la strada di chi ha numeri nuovi, non di chi riorganizza la giornata.
Richiudendolo, i totali di adesso diventano il nuovo vincolo.

**Ma la ridistribuzione salta i pasti «lo faccio io».** Il lucchetto divide la
giornata fra i pasti che DietAI genera: quello che prepara l'utente ha numeri che ha
scritto lui — quanto pesa il panino della mensa lo sa soltanto lui — e correggere la
colazione non può riscrivergli lo spuntino. `isMine` (`auto_generate === false`) è il
segno, e lo rispettano tutte e tre le operazioni: `rebalanceField`, `removeMeal` e
`addMeal` (che la sua quota la prende dai soli pasti liberi, per lo stesso motivo).
Cambia anche il tetto del valore scritto: non è più il totale del giorno ma **quello
che resta** dopo i pasti fermi, o gli altri finirebbero in negativo per far posto. Il
caso limite si dichiara invece di essere aggirato: senza nemmeno un pasto libero il
lucchetto non ha più a chi girare la differenza, quindi il valore torna quello di prima
(`rebalanceField` restituisce lo spazio disponibile, che a totale invariante è il
valore di partenza) e la pagina dice di aprire il lucchetto — un campo che non si
lascia scrivere, senza una riga che spieghi perché, sembra rotto. Stessa cura per gli
altri due: togliere un pasto senza nessun libero **accorcia** davvero la giornata e il
messaggio lo dice, e il pasto aggiunto in quella situazione nasce a zero. Guardie in
`lib/macros.test.js`.

Il riallineamento aspetta il `blur`, non il tasto: ridistribuire a ogni battuta farebbe
ballare gli altri pasti su "6" e su "60" mentre si scrive "600", e un pasto che passa
da zero perderebbe per strada le proporzioni. Nel frattempo il totale in fondo mostra
lo scarto — è il modo più corto per dire perché gli altri stanno per muoversi. Da qui
il `draft` in `DietPage`: `commit()` chiude la modifica **e restituisce** i pasti
aggiornati, perché premendo "Salva" da dentro un campo il blur e il clic arrivano nello
stesso batch di React e lo stato sarebbe ancora quello di prima.

Il backend non impone niente di tutto questo — riceve i pasti e li salva — perché
l'editor è un foglio di lavoro locale e l'utente deve poter correggere prima di
salvare. L'unico posto dove i totali forzati arrivano al server è il questionario, che
li accetta come `targets` e ci divide sopra i pasti: lì i pavimenti della formula (mai
sotto il metabolismo basale) **non si applicano**, perché difendono un calcolo
automatico, non discutono i numeri di chi li sta scrivendo a mano.

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
spesa è lo stesso alimento, col nome che usa la dieta: i formati della pasta
(`_PASTA_TYPES`: penne, fusilli, spaghetti, e anche "pasta integrale" → `pasta`), i
pesci bianchi (`_PESCE_MAGRO` → `filetto di pesce magro`), i formaggi da grattugia
(`_DA_GRATTUGIA`: parmigiano, grana padano → `formaggio`). Sono liste da allargare col
bilancino, perché **unire due alimenti diversi è un danno che si disfa a mano**:
`riso`, `cous cous`, `farro`, `orzo` finiti dentro `_PASTA_TYPES` hanno reso "pasta"
mezzo ricettario, e la fusione cancella la riga di anagrafica — il nome originale
resta solo nel testo della ricetta. Le unificazioni confrontano il **nome intero** e
non una parola in mezzo, o "grana padano" diventa "formaggio padano".

Prima di tutto il resto viene `_segni`, che dà **un modo solo di scrivere** apostrofi,
spazi ed elisioni: l'apostrofo tipografico che il modello mette da sé diventa quello
dritto, gli spazi che non si vedono diventano spazi, e "di" davanti a vocale si elide
("olio di oliva" → "olio d'oliva", che è anche la forma del catalogo). È il doppione
peggiore che ci sia: in dispensa compaiono due righe di "tonno all'olio d'oliva"
identiche a leggersi, e non c'è modo di accorgersene guardando né di correggerle con
una regola scritta a mano — anche quella andrebbe scritta con l'apostrofo giusto.

`_VARIANTI` è il gradino sotto: la stessa parola scritta in due modi ("couscous" →
"cous cous"). Non è un accorpamento — non si uniscono due alimenti — e infatti si
applica **sulla parola** e non sul nome intero, o "couscous integrale" resterebbe una
riga a sé.

Sempre per lo stesso motivo, **singolare e plurale sono lo stesso alimento** e finiscono
sulla forma del catalogo, che è quella a cui sono attaccati reparto e prezzo
(`_CATALOG_FORMS`: "peperone" → "peperoni", "cetriolo" → "cetrioli", "uovo" → "uova").
La mappa si **deriva** dal catalogo invece di scriverla a mano — un elenco a parte
resterebbe indietro al primo ingrediente aggiunto — e genera solo le coppie che in
italiano sono davvero singolare/plurale (o↔i, a↔e, e↔i): senza quel vincolo "pesca" e
"pesce" avrebbero lo stesso gambo e la frutta diventerebbe pesce. Una forma che porta a
due nomi del catalogo, o che è già un nome del catalogo, si lascia stare. Il confronto è
sul nome intero e si fa **per ultimo**, dopo accorpamenti e qualificatori: prima
"sedani" dev'essere diventato pasta, e "peperone rosso" dev'essere già "peperone".

Chi unisce tocca anche `utils/pricing.py`, in due modi: il nome fabbricato va aggiunto
(o resta senza prezzo, e sono sempre le voci più care) e quelli che ha inghiottito
vanno tolti — il seed semina l'anagrafica coi nomi del catalogo così come sono
scritti, quindi un nome che `normalize_name` non può più produrre diventa una riga che
nessuna ricetta userà mai, ricreata a ogni avvio del container. Non è un promemoria:
`test_normalizzazione.py` rende ogni nome del catalogo e pretende che esca identico, e
che due voci non finiscano sulla stessa riga (sarebbero due prezzi per lo stesso nome,
e a vincere sarebbe l'ultimo seminato). È così che si sono scoperte cinque righe morte
— "tonno fresco", "manzo macinato", "fave secche", "piselli secchi", "frutta secca
mista" — che il seed ricreava a ogni avvio mentre l'alimento vero restava senza prezzo.

**Le stesse regole si allargano dalle Impostazioni**, senza deploy (Impostazioni →
Nomi e accorpamenti, solo amministratore: l'anagrafica è una sola per tutti).
`NormalizationRule` tiene le modifiche — `kind='alias'` è un termine che finisce su un
nome normalizzato, `kind='noise'` una parola da togliere, `kind='off'` **spegne un
termine di serie** — e `load_rules(db)` le compila nella stessa forma di quelle di
serie: una sostituzione con regex su parola intera. I termini di serie restano scritti
nel codice anche da spenti, perché `kind='off'` è una sospensione e non una
cancellazione: `_builtin(spenti)` ricompila le regex senza quei termini (in `lru_cache`,
perché l'insieme cambia una volta ogni mai e normalizzare succede cento volte per
generazione) e togliendo la riga tutto torna com'era. Serve per i termini ambigui —
"sedani" è un formato di pasta ma è anche il plurale del sedano — e per questo la UI li
mostra barrati invece di farli sparire: nascosti, fra sei mesi si riscriverebbero a mano.
Se si spegne l'ultimo termine di un gruppo la sostituzione viene **saltata**, non
compilata vuota (`\b()\b` matcha ovunque). Si applicano **dopo** le regole del codice, che restano la base su cui si
reggono il catalogo dei prezzi e mezza suite di test; per questo un termine si salva
già normalizzato ("pasta rigate", non "penne rigate") e chi ne aggiunge uno inutile si
sente rispondere perché. Senza regole aggiunte `NormalizationRules` è falsa e la
normalizzazione resta identica byte per byte (`__bool__`): è la garanzia che questo
strato non esista finché non lo si usa. Chi chiama `normalize_name` avendo una
sessione in mano **passa sempre** `load_rules(db)` — nessuna cache di processo, perché
sarebbe un valore vecchio da invalidare a mano.

Salvare una regola riallinea subito l'anagrafica (lo stesso lavoro di
`merge_ingredients`), e prima di salvare si passa da `POST
/api/config/normalization/preview`, che dice quali righe cambierebbero nome e quali si
fonderebbero con una che esiste già. L'anteprima non è cortesia: **togliere la regola
non disfa la fusione** — le righe cancellate non tornano e le quantità sommate in
dispensa non si dividono — quindi "riso → pasta" va visto prima, non dopo.

Cambiata una regola nel codice, le righe già in tabella vanno riallineate a mano:
`python -m app.merge_ingredients` fonde i doppioni spostando ricette, dispensa, liste
e preferenze sulla riga buona. Se la fusione ha unito troppo,
`python -m app.repair_cereals` rimette al loro posto le ricette che nel testo dicono
ancora cous cous o riso; la dispensa no, perché le scorte sommate non si dividono.

**Niente email, in tutta l'app.** Nessun SMTP, nessuna registrazione, nessun recupero
password via link: l'unico endpoint pubblico è `/auth/login`. L'amministratore nasce
dal seed; gli altri li crea lui da Impostazioni → Utenti, e la password iniziale gliela
dice a voce (per questo il campo è in chiaro: bisogna poterla leggere per dettarla).
Chi perde la password se la fa rimettere dall'amministratore; se a perderla è
l'amministratore c'è `python -m app.reset_password` dal container, ed è l'unica via.
Cancellare la riga utente per farla ricreare dal seed **distrugge tutti i dati** (FK in
CASCADE) — e il seed **non** ricrea gli altri account: gira a ogni avvio del container
e resusciterebbe ogni volta chi è stato cancellato apposta.

**Le rotte sono `def`, mai `async def`.** Il lavoro dell'app è sincrono e bloccante
(SQLAlchemy senza async, chiamate al modello che durano minuti): su una rotta `async`
girerebbe sull'event loop e congelerebbe l'intero server — durante una generazione
perfino `GET /api/auth/me` restava appeso. Con `def`, FastAPI le esegue in un
threadpool. La regola non ha eccezioni e `tests/test_concurrency.py` la fa rispettare.

## Convenzioni

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
- Un solo file CSS (`index.css`) con custom properties. Niente CSS modules, niente Tailwind.
- **Ogni variante di pulsante porta un bordo di 1px**, anche quando non si vede
  (`border: 1px solid transparent` su `.btn-primary`, `.btn-ai` e `.btn-danger`).
  Senza, un primario è 2px più basso di un secondario — che il bordo ce l'ha davvero —
  e la sua scritta sta un pixel più su: in una riga di tre pulsanti si vede, ed è il
  tipo di disallineamento che si guarda dieci volte senza capire da dove viene.
- **Quello che chiama il modello si vede che lo chiama:** il lime della palette
  (`.btn-primary` se è l'azione principale, `.btn-ai` — tinta tenue, stessa
  costruzione di `.btn-danger` — se è l'alternativa) e l'icona `Sparkles`, la stessa
  di "lo genera DietAI" nell'editor della dieta. Serve perché quelle azioni stanno in
  fila con azioni che non costano niente: scegliere dal ricettario è istantaneo e
  gratis, generare dura minuti e si paga. Unica eccezione, l'icona tonda della griglia
  settimanale, che resta `RefreshCw` perché lì gira su sé stessa mentre lavora — e una
  scintilla che ruota non dice niente a nessuno.
- **L'app è scura, tutta.** Il fondo è un nero caldo (`#14130f`), le card ci stanno
  sopra col loro bordo, e l'accento è un lime (`#d9f24e`). C'era anche una superficie
  chiara (`.on-paper`, crema) sul pasto di adesso, sul foglio della ricetta e sul
  conto della spesa: è stata tolta ovunque — su un'app scura una macchia crema non
  legge come «questa è la cosa», legge come una finestra di un altro programma.
  `data-theme="light"` resta come tema a sé. Tre caratteri con tre mestieri: `--font-display` (Instrument Serif) per i nomi dei piatti e i numeri
  grossi, `--font-body` (Instrument Sans) per il testo, `--font-mono` (JetBrains Mono)
  per etichette e cifre, che devono incolonnarsi da sole. Il serif ha **un peso solo**,
  il 400: scriverci `font-weight: 700` non lo ingrossa, lo fa ingrassare al browser.
- **`--accent` si scrive, `--accent-fill` si riempie.** Sono due token perché sul
  fondo scuro il lime fa tutte e due le cose e su un fondo chiaro nessuna delle due da
  solo: scritto su crema non si legge, ma una pastiglia lime con l'inchiostro sopra sì.
  Quindi al buio i due token coincidono, col tema chiaro `--accent` diventa un oliva
  scuro (per testo, icone, voce di menu accesa) e `--accent-fill` resta il lime (per
  pulsante primario, spunte, barre). Regola pratica: se sopra ci va del testo in
  `--accent-contrast`, il fondo è `--accent-fill`; altrimenti è `--accent`. Stessa
  ragione per cui `.btn-moved` scrive in `--danger-contrast` e non in
  `--accent-contrast`: col tema chiaro il terracotta si scurisce, e l'inchiostro
  sopra sparisce.
- **`--accent-hover` scurisce, in tutti e due i temi.** È il fondo di un
  riempimento — il pulsante primario, la barra della spesa — e un fondo pieno che
  all'hover si schiarisce sembra spegnersi: col lime pallino di partenza la barra
  della spesa diventava quasi bianca sotto il dito. Non ha un valore per tema: nel
  tema chiaro l'oliva scuro di `--accent` ci finiva sotto il testo inchiostro, e il
  pulsante primario all'hover diventava illeggibile.
- **Com'è andata si dice con un anello, non con un fondo.** «Seguito» è un anello
  lime tutt'attorno alla card (bordo più un `inset` da 1px, così segue il raggio) e la
  parola nel piede; «ho mangiato altro» lo stesso in terracotta, più il fondo che se
  ne va. Prima era una tinta verde stesa su tutta la card: copriva il piatto — l'unica
  cosa che cambia da una casella all'altra — e su sette giorni segnati la settimana
  era una parete verde. `box-shadow` **inset** e non esterno: fuori sborderebbe nella
  griglia.
- **All'hover la card si accende di un tono, non si sbianca.** `--bg-card-hover` sul
  fondo e `--border-light` sul bordo. Ed è il momento in cui, nella griglia della
  settimana, compaiono i comandi ✓ ✗ ⋯ — nascosti a riposo dentro
  `@media (hover: hover)`, perché col dito `:hover` non esiste e quello che si mostra
  solo all'hover non si mostra mai. Una casella **vuota** fa eccezione e il suo
  «Genera» ce l'ha sempre: è l'unica cosa che si cerca guardando la settimana.
- **Il menu è una stecca di icone da 84px** (`.sidebar`), non più una colonna di
  etichette da 236: le voci sono otto e non cambiano mai, dopo il primo giorno non si
  leggono più, si mirano. Ogni voce porta **due nomi** — `sidebar-label` intero e
  `sidebar-short` da sei lettere — nello stesso markup. Sotto i 768px la stecca non
  c'è: al suo posto le schede in fondo.
- **Sul telefono si naviga da sotto.** Cinque schede fisse (`.tabbar` in `App.jsx`):
  Oggi, Settimana, Spesa, Ricette e **Altro**, che è una pagina vera (`/altro`,
  `pages/AltroPage.jsx`) e raccoglie quello che non sta nelle quattro — dieta,
  dispensa, andamento, preferenze, la parte da amministratore, l'account, il tema e
  l'uscita. Prima c'erano una barra in alto col pulsante del menu e un cassetto che
  entrava da sinistra: due elementi fermi e due gesti per arrivare dove adesso si
  arriva con un pollice, e 54px di schermo spesi per scrivere il nome dell'app a chi
  l'app l'ha già aperta. Con loro sono spariti `navOpen`, `apriMenu` e
  `testataPropria`, che esisteva solo perché il piano doveva fare anche da barra.
  Le schede **non compaiono sul dettaglio del pasto**: quella schermata ha già la sua
  barra in fondo, e due barre impilate sono centotrenta pixel di comandi sopra la
  piega.
  Le cinque schede non si ricavano dalle otto voci del menu (`schede` è una lista a
  sé): un cassetto può permettersi otto voci, cinque schede larghe 78px no.
- **Sul telefono un pasto è una riga, non una card.** Nella home (`.meal-row`, scelta
  da `useTelefono()` in `lib/schermo.js`) e nella settimana (`.meal-card` riscritta in
  riga con un filetto): quattro card impilate erano 860px per una giornata, cioè due
  schermate per sapere cosa si mangia. Nella settimana in coda alla riga resta **un
  bersaglio solo**, «l'ho seguito» — la cosa che si fa più spesso col telefono in
  mano; «ho mangiato altro» e il cassetto con rigenera ed elimina si aprono dal pasto,
  dove la barra in fondo li ha già tutti sotto il pollice. Tre comandi per riga su
  quattro righe erano dodici bersagli sopra quattro nomi di piatti.
- **La riga della dispensa in modifica è una griglia, non un flex che va a capo.**
  `.pantry-edit` — nome, quantità, unità e i due comandi, una colonna ciascuno, che si
  stringono insieme. Con `flex-wrap`, in una colonna da 320px, il nome scendeva sotto e
  i due pulsanti restavano appesi a destra della riga di sopra. È la stessa forma in
  due momenti: la riga che si aggiunge (`.aggiungi`, col pulsante largo in coda) e
  quella che si corregge (✓ pieno e ✗ di contorno). Sotto i 560px va a capo **in modo
  dichiarato**: il nome si prende tutta la prima riga, il resto sta sulla seconda.
- **La riga di contesto sta sopra il titolo.** Nel markup di una `.page-header` viene
  prima il titolo (è un `h1`, e mandarlo dopo il suo sottotitolo vorrebbe dire
  scrivere la pagina al contrario per un fatto di grafica); a scambiarli è `order`,
  dichiarato solo su quei due. **Non** `column-reverse`: la testata a volte porta
  anche altro, e col verso rovesciato quello finirebbe in fondo. Il sottotitolo prende
  lo stile dell'occhiello — mono, in maiuscoletto, spaziato — perché dove sei si legge
  prima di cosa stai guardando.
- **Metà delle schermate sono a due colonne** (`.page-split`): la cosa a sinistra
  (`.page-main`), e a destra una colonna **stretta e fissa** (`.page-aside`) con quello
  che la accompagna. Fissa e non proporzionale perché contiene sempre le stesse cose e
  non ha bisogno di crescere: a guadagnare spazio su un monitor largo dev'essere la
  lista, la griglia, il foglio della ricetta. La larghezza si passa caso per caso
  (`--aside`: 356px sulla home, 380 sulla spesa, 400 sul pasto, sulla dieta e
  sull'andamento). Sotto i 1100px la colonna passa sotto, nello stesso ordine di
  lettura. `.page-split.pari` le fa alte uguale, e serve dove le due sono due letture
  della stessa cosa — il grafico dell'andamento e i numeri che lo commentano.
- **La ricetta è un foglio, e se lo porta dietro** (`RecipeView`): fascia
  del piatto in cima col tondo per tornare indietro, occhiello, titolo serif,
  pastiglie, i tre macro, ingredienti e procedimento in due colonne, e **in fondo la
  riga delle azioni**. Le tre parti che cambiano col posto da cui si guarda la ricetta
  si passano da fuori (`eyebrow`, `azioni`, `indietro`): dal piano è il pasto di un
  giorno preciso e le azioni sono «l'ho seguito» e «rigenera», dal ricettario è un
  piatto e basta. Il dettaglio del pasto **non ha una testata** quando la ricetta c'è:
  il titolo della pagina è il nome del piatto, ed è scritto sul foglio.
- **Il segnaposto al posto della foto** (`.dish`). Il disegno mette un'immagine su
  ogni card e in cima al foglio della ricetta; DietAI non ha immagini — niente
  caricamento, niente modello che le disegni — ma togliere la fascia lascerebbe le
  card sbilenche, perché l'impaginazione ci conta sopra. Al suo posto un riquadro del
  colore delle superfici incassate con l'icona delle posate in mezzo: dichiara di
  essere un segnaposto invece di fingersi una foto mancante. Per un giro è stato tinto
  dal nome della ricetta, in modo che due card vicine non fossero mai dello stesso
  colore: sette tinte in una griglia da dieci però si guardavano più dei nomi dei
  piatti, che sono la cosa. Il giorno che le foto arrivano, `.dish` è il posto dove ci
  va l'`<img>`.
- **`useDueColonne()` (`lib/schermo.js`) solo dove la larghezza cambia *cosa* è una
  cosa**, non come è fatta. La chat della spesa sul monitor è una colonna in pagina,
  sul telefono un cassetto che si apre da un pulsante e si chiude con la X: due
  componenti con due comandi diversi. Nasconderne uno col CSS vorrebbe dire montarli
  tutti e due — due conversazioni sullo stesso schermo, di cui una invisibile che
  continua a scaricare messaggi. Dove basta il CSS si usa il CSS.
- **Il telefono è il caso normale** (lista della spesa al supermercato, "l'ho seguito"
  dopo cena): tre regole che si dimenticano scrivendo su un monitor. Le altezze a
  schermo pieno vanno in `dvh` — `100vh` su iOS comprende la barra degli indirizzi e
  manda l'ultima riga (di solito il campo della chat) sotto il bordo. Tutto ciò che è
  `fixed` o incollato a un bordo somma `env(safe-area-inset-*)`, perché
  `viewport-fit=cover` lascia passare la pagina sotto la tacca. E ciò che compare solo
  `:hover` col dito non compare mai: le correzioni per il touch stanno nel blocco
  `@media (pointer: coarse)` in fondo al foglio, bersagli da 44px compresi.
- **Più di un'azione in uno stato vuoto va incolonnata** (`.empty-actions`: griglia,
  larghezza uguale, 320px al centro). In riga i pulsanti si allineano solo per
  combinazione — le etichette sono lunghe diverse e `.btn` non manda a capo — quindi
  fra i 1100 e i 1280px, dove accanto c'è ancora la colonna della chat, andavano a capo
  2+1, e sul telefono diventavano una scaletta storta. Sul telefono vale anche per la
  testata: `.page-actions` prende tutta la riga e i pulsanti crescono a riempirla,
  perché il bordo destro frastagliato è la stessa bruttura vista dall'altro lato.
- **Una striscia che scorre di lato deve arrivare dove sei.** È l'errore che si vede
  solo aprendo l'app sul telefono: le schede delle impostazioni scorrevano, e su
  "Utenti" la striscia mostrava ancora le prime tre — la pagina non diceva più dove ti
  trovavi. Ora vanno a capo (`flex-wrap`), che è la soluzione quando le voci sono
  poche e contate. Dove andare a capo non si può — il calendario dell'anno, che di
  colonne ne ha 52 — si scorre da soli fino a oggi al primo render, altrimenti si apre
  su gennaio, cioè su una griglia vuota; e l'incolonnata dei giorni resta `sticky` a
  sinistra, o a metà anno le caselle non hanno più un'etichetta.
- **Una tabella sul telefono diventa una scheda per riga.** Sette colonne in 300px non
  si restringono, si sbriciolano: l'editor della dieta finiva a due campi per riga sotto
  intestazioni che ne annunciavano sei, e quale numero fosse quale non lo diceva più
  niente. Il modo che regge senza duplicare il markup: ogni cella si porta dentro la
  propria etichetta (`.meal-editor-cell > span`), invisibile finché la riga di
  intestazione c'è, e sul telefono l'intestazione sparisce e le etichette escono fuori.
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
- **Il conto della spesa sul telefono è una barra in fondo**, sopra le schede: il
  totale cambia a ogni spunta ed è quello che si guarda mentre si spunta, non
  qualcosa da cercare scorrendo fino in fondo alla lista. È la stessa
  `.shopping-total-card` della colonna di destra, che lì si compatta — via il titolo
  e la frase lunga, che in una barra da 80px non ci stanno.
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
