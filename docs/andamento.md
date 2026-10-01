# Andamento e aderenza

Come si legge com'è andata: calendario dell'anno e grafico della settimana. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**Il peso è un film, e il ricalcolo si propone, non si fa.** Il peso del questionario
era una fotografia: quella del giorno in cui lo si era compilato. `WeightEntry` (una
pesata per giorno: ripesarsi lo stesso giorno corregge, non aggiunge) dà lo storico,
e la scheda «Peso» di Andamento lo disegna. Il questionario stesso segna una pesata,
così lo storico parte da lì.

I target di una dieta da questionario dipendono dal peso (Mifflin-St Jeor, proteine
per chilo): sei chili dopo sono i target di un'altra persona. `services/weight.history`
confronta l'ultima pesata col peso del profilo e, oltre `max(2 kg, 3%)` — sotto, la
differenza sui target è di poche decine di kcal, meno dello scarto fra due pesate a ore
diverse —, propone il ricalcolo. Il pulsante porta alla dieta col questionario già
aperto e il peso nuovo dentro (`state.ricalcolaConPeso`, consumato subito come quello
della dialog di generazione). L'app non ricalcola da sola: cambierebbe la dieta sotto i
piedi dell'utente. E per la dieta di un nutrizionista non propone niente: i suoi numeri
non vengono da una formula che l'app conosce.

Il grafico è una linea sola, quindi senza legenda: asse x sul tempo vero (le pesate non
sono equidistanti, e a passo fisso il grafico mentirebbe sulla velocità), asse y che
non parte da zero (su 70 kg una variazione di 2 è tutto quello che c'è da vedere), il
peso dei target come riga tratteggiata. L'elenco delle pesate a fianco è la sua vista
tabellare. Guardie in `tests/test_peso.py`.

**«Ho mangiato altro» dice anche cosa.** Un pasto saltato era un buco nei dati: si
sapeva che il piano non era stato seguito, non cosa si era mangiato al suo posto. Sul
pasto segnato «ho mangiato altro» ora c'è un campo («una pizza», «panino al bar») e
`PUT /api/planning/meals/{id}/eaten` lo fa stimare al modello (ruolo `chat`, prompt
`EATEN_ESTIMATE_SYSTEM`, porzioni tipiche italiane, mai una domanda di chiarimento): il
testo resta in `deviation_notes`, la stima in `PlannedMeal.eaten_nutrition`. Vale solo
lì — su un pasto seguito si è mangiato il piatto in programma, su uno non segnato non si
sa — e cambiare risposta la cancella, perché non descrive più niente.

L'andamento ne ricava **quanto si è mangiato davvero** (`eaten_calories` per giorno):
il piatto per i pasti seguiti, la stima per quelli sostituiti. Ma lo dice solo dei
giorni di cui si sa tutto (`eaten_complete`), e la media della settimana conta solo
quelli: un totale fatto di metà pasti non è il totale del giorno, e uno zero al posto
di un pasto non segnato sembrerebbe un digiuno. È la stessa regola del calendario
dell'anno, dove un giorno non tracciato resta fuori. Guardie in
`tests/test_mangiato_altro.py`.

**Il promemoria serale chiude il buco dei giorni mai segnati.** Un giorno passato e mai
segnato finisce rosso nel grafico della settimana, perché per l'app non c'è modo di
distinguerlo da un «no» — e quasi sempre non è un giorno andato male, è un giorno in
cui ci si è dimenticati. Da Impostazioni → Preferenze si sceglie un'ora; a quell'ora
(italiana: `push.FUSO`, perché il container gira in UTC e «21:00» arriverebbe alle 23)
arriva una notifica push **solo se oggi c'è ancora qualcosa da segnare**: una notifica
che non chiede niente insegna a ignorare le notifiche. Una volta al giorno
(`UserPreferences.last_reminder_on`, segnato anche quando non si manda, così il giro
non ricontrolla la stessa persona ogni minuto fino a mezzanotte); spostare l'ora lo
azzera, o spostare il promemoria a più tardi lo perderebbe per oggi.

Il giro lo fa un thread del backend, ogni minuto (`push.start_scheduler`, avviato
all'avvio dell'app), come le settimane si archiviano senza scheduler esterno: il
backend gira in un processo solo, e il thread vive con lui. Se il processo si riavvia
nel minuto del promemoria lo si perde: è un promemoria, non una scadenza. I test lo
spengono con `DIETAI_SCHEDULER=0`.

Le chiavi VAPID che firmano le notifiche si **ricavano da `SECRET_KEY`** se
`VAPID_PRIVATE_KEY` non c'è: niente da configurare su Coolify, e restano le stesse a
ogni riavvio — chiavi nuove renderebbero inutili tutte le iscrizioni dei telefoni. Ogni
dispositivo è una `PushSubscription` (l'`endpoint` è unico: lo stesso telefono con un
altro account loggato passa a quell'account); quelle che il servizio di push dichiara
morte (404/410) si cancellano al primo invio. Su iPhone le notifiche esistono solo per
l'app installata sulla schermata Home, e la pagina lo dice invece di mostrare un
pulsante che non funziona. Guardie in `tests/test_promemoria.py`, compreso il giro vero
di cifratura e firma fino alla richiesta HTTP esclusa.
