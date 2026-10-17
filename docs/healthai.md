# healthAI: i pasti consumati

Come i pasti che l'amministratore segna come mangiati arrivano a healthAI, il suo
server dei dati di salute (Apple Salute e Apple Watch), dove Claude li incrocia con
allenamenti, sonno e recupero. DietAI non scrive in Apple Salute: questo è l'unico
canale. Il perché di ogni scelta: le regole in breve stanno in `CLAUDE.md`, qui c'è
la storia che le giustifica.

**Cosa si manda.** Un pasto consumato è quello che l'andamento conta come «mangiato
davvero» (`tracking.weekly_tracking`), letto allo stesso modo: «l'ho seguito» → il
piatto in programma, coi numeri della ricetta; «l'ho seguito» su un pasto «lo faccio
io» → i target del pasto, che è come l'andamento lo conta; «ho mangiato altro» con la
stima → la stima, col testo dell'utente come titolo. Tutto il resto non si manda: un
pasto saltato senza dire cosa non è un pasto a zero, è un buco di dati, e a healthAI
arriverebbe come un digiuno. I valori sono per la porzione di una persona:
`MealSlot.servings` moltiplica la spesa, non quello che si mette nel piatto. La data
è quella del giorno del piano (`DayPlan.date`), che è già una data di casa; il giro si
ferma a oggi, ora italiana — un pasto di domani segnato per sbaglio non è stato
mangiato.

**Le ricette scritte a mano partono coi valori calcolati.** In DietAI una ricetta
scritta dall'utente tiene i suoi numeri (`docs/macro.md`): il calcolo difende da una
somma sbagliata del modello, non discute quelle di chi la ricetta l'ha pesata. Ma a
healthAI, che incrocia quello che si è mangiato con sonno e allenamenti, l'utente
vuole il conto fatto sugli ingredienti, come per le ricette generate — spesso è una
ricetta messa in un pasto «lo faccio io» solo perché entri nella spesa, coi macro
scritti a occhio. Quindi `_valori_ricetta` rifà il conto **solo per il payload**: la
ricetta in DietAI non si tocca, né nella pagina né nell'andamento. Un ingrediente
senza composizione la riceve dal modello (`ensure_composition`, chiave e modello
dell'amministratore, una volta per processo: un nome che il modello non sa non si
richiede a ogni giro), e resta in anagrafica come dopo una generazione. Se il conto
non si chiude lo stesso partono i numeri dell'utente; un valore che il conto lascia
aperto prende il suo. Le ricette generate non passano da qui: i loro numeri sono già
quelli calcolati.

**Solo l'amministratore.** healthAI è suo: i pasti di un ospite finirebbero nei dati
di salute di un altro. Guardia in `test_i_pasti_dell_ospite_non_partono`.

**Non è una coda di azioni, è un confronto di stati.** La prima idea era agganciare un
POST a «l'ho seguito» e una DELETE a «desegnato». Ma le strade che cambiano cosa si è
mangiato sono una dozzina — seguito, «ho mangiato altro», la sua stima, la chat che
riscrive la ricetta, la sostituzione di un ingrediente, il cestino, la rigenerazione,
il cambio di dieta che sposta le caselle, `recompute_macros` — e la prima rotta nuova
che se ne dimenticasse lascerebbe su healthAI un pasto che non esiste più. Una coda,
poi, ha il problema dell'ordine: un POST fallito e ritentato dopo una DELETE fa
ricomparire il pasto. Invece ogni minuto `services/healthai.sync` guarda cosa dice
**adesso** ogni pasto degli ultimi `HEALTHAI_DAYS` giorni (90), ne fa l'impronta e la
confronta con quella di quello che healthAI ha (`HealthSync.sent_hash`): diversa →
POST (healthAI fa upsert su `external_meal_id`, quindi è anche la modifica); pasto non
più consumato, o cancellato, ma presente lì → DELETE. L'ordine è giusto per
costruzione: il POST vecchio non esiste più, esiste solo lo stato di adesso. Nessuna
rotta deve ricordarsi di niente. `HealthSync.meal_id` non è una FK apposta: la riga
deve sopravvivere al pasto cancellato, perché è lei che ricorda che su healthAI c'è da
togliere. Un pasto uscito dalla finestra dei 90 giorni non si tocca più, né per
mandarlo né per toglierlo.

**L'invio non fa mai fallire niente.** Gira nel suo thread (`start_scheduler`, come
il promemoria serale, spento nei test e quando l'integrazione è spenta), con timeout di
10 secondi: segnare o desegnare un pasto riesce sempre, la sincronizzazione arriva al
giro dopo. I fallimenti si dividono in due. Passeggeri (rete, timeout, 5xx, 429): si
riprova dopo 1, 5, 30 minuti e poi ogni ora, per 24 ore; e il giro intero si mette in
pausa, perché con healthAI giù ogni pasto pagherebbe il suo timeout. Definitivi: 401
vuol dire token sbagliato, si scrive nel log e non si riprova fino al riavvio (che è
anche quando una variabile d'ambiente corretta arriva al container); 422 vuol dire un
payload che healthAI non accetta, cioè un bug nella stima o nel mapping — si scrive il
dettaglio e quel payload non si ritenta. Un fallimento definitivo si sblocca da sé
quando il pasto cambia, perché cambia l'impronta. Nei log solo l'id del pasto e la
risposta di healthAI: né il contenuto del pasto né il token.

**Configurazione.** `HEALTHAI_URL` e `HEALTHAI_TOKEN` (il Bearer di healthAI, lo
stesso di `/ingest`); se ne manca una l'integrazione è spenta, senza errori. Vanno
nelle variabili di Coolify e passano dal `docker-compose.yml`: senza la riga lì il
container non le vede. Sullo stesso server, se le due app sono sulla stessa rete
Docker basta il nome del servizio (`http://<servizio>:8000`), altrimenti l'URL
pubblico https.

**L'allineamento iniziale.** `python -m app.healthai_sync --yes` rimanda tutti i
pasti consumati degli ultimi 90 giorni (`--days` per cambiarli), anche quelli che
risulterebbero già inviati: serve al primo collegamento e dopo un periodo in cui
healthAI ha perso i dati. L'upsert non crea doppioni. Senza `--yes` conta soltanto.

**0 e null.** Fibre, zuccheri, saturi, alcol e caffeina viaggiano con la stessa
distinzione che hanno in DietAI (vedi `docs/macro.md`): `0` = stimato, non ce n'è;
`null` = non si sa. healthAI li legge in due modi diversi, e uno zero al posto di un
«non so» direbbe che quel giorno non si è bevuto caffè.

Guardie in `tests/test_healthai.py`: il payload, ogni transizione, l'ultima azione che
vince, le attese, il 401 e il 422 non ritentati, il token che non finisce nei log.

**Un pasto storto non ferma il giro, e un pasto senza calorie non parte.** Il giro
preparava tutti i payload della finestra in un colpo: una stima con «circa 400» al posto
di un numero faceva fallire `float()` e con lei l'intero giro, ogni minuto, e a healthAI
non arrivava più niente. Ora `desired_payloads` salta il pasto che non riesce a preparare
(lo dice nel log, con l'id) e lascia a healthAI quello che ha. Una stima senza calorie è
un buco, non un pasto a 0 kcal: `meal_payload` non la manda. E il giro committa prima di
ogni chiamata HTTP — niente transazione aperta mentre si aspetta healthAI, e un errore a
metà non fa perdere gli esiti già ottenuti.
