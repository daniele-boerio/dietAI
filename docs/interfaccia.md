# L'interfaccia

Le schermate (piano, home, dettaglio del pasto) e le convenzioni visive. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**In griglia ci sono tutti i pasti, anche quelli che DietAI non genera.** Per un giro
«lo prepari tu» era finito in un riquadro a parte, in colonna a destra, col
ragionamento che una card senza ricetta è una card con dentro niente. Sbagliato: quel
pasto **lo mangi**, quindi va segnato come tutti gli altri — «l'ho seguito» e «ho
mangiato altro» contano nella giornata e nell'aderenza esattamente uguale, e il
riquadro li rendeva le uniche due caselle della giornata su cui non si poteva
rispondere. Adesso stanno in fila con gli altri, con le stesse tre azioni, e a
distinguerli è il **cappello** accanto al nome del pasto (`.meal-mark.mine`, lo stesso
segno della griglia della settimana) più il segnaposto in terracotta (`.dish.mio`) —
che non è tratteggiato come quello di una casella vuota: lì non manca niente da
riempire. Il backend li accettava già: `consume_from_pantry` prende un `recipe_id`
nullo e `skip_meal` non sposta un pasto che prepari tu.

A destra (`.page-aside`) resta quello che si guarda ogni tanto: la **spia
dell'aderenza** delle ultime quattro settimane e i tre numeri (`.mini-stats`).

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

## Convenzioni visive

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
