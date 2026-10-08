# Le cucine del mondo

Catalogo, quote, sorteggio e il vincolo sugli ingredienti. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

**La cucina viaggia, gli ingredienti no.** `UserPreferences.cuisines` tiene le
cucine da cui attingere — chiavi del catalogo in `utils/cuisines.py`, una sessantina
in sei aree — e ha preso il posto dell'interruttore `prefer_italian`, che era la
stessa domanda con una risposta sola: acceso voleva dire "italiana", spento voleva
dire *niente*, cioè la stessa mano libera di chi non aveva mai aperto quella
schermata. I due comandi insieme non si potevano tenere, perché si sarebbero
contraddetti al primo utente che spegneva l'interruttore lasciando "Italiana" spuntata
nell'elenco. La migrazione `0020` converte quello che il flag diceva davvero: acceso →
`["italiana"]`, spento → `[]`.

Il vincolo che rende utile la funzione sta in `prompt_line()`, ed è la seconda metà
della richiesta: **scegliere la cucina giapponese chiede quelle tecniche con la base
che si compra sotto casa.** Una ricetta che vuole la galanga fresca non è una ricetta
difficile, è una ricetta che non si cucina — e peggio, quella roba finisce in lista
della spesa come se bastasse passare al supermercato. Perciò la riga porta due elenchi
corti di esempi, da una parte e dall'altra: "reperibile in Italia" da solo è un
giudizio che il modello dà a sentimento, con due elenchi il confine si vede. Dove il
piatto tipico chiederebbe l'introvabile, il modello mette il sostituto più vicino e
**lo scrive nella descrizione**, invece di cambiarlo in silenzio.

**Ma il confine passa fra il fresco e la bottiglia, non fra l'Italia e il resto del
mondo.** La prima versione della riga diceva "usa SOLO ciò che si compra in un normale
supermercato italiano" e metteva fra gli esempi la sola salsa di soia: il modello ne
ricavava l'ordine di condire con quella **ogni** piatto orientale, e teriyaki, salsa
di ostriche, pesce, hoisin e miso sparivano tutti dentro lo stesso ingrediente. Ma un
saltato condito con la soia al posto del teriyaki non è lo stesso piatto fatto con
quello che c'è, è un altro piatto — e quelle salse si comprano: metà stanno già al
supermercato, il resto si ordina una volta e dura mesi in dispensa. Perciò i
condimenti sono **l'eccezione dichiarata** (`INGREDIENTI_LOCALI`: salse, paste, aceti
e oli si chiamano col loro nome, col divieto esplicito di ridurli alla salsa di soia o
di scambiarli fra loro) e a restare fuori è solo il fresco esotico, che nessuno ordina
per una cena: galanga, foglie di kaffir, erbe asiatiche fresche. La stessa eccezione
va ripetuta dove il vincolo è scritto una seconda volta — `WEEK_PLAN_SYSTEM` (regola
REALISMO), `SINGLE_MEAL_SYSTEM` e `SUBSTITUTE_SYSTEM` —, o il prompt si
contraddirebbe da una schermata all'altra. Resta com'era `SHOPPING_CHAT_SYSTEM`, dove
il sostituto deve stare sullo scaffale davvero: lì l'utente è in negozio e non può
aspettare una consegna. In lista della spesa le salse restano **righe distinte**:
`normalize_name` non le accorpa — sono alimenti diversi, con prezzi diversi — e stanno
a catalogo (`utils/pricing.py`) perché senza una riga di anagrafica il reparto lo
indovina `guess_category`, che proprio sulle più usate sbaglia: "salsa di pesce" al
banco del pesce, "pasta di curry" fra i cereali, "latte di cocco" fra i latticini.

