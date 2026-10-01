# Generazione delle ricette e modelli

Ruoli dei modelli, budget di ragionamento, cosa si genera, stato e diario della generazione. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**E alla fine anche il lavoro è uscito dalla richiesta.** Stato, diario ed errore
stavano già sul `WeekPlan` perché la risposta della POST arrivava di rado; restava che
la POST rimanesse appesa per minuti su una connessione che il proxy aveva già chiuso,
tenendo occupato un worker del threadpool per niente. Ora `generate_week(...,
background=True)` prepara tutto nella richiesta — validazione, prompt, sorteggio,
client, il segno `generation_started_at` — e lascia a un thread (`_in_background`)
solo la parte che dura: la chiamata al modello e la scrittura del piano
(`_run_generation`). La rotta risponde **202** con la settimana già «in generazione»,
e il frontend non annuncia più niente sulla risposta: l'esito lo dice il polling, come
già faceva.

Tre dettagli. Il thread ha una **sessione sua**: quella della richiesta si chiude
quando la richiesta finisce, e gli oggetti si ricaricano per id dentro il thread. Il
client AI invece passa così com'è, perché non tiene in mano il database. Il thread è
`daemon`: se il processo si riavvia a metà, la settimana resta «in generazione» fino
a `GENERATION_TIMEOUT`, che è esattamente quello che succedeva prima con la richiesta
appesa — il segno sul database è l'unica cosa che sopravvive a un riavvio. E un errore
nel thread non ha nessuno a cui arrivare: `_run_generation` lo logga e lo scrive sulla
settimana prima di rilanciarlo, `_in_background` lo ingoia.

La suite genera in primo piano (`generazione_in_primo_piano` in `conftest.py`, che
spegne `planner.GENERATION_IN_BACKGROUND`): ogni test legge il piano dalla risposta,
come prima. `test_generazione_in_background.py` riaccende il background, mette il
lavoro in coda invece di lanciarlo — SQLite in memoria ha una connessione sola, e due
thread insieme proverebbero il driver invece dell'app — e prova il thread vero a parte,
su un database suo.
