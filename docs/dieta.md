# La dieta: questionario ed editor

Da dove vengono i target del giorno e dei pasti, e come si modificano. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**Le frequenze settimanali sono un dato della dieta, non una regola a parole.** «Pesce
2-3 volte, carne rossa al massimo una»: le diete dei nutrizionisti sono scritte così,
e fin qui il vincolo poteva vivere solo nelle regole libere, cioè in un prompt che il
modello leggeva in fondo a venti righe — un auspicio, come lo era «alterna le cucine».
Ora `DietPlan.frequencies` tiene una riga per gruppo (`utils/frequencies.FOODS`: pesce,
legumi, carne bianca, carne rossa, salumi, uova, formaggi — un catalogo chiuso per la
stessa ragione delle cucine) con minimo e massimo, e Python fa due cose.

Prima della chiamata, `freq.assign` decide quale proteina va in quale **pasto
principale** da generare e lo scrive accanto alla casella in «DA GENERARE» (`PROTEINA:
Pesce`), partendo da quello che la settimana ha già. Prima i minimi che mancano —
sparpagliati: mai due nello stesso giorno, il più lontano possibile, la stessa idea del
sorteggio delle cucine —, poi le caselle libere, che portano il divieto dei gruppi già
al massimo (`PROTEINA: libera, ma non carne rossa`). Un pasto è principale se porta
almeno un quarto delle calorie del giorno (`is_main_slot`): i nomi li sceglie il
nutrizionista, il peso no. La rigenerazione di un pasto non assegna niente — si rifà un
piatto, non si pianifica la settimana — ma dice cosa manca e cosa è già al massimo;
con una richiesta dell'utente tace, perché comanda lei.

Dopo, `frequency_report` conta cosa c'è **davvero** nel piano e `serialize_week` lo
espone: la settimana lo mostra in una riga di pastiglie, in giallo quello che non torna.
Il conto è sul piano e non sul prompt, perché il modello può ignorare un'assegnazione,
e questa riga è dove lo si vede. Conta come «una volta» un piatto che di quel gruppo ha
una porzione vera (`SOGLIA_G`): il cucchiaio di parmigiano non è la porzione di
formaggi, l'acciuga nel sugo non è il pesce.

Le frequenze arrivano dal PDF (il prompt di lettura le chiede, e dice di non
inventarle), si correggono dalla pagina della dieta e, per chi non ha una dieta
scritta, ci sono quelle delle linee guida CREA a un clic — proposte, mai imposte. Una
dieta nuova senza frequenze sue **eredita quelle della precedente**
(`_deactivate_previous`): chi ricalcola i macro dal questionario perché è cambiato il
peso non ha cambiato idea sul pesce. Guardie in `tests/test_frequenze.py`.
