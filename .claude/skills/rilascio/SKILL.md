---
name: rilascio
description: Committare, pubblicare e mantenere DietAI in produzione su Coolify — messaggi di commit, push su main, deploy che fallisce, variabili d'ambiente, comandi di manutenzione nel container (seed, reset_password, make_admin, delete_user, merge_ingredients, merge_recipes). Usala quando si chiede di fare il commit, "mandalo in produzione", o quando un deploy o un account in produzione hanno un problema.
---

# Commit, deploy e manutenzione

## Commit

- Committa solo quando l'utente lo chiede. Si lavora su `main` (push → deploy).
- Formato dei messaggi, come nella storia del repo: `feat(scope): descrizione in
  italiano` (anche `fix`, `refactor`, `docs`, `test`). Scope = area: `planner`,
  `preferences`, `shopping`, `pantry`, `chat`, `diet`, `admin`, `ui`...
- Corpo breve in italiano: cosa cambia per l'utente e perché.
- Prima del commit: test mirati verdi, e la suite completa se hai toccato modelli o
  servizi condivisi (skill `avvia-dietai`). Se un test fallisce già su `HEAD`, dillo
  nel resoconto invece di tacerlo.
- Mai nel commit: `backend/.env`, file `*.db` lasciati dai test o da prove a mano
  (`backend/mig_check_tmp.db`), `.claude/settings.local.json`.

## Deploy (Coolify)

Push su `main` → Coolify ricostruisce via `docker-compose.yml` (frontend Nginx +
backend; il Postgres è una risorsa Coolify separata). Il backend all'avvio fa
`alembic upgrade head`, poi `python -m app.seed` (idempotente, non blocca l'avvio),
poi uvicorn.

- Variabili: `DB_*`, `SECRET_KEY`, `ENCRYPTION_KEY`, `SEED_USER_EMAIL`,
  `SEED_USER_PASSWORD`, `COOKIE_SECURE=true`, più `AI_*` per provider e modelli.
- **`ENCRYPTION_KEY` non si cambia mai** dopo il primo avvio: la API key salvata
  diventerebbe indecifrabile.
- Deploy che fallisce con `Failed to read the Docker Compose file from the
  repository`: non è il repository. L'app deve usare la **sorgente GitHub autenticata**
  di Coolify, non la git source pubblica (vedi memoria `coolify-git-source`).
- Un deploy con migrazione: la migrazione deve reggere i dati veri (skill
  `migrazione-db`); se fallisce, il container non parte.

## Comandi nel container del backend

Si lanciano dal terminale del container in Coolify, `python -m app.<comando>`.
Quelli che cancellano o fondono mostrano l'anteprima e vogliono `--yes`.

| Comando | Quando |
|---|---|
| `seed` | riallinea catalogo ingredienti; ricrea l'admin solo se non ce n'è nessuno |
| `reset_password '...'` | l'amministratore ha perso la password (unica via) |
| `make_admin [--email ...]` | nessun amministratore in tabella |
| `delete_user --email ... [--yes]` | cancellare un **altro amministratore** (gli utenti normali si cancellano da Impostazioni → Utenti) |
| `merge_ingredients` | dopo aver cambiato una regola di normalizzazione nel codice |
| `merge_recipes [--yes]` | ricettario con doppioni di prima delle ricette condivise |
| `recompute_macros [--yes]` | dopo la migrazione 0021: rifà i macro delle ricette vecchie dagli ingredienti |
| `refit_macros [--yes] [--email ...]` | ritocca le grammature delle ricette da oggi in avanti fuori dal ±10%, senza chiamare il modello |
| `repair_cereals` | una fusione di ingredienti ha unito troppo (cereali finiti in "pasta") |

Non cancellare mai la riga di un utente "per farla ricreare dal seed": le FK sono in
CASCADE e si perde tutto, e il seed non ricrea gli account non amministratori.
