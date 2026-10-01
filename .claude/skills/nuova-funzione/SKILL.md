---
name: nuova-funzione
description: Aggiungere o cambiare una funzione di DietAI che attraversa backend e frontend — una rotta FastAPI, un servizio, la chiamata in api.js e la pagina che la usa. Usala per nuovi endpoint, nuove azioni su pasti/settimane/spesa/dispensa, nuove pagine, o modifiche a rotte esistenti.
---

# Una funzione dal database allo schermo

## Backend

1. **Rotta** nel router giusto in `backend/app/routers/` (auth, admin, diet, config,
   planning, recipes, chat, shopping, tracking). La logica sta in `services/`, il
   router valida, chiama e serializza.
2. **`def`, mai `async def`.** Il lavoro è sincrono (SQLAlchemy, chiamate al modello
   di minuti): una rotta async congela tutto il server. `tests/test_concurrency.py` lo
   fa rispettare.
3. **Ogni query su dati personali filtra per `user_id`.** Per i pasti passa da
   `_get_meal()` (risale pasto → giorno → settimana). Dimenticarlo è un bug di
   sicurezza: gli account sono più d'uno. Le rotte da amministratore dipendono da
   `get_current_admin` (403 da sole: nascondere il pulsante non è la difesa).
4. **Input con Pydantic** in `schemas.py`; **risposte come dict costruiti a mano**.
5. **Chi restituisce un'entità la restituisce intera**, anche dalle rotte di modifica,
   con lo stesso serializzatore della GET (`serialize_meal(full=True)`,
   `serialize_week`, `serialize_shopping_list`): il frontend ridisegna con la risposta
   del pulsante, e una risposta più povera spegne la pagina.
6. **Funzioni AI**: il client si costruisce solo con `get_client(db, user, role)` —
   chiave e modello sono dell'amministratore (`ai_owner`), non di chi chiama, e lì
   dentro c'è già il controllo di `ai_enabled`: costruirlo altrove lo salterebbe. Rate
   limit `@limiter.limit(AI_LIMIT)`; errori del provider con messaggi che non mandano
   l'ospite in schermate che non ha. Nuovo ruolo di modello → `ROLES` in
   `ai_client.py`, `_DEFAULTS` in `config.py`, `ROLE_LABELS` in `routers/config.py`.
7. **Chi tocca il piano** (ricette, pasti saltati/seguiti, giorni) chiama
   `rebuild_shopping_list(db, user_id)`: la spesa è una funzione del piano.
8. Le invarianti di dominio stanno in `CLAUDE.md` (in breve) e in `docs/` (il
   perché): pasti saltati che conservano la ricetta, `pantry_used` NULL e non `[]`,
   «lo faccio io» che conta nei macro, ricette condivise da staccare con
   `fork_recipe_for_meal`, settimane passate non create. Leggi il documento della
   parte che tocchi **prima** di scrivere.

## Frontend

1. Funzione in `frontend/src/api.js` — **mai `fetch` nei componenti**: lì c'è il
   refresh automatico sul 401.
2. Pagina nuova: file in `pages/`, `<Route>` in `App.jsx` dentro l'`ErrorBoundary`,
   voce nella stecca (`sidebar`) e, se serve sul telefono, in `pages/AltroPage.jsx`
   (le cinque schede in fondo non si allungano).
3. Errore di caricamento → `LoadError`, mai `return null`. Indietro → `useGoBack`.
4. Aspetto e telefono → skill `interfaccia`.

## Test

Un file `backend/tests/test_<cosa>.py` in italiano, con le fixture di `conftest.py`
(`client`, `guest_client`, `diet`) e `FakeModel` al posto del modello. Prova almeno:
il caso felice, che **l'altro account non vede/tocca** i dati (404/403), e che la
risposta della rotta di modifica ha la stessa forma della GET. La logica pura del
frontend va in `lib/` con il suo `.test.js` (vitest).

## Documentazione

Se la funzione introduce un concetto (una regola che "si dimentica scrivendo il
codice"), aggiungi la riga in `CLAUDE.md` (*Regole in breve*) e il paragrafo nel
`docs/` dell'area, con il perché e il test che lo guarda. Aggiorna la mappa di *Struttura* se aggiungi file.
