# Nomi degli ingredienti e accorpamenti

Normalizzazione, catalogo prezzi, regole dalle Impostazioni. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**Il reparto di un nome nuovo si indovina dall'inizio delle parole, e dal primo
nome.** Quello che il catalogo non conosce passa da `guess_category`, che lavorava a
pezzi di parola in mezzo al nome e con l'ordine delle categorie come arbitro: "pepe"
dentro "peperoni" li mandava fra i condimenti, "mel" dentro "melanzane" fra la frutta,
"grana" dentro "melagrana" fra i latticini — venti voci del catalogo su centottanta
sbagliate, misurate facendo indovinare al codice il reparto dei nomi che il catalogo
ha già. Ora una parola chiave vale solo **a inizio parola**, decide la **prima parola
del nome** che ne riconosce una (in italiano il nome che conta è il primo: "salsa di
pesce" è una salsa, "petto di pollo" è pollo perché "petto" non dice niente) e fra più
parole chiave vince **la più lunga** ("peperon" batte "pepe"). La stessa misura è la
guardia (`test_reparti.py`). Le righe già in tabella col reparto indovinato male le
rifà il seed (`reguess_categories`), lasciando stare quelle spostate a mano.
