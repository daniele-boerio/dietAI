# Il piano della settimana

Settimane, caselle, pasti saltati, fissi, «lo faccio io» e ricette condivise. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**"Lo faccio io" è un flag della dieta, non della settimana.** `MealSlot.auto_generate`
a False significa che l'utente quel pasto lo prepara da sé: l'AI non lo genera mai e i
suoi ingredienti non entrano in lista della spesa, **ma i suoi macro contano lo stesso**
nel totale del giorno e nel tracking, dati per centrati sul target. Scordarsi la seconda
metà è l'errore facile: si vedrebbe un buco di 400 kcal al giorno e l'aderenza a picco
per un pasto che invece rispetta la dieta. Vedi `_is_fixed`, `serialize_week` e
`weekly_tracking`. E nell'editor della dieta i suoi numeri non li muove nessun altro:
la ridistribuzione del lucchetto lo salta (vedi `docs/dieta.md`, *Ma la ridistribuzione salta i pasti «lo
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

**Cucinare per più persone, e una volta per più giorni.** La dieta è di una persona,
ma in cucina spesso non si è soli e non sempre si cucina ogni giorno. Sono due
impostazioni del pasto, accanto a «lo faccio io», nell'editor della dieta.

`MealSlot.servings` dice per quante persone si cucina. La ricetta e i macro **restano
per una**: sono la dieta di chi usa l'app, e moltiplicarli vorrebbe dire sbagliare il
totale del giorno. A moltiplicare sono la spesa (`_aggregate_ingredients`, ricetta per
ricetta) e la dispensa quando si segna «l'ho seguito» (`consume_from_pantry(...,
servings)`): dal frigo è uscito per tutti. Il foglio della ricetta lo scrive accanto agli
ingredienti, perché chi cucina per due deve leggerlo lì.

`MealSlot.batch_days` dice per quanti giorni di fila si mangia lo stesso piatto,
cucinato una volta. La generazione mette in fila i giorni da riempire di quel pasto e li
taglia in **gruppi di giorni consecutivi** (`_batch_groups`): un buco — un giorno
saltato, una casella già piena — chiude il gruppo, perché un piatto cucinato lunedì per
mercoledì non è un batch, è un avanzo dimenticato. Al modello si chiede solo la prima
casella di ogni gruppo, con la nota «BATCH» (regola 10: un piatto che regge in frigo e
si riscalda, grammature sempre per una porzione); le altre ricevono la stessa ricetta
dopo, ed è la ricetta condivisa di sempre — modificare un giorno ne stacca una copia. È
la stessa scelta del sorteggio delle cucine: «ripeti lo stesso pranzo per tre giorni»
scritto in un prompt è un invito a variarlo, e la regola VARIETÀ lo vieterebbe comunque.

Un limite noto: le frequenze settimanali si assegnano sulle sole prime caselle dei
gruppi, quindi un batch di pesce da tre giorni conta per l'assegnazione come una volta
sola. Il resoconto dopo la generazione invece conta il piano vero, e lo dice. Guardie in
`tests/test_porzioni_batch.py`.
