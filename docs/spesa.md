# Lista della spesa e dispensa

La lista come funzione del piano, i reparti, la dispensa che si riempie e si svuota. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**I prezzi non ci sono più** (migrazione `0032`). C'erano una stima del costo dai prezzi
medi del catalogo, il prezzo pagato scritto a mano su ogni riga (che insegnava il prezzo
al chilo all'anagrafica), la lettura della foto dello scontrino, un livello di budget e
un tetto settimanale in euro che arrivavano al modello e si confrontavano col totale.
Le medie nazionali al negozio vero non dicevano quasi niente, il prezzo scritto «a
spesa fatta» non funzionava (dopo «Ho fatto la spesa» la riga usciva dalla lista e
segnarne il prezzo dava 404: nei test passava solo perché SQLite riusava gli id), e
l'utente non li usava: ha deciso di toglierli tutti. Il riquadro accanto alla lista
ora dice quanti articoli restano da prendere, e la lista è fatta solo di nomi,
quantità e reparti. Se un giorno i prezzi tornassero, il primo problema da risolvere è
dove restano visibili le righe già comprate.

**La lista si aggiorna per differenza, e gli id restano.** `rebuild_shopping_list`
cancellava tutte le righe e le riscriveva a ogni lettura: gli id cambiavano a ogni GET,
e una spunta data dal telefono mentre il computer rileggeva la lista finiva in un 404.
Ora la riga che serve ancora si aggiorna (la quantità), quella nuova si aggiunge,
quella che non serve più si toglie; spunta e quantità presa stanno sulla riga e non
vanno più ricopiate.

**Il reparto di un ingrediente lo decide chi fa la spesa.** `Ingredient.category`
serve a girare il supermercato una volta sola, e il catalogo non può sapere che gli
il seitan sta con la carne (`guess_category` non lo riconosce e finisce in
"altro"). `PUT /api/config/ingredients/{id}/category` li sposta per tutte le liste,
presenti e future, e alza `category_by_user`: senza quel flag il seed — che gira **a
ogni avvio del container** e riallinea l'anagrafica al catalogo — se la riprenderebbe
al primo deploy. Il raggruppamento avviene alla lettura (`serialize_shopping_list`),
quindi non serve ricostruire niente.

Il reparto sta sull'anagrafica, che è **una per tutti gli account**:
quello che sposta un ospite lo vede anche l'amministratore. È voluto — gli account
sono della stessa casa e girano gli stessi negozi, e un reparto per persona vorrebbe
dire una tabella in più e ogni lettura della lista da riscrivere — e la review di
sicurezza lo ha segnalato come canale fra account: per questo lo dice un test
(`test_il_reparto_e_della_casa` in `tests/test_due_account.py`). Se un giorno
gli account non fossero più della stessa casa, è il primo posto da separare.

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

La lista ha una riga per (ingrediente, unità), la dispensa una per ingrediente: le
uova in grammi e le uova "2 unità" sono due righe da spuntare e una scorta sola. Prima
`complete_shopping` cercava la scorta con una query per ogni riga, e senza autoflush
non vedeva quella appena aggiunta dalla riga precedente: due scorte dello stesso
ingrediente, `uq_pantry_item` violato, e "Ho fatto la spesa" rispondeva 500 per
intero. Ora le scorte toccate nel giro si tengono in un dizionario; se le due righe
hanno unità che non si sommano vince la prima. Guardia in `tests/test_dispensa.py`
(`test_lo_stesso_ingrediente_in_due_unita_non_rompe_la_spesa`).

Il piano resta modificabile sempre: passato, presente e futuro, spesa fatta o no. Se
cambi una ricetta già comprata l'app **non tocca la dispensa** — quello che è in casa
resta in casa, e la scorta la corregge chi apre il frigo. È una scelta esplicita:
indovinare cosa è rimasto sarebbe peggio che lasciar fare all'utente.
`refresh_week_statuses` archivia le settimane passate a ogni lettura, senza scheduler,
ma "archiviata" è un'etichetta, non un lucchetto.

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

**Quello che scade si usa prima.** «Dispensa attuale (da consumare in via
prioritaria)» valeva per tutta la dispensa allo stesso modo: la ricotta che scade
dopodomani pesava quanto il pacco di riso. `PantryItem.expires_on` è facoltativa — la
si segna per le cose che scadono davvero — e `_pantry_descriptions` ne fa due usi:
l'ordine (prima ciò che scade, poi il resto) e una scritta accanto alla voce entro
`SCADENZA_VICINA_GIORNI` (7) con **la data**, perché giovedì è troppo tardi per una
cosa che scade martedì. Per la stessa ragione la riga della dispensa nel contesto non
passa da `_fmt_list`, che mette in ordine alfabetico. Una scorta già scaduta resta in
elenco con l'avviso di non usarla invece di sparire: la lista della spesa la conta
ancora come presente, e toglierla di nascosto dal contesto la farebbe ricomparire nel
piano con un altro nome.

La spesa fatta non tocca la scadenza di una scorta che c'era già: la data si riferiva
al pacco vecchio, e indovinare quella del nuovo sarebbe inventare. La si corregge dalla
dispensa. Guardie in `tests/test_scadenze.py`.