Tre casi e non uno: nessuna scelta lascia mano libera (è quello che si aspetta chi
quella schermata non l'ha aperta), la sola italiana non si porta dietro il discorso
sugli ingredienti — ce li ha già tutti, ed è la riga che si genera più spesso —, e più
cucine insieme si **sorteggiano con le loro quote** (vedi qui sotto). `clean()`
rimette l'ordine del catalogo invece di quello dei clic: la lista finisce in un prompt, e le stesse scelte
spuntate in ordine diverso sarebbero due contesti diversi. Il catalogo è un elenco
chiuso e non testo libero perché la chiave finisce nel prompt **e** nei tag della
ricetta: "giapponese", "Giappone" e "cucina nipponica" scritti a mano sarebbero tre
preferenze per la stessa cosa. Per tutto il resto ci sono le regole libere (`docs/chat.md`).

**E il sorteggio lo fa Python, non il modello.** «Attingi a queste cucine,
alternandole nell'arco della settimana» è un auspicio: il modello ancora sulla prima
voce dell'elenco, o su quella che gli viene più facile — a parità di macro l'italiana
è quella di cui conosce più piatti —, e chi ne ha spuntate otto si ritrova sette cene
italiane. Una cucina **assegnata** è un'istruzione; una da alternare è una speranza.
Perciò `cuisines.draw()` estrae in `generate_week` **una cucina per giorno**, e la
scrive accanto al giorno in `DA GENERARE` (`Lunedì (day_of_week 0) — CUCINA: Greca`):
è il posto dove il modello la legge mentre compone quel giorno, invece che in fondo a
venti righe di contesto. Per giorno e non per pasto perché una giornata coerente è
anche una spesa coerente — è la stessa ragione dell'anti-spreco. Il contesto allora
smette di elencare le cucine e dice soltanto che il sorteggio è **già fatto**
(`PER_GIORNO`), col divieto esplicito di ripiegare sull'italiana: senza quella riga
«CUCINA: Greca» si legge come un suggerimento.

**E ogni cucina si porta dietro la sua quota.** `cuisines` non è un elenco ma una
mappa `{chiave: percentuale}` — `{"italiana": 70, "greca": 30}` — perché «anche la
giapponese» e «una cena giapponese ogni tanto» sono due richieste diverse, e un elenco
le scrive uguali. Le quote **sommano sempre a 100**, e a garantirlo è `clean()`, che
normalizza a ogni lettura: è l'unico modo perché la somma torni anche dopo che una
voce è stata tolta. Sotto c'è `QUOTA_MINIMA = 1`, perché una voce spuntata che non può
mai uscire è una voce che mente — chi non la vuole più ha la X accanto; **se c'è, è
scelta: il numero dice solo quanto**, quindi una quota a zero si porta al minimo
invece di scartare la cucina, che altrimenti sparirebbe dall'elenco al salvataggio.
Il tetto di dodici (`MAX_CUCINE`) non è gusto: con quote da 8% l'una il sorteggio su
sette giorni ne pescherebbe comunque una manciata, e «attingi a queste dodici»
equivale a non aver chiesto niente. In archivio resta la forma della prima versione
(`["italiana", "greca"]`), che vale «in parti uguali»: `_as_shares` la legge invece di
migrarla, perché una migrazione che riscrive un JSON per dire la stessa cosa può solo
introdurre bug, e la riga si risalva da sé.

**Le quote si contano, non si tirano a sorte.** `draw` fa due cose che sono due
domande diverse: **quante** caselle per ciascuna (`_quante_volte`) e **in che ordine**
(`_distanziate`). La prima usa il metodo del resto più grande — la stessa aritmetica
di `_share_out` e di `lib/macros.js` — così il 70% è il 70% **di questa settimana** e
non la media di infinite settimane: con un dado indipendente per giorno, sette
italiane di fila sono un risultato onesto e, per chi guarda il piano, sono il guasto
che le percentuali dovevano riparare. Il resto va a chi ha la parte frazionaria più
alta, coi pareggi sciolti a caso — senza, con tre cucine in parti uguali la carta in
più sarebbe sempre della prima in ordine di catalogo.

La seconda merita la trappola in cui è già caduta una volta. Il modo ovvio di
distanziare — pescare ogni volta la cucina a cui ne restano di più, saltando quella
appena uscita — distanzia benissimo ed è **sempre la stessa fila**: con 5/1/1 usciva
«italiana, greca, italiana, giapponese, italiana, italiana, italiana» a ogni
generazione, cioè il guasto di partenza servito una riga più in là. Ora ogni casella
prende una posizione: la i-esima di una cucina che ne ha `n` cade **a caso dentro
l'i-esima fetta** di settimana larga `1/n`. Le cinque italiane finiscono così una per
fetta — sparse per costruzione — ma dove dentro la fetta lo decide il caso, e la fila
cambia a ogni generazione. Resta da riparare ciò che le fette non garantiscono, cioè
due fette confinanti che consegnano la stessa cucina a cavallo del confine: chi si
trova un gemello accanto cerca uno scambio che sistemi entrambi i posti. Se non c'è si
ripete, e va bene — con l'80% su cinque giorni due di fila sono aritmetica, ed è
esattamente quello che l'utente ha chiesto.

Le percentuali finiscono anche in `prompt_line`, cioè nel contesto di chi **non**
sorteggia: chiedendo in chat un'alternativa a un piatto, la proporzione dice da che
parte guardare — con 70% italiana il sostituto giusto è quasi sempre italiano, e senza
quel numero le due cucine peserebbero uguale.

Nel selettore ogni scelta è una riga con un cursore (`lib/quote.js`, con
`quote.test.js`): alzarne una stringe le altre in proporzione, perché il totale non è
una scelta ma 100 per definizione — è il lucchetto dell'editor della dieta senza il
lucchetto. L'aritmetica è **la stessa** di `clean()` e deve esserlo: il numero che si
legge mentre si trascina è quello che verrà salvato, e se il server ne restituisse un
altro i cursori salterebbero da soli appena lasciati. Per la stessa ragione `riparti`
difende il valore scritto dall'arrotondamento, scaricandolo sulla quota più grande fra
le altre: vedere il proprio 70 diventare 69 da solo è il modo più rapido di non
fidarsi più del cursore.

Anche `regenerate_meal` sorteggia, ed è dove la differenza si sente di più: «rigenera»
premuto tre volte di fila dava tre piatti italiani. Lì si estrae **una** cucina e si
esclude quella del piatto che si sta buttando (`avoid`), che è la stessa ragione per
cui gli si dice di non riproporlo — chi rigenera vuole un'altra cosa; `avoid` però non
svuota mai il mazzo, o chi ha scelto una cucina sola non potrebbe più rigenerare. Con
una **richiesta dell'utente** non si sorteggia niente: «fammi una carbonara» più «oggi
è coreano» sono due ordini contrari, e a scegliere quale seguire sarebbe il modello.

Quello che **non** sorteggia è tutto il resto — le due chat e la sostituzione di un
ingrediente —, e per questo `build_context` prende un `cuisine` già pronto invece di
comporlo sempre da sé: lì si parte da una ricetta che una sua cucina ce l'ha già, e
tirarne un'altra vorrebbe dire riscrivere il piatto invece di correggerlo. Sotto le
due cucine scelte non si sorteggia comunque: non c'è niente da estrarre, e il prompt
resta identico a prima. Guardie in `tests/test_cucine.py`.

Il selettore (`components/CuisinePicker.jsx`, in Impostazioni → Preferenze e
nell'onboarding) scarica il catalogo da `GET /api/config/cuisines` invece di tenerne
una copia, come il questionario con `/questionnaire/options`: due elenchi che si
allontanano sono un 400 in faccia all'utente per una voce aggiunta da una parte sola.
Si cerca per **paese, piatto o area** («Giappone», «sushi», «Asia») e non solo per
l'aggettivo con cui la voce è scritta, che è l'unica delle quattro cose che non viene
in mente per prima — gli alias stanno nel catalogo, accanto alla voce. Le scelte si
vedono due volte, in pastiglia sopra e accese nell'elenco, perché l'elenco scorre e
quello che hai spuntato tre righe fa è già fuori campo. E il salvataggio è l'unico
della pagina che aspetta (`saveTraPoco`, 700ms): le cucine si spuntano a raffica, e
tre clic sarebbero tre PUT e tre «Preferenze salvate ✓».

**La ricetta dice da che paese viene.** `tags.cuisine` è la chiave del catalogo, cioè
un aggettivo e a volte un'area intera («balcanica», «mediorientale», «africana
occidentale»): basta al sorteggio, ma a chi legge la ricetta non dice da dove arriva
il piatto. Perciò `RECIPE_JSON_SHAPE` chiede anche `tags.origin`, il paese in italiano
con la regione dopo un punto mediano quando il piatto è regionale («Italia · Sicilia»,
«Messico · Oaxaca»), e `RecipeView` lo mostra in una pastiglia con la puntina accanto
al tipo di piatto. Sta nella forma condivisa e non in un prompt solo, così lo scrivono
generazione, rigenerazione e le due chat; e siccome la chat riscrive i tag interi, una
ricetta corretta in chat se lo porta dietro. Le ricette di prima non ce l'hanno e non
si migrano: la pastiglia ripiega sulla cucina del catalogo, che dice la stessa cosa
con meno precisione. Guardia in `tests/test_cucine.py`.
