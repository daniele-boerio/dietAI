# Le chat e le regole libere

Chat del pasto, chat della spesa, marcatori e regole scritte dall'utente. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

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

**Le regole dell'utente sono testo libero, di proposito.** `UserPreferences.notes`
finisce in `CONTEXT_TEMPLATE` così com'è: il destinatario è un modello linguistico,
quindi trasformare "carne rossa al massimo due volte a settimana" in caselle
perderebbe sfumature senza guadagnare niente. Vale per generazione, rigenerazione e
chat, perché tutte e tre passano da `build_context`.
