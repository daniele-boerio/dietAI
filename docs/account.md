# Account, amministratore e accesso

Chi paga la chiave, chi crea gli account, come si sospende e come si rientra. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

**Gli account sono più d'uno, ma la API key la mette una persona sola.**
`User.is_admin` è chi paga: l'unico che vede la schermata della chiave
(`PUT /api/auth/api-key` è `get_current_admin`), l'unico che sceglie i modelli
(`/api/config/ai/models`, GET e PUT) e l'unico che crea account
(`/api/admin/*`). Gli altri **generano con la sua chiave e con i suoi modelli**:
`ai_owner(db, user)` restituisce l'admin per chi non lo è, e `get_client` costruisce
il client su quello — chiave, modello e conto sono suoi. Nascondere la scheda nel
frontend non basta e non è la difesa: le rotte rispondono 403 da sole
(`tests/test_due_account.py`).

Due conseguenze che si dimenticano scrivendo il codice. La prima: `has_api_key` in
`/api/auth/me` dice **la chiave con cui quell'utente genererà**, non "ne possiede
una" — e il gate dell'onboarding pesa la chiave solo per chi la gestisce
(`can_manage_api_key`), altrimenti l'ospite resterebbe chiuso nel percorso guidato
per sempre, con tutti i passi fatti. La seconda: i messaggi d'errore non possono
mandare in "Impostazioni → Account" chi quella schermata non ce l'ha.

Il flag arriva da tre parti, in ordine di quanto è probabile: la migrazione `0015` lo
dà all'utente più vecchio, il seed lo dà a `SEED_USER_EMAIL` **quando in tabella non c'è
nessun amministratore** (gira a ogni avvio del container, quindi si ripara da sé al
primo deploy), e `python -m app.make_admin [--email ...]` lo alza a mano. Serve un
comando perché da qui non si esce dalla UI: le rotte che rimetterebbero il flag sono
proprio quelle riservate all'amministratore, e un database senza admin è chiuso a
chiave dall'interno.

Due interruttori, che sono due problemi diversi: `is_active` toglie l'accesso
(login 403, `get_current_user_id` 403, sessioni revocate e `token_version` alzata,
perché sospendere deve avere effetto adesso e non fra mezz'ora) e `ai_enabled` spegne
solo le funzioni AI — l'app resta in piedi, i dati non si toccano, ed è il freno sulla
bolletta di chi mette la chiave. Cancellare un account porta via tutto (FK in
CASCADE): è proprio il motivo per cui esiste la sospensione. L'amministratore non si
sospende, non si cancella e non si resetta da solo (`_target` in `routers/admin.py`):
da lì si tornerebbe soltanto con `python -m app.reset_password` dal container. Un
**altro** amministratore il pannello non lo tocca affatto, e per quello c'è
`python -m app.delete_user --email ...`: senza `--yes` stampa solo l'inventario di cosa
sparirebbe, e si rifiuta di lasciare l'app senza amministratori o di cancellare
l'utente di `SEED_USER_EMAIL`, che il seed ricreerebbe al riavvio successivo.

Quello che **non** è per-utente è l'anagrafica ingredienti (`Ingredient`): è un
dizionario di nomi, reparti e prezzi al kg, non un dato personale. Se un utente
corregge il prezzo del pane, il pane costa quello per tutti.

**Niente email, in tutta l'app.** Nessun SMTP, nessuna registrazione, nessun recupero
password via link: l'unico endpoint pubblico è `/auth/login`. L'amministratore nasce
dal seed; gli altri li crea lui da Impostazioni → Utenti, e la password iniziale gliela
dice a voce (per questo il campo è in chiaro: bisogna poterla leggere per dettarla).
Chi perde la password se la fa rimettere dall'amministratore; se a perderla è
l'amministratore c'è `python -m app.reset_password` dal container, ed è l'unica via.
Cancellare la riga utente per farla ricreare dal seed **distrugge tutti i dati** (FK in
CASCADE) — e il seed **non** ricrea gli altri account: gira a ogni avvio del container
e resusciterebbe ogni volta chi è stato cancellato apposta.

**Chi paga vede quanto.** L'amministratore mette la chiave e paga per tutti, e fin qui
aveva solo l'interruttore `ai_enabled` per frenare la bolletta, senza un numero per
decidere quando usarlo. Ora ogni chiamata lascia una riga (`AIUsage`): token in
entrata e in uscita e il costo in dollari, e Impostazioni → Utenti mostra il conto per
account su 7, 30 o 90 giorni (`GET /api/admin/usage`, solo amministratore). La riga va
a **chi ha premuto il pulsante**, non a chi paga — chi paga è sempre lui, e la domanda
a cui il pannello risponde è un'altra.

Il costo lo dichiara OpenRouter nella risposta (`usage.cost`, fra i campi che l'SDK non
conosce); in streaming serve `stream_options={"include_usage": True}`, perché l'uso
arriva nell'ultimo pezzo senza `choices` — e la generazione della settimana, la più
cara, va proprio in streaming. Dove il costo non c'è (il backend Anthropic) si stima
dal listino del catalogo modelli **solo se è già in memoria**: il registro non deve mai
essere il motivo di una richiesta di rete nel mezzo di una generazione. Le chiamate
senza costo noto si dichiarano nel pannello invece di sparire dal totale.

Due dettagli. L'uso si registra nel `finally` di `_complete`: una risposta finita a
vuoto per «length» i token li ha consumati tutti, ed è proprio quella da contare. E si
scrive con una sessione propria (`usage.recorder`), perché chi chiama può avere in mano
mezza settimana non committata; se la scrittura fallisce si logga e basta. Guardie in
`tests/test_costo_ai.py`.
