---
name: avvia-dietai
description: Avviare DietAI in locale (Postgres in Docker, FastAPI, Vite) e lanciare i test backend e frontend. Usala quando si chiede di far partire l'app, di vedere una modifica nel browser, di rifare lo schema o il seed, o di eseguire pytest/vitest — anche per richieste come "proviamolo", "fai girare i test", "apri l'app".
---

# Avviare DietAI e far girare i test

Ambiente: Windows, Git Bash. Python **3.12** obbligatorio (su 3.13+ `pydantic-core`
prova a compilare da Rust). Il `.env` sta in `backend/.env` e lo carica `config.py`:
non stampare mai i valori (ci sono `SECRET_KEY`, `ENCRYPTION_KEY`, la password del seed).

## L'app

Tre processi, ognuno in background (`run_in_background: true`), dalla radice del repo:

```bash
docker compose -f docker-compose.dev.yml up -d          # Postgres 16 su :5432
cd backend && .venv/Scripts/python.exe -m alembic upgrade head
cd backend && .venv/Scripts/python.exe -m app.seed       # idempotente: admin + catalogo
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev                               # http://localhost:3000
```

- Il frontend va aperto su **:3000**, mai su :8000: il proxy di Vite tiene tutto
  same-origin, ed è l'unico modo in cui i cookie `httpOnly` funzionano.
- Le credenziali di login sono `SEED_USER_EMAIL` / `SEED_USER_PASSWORD` del `.env`:
  chiedile all'utente invece di leggerle.
- Senza API key del provider le funzioni AI rispondono 400 con un messaggio chiaro: è
  il comportamento previsto, non un guasto.
- Se manca il venv: `cd backend && py -3.12 -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements-dev.txt`.

Per aspettare che un servizio sia su usa un `until` in background
(`until curl -sf localhost:8000/api/health ...; do sleep 1; done`), non `sleep`.

## I test

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q          # ~3 minuti, ~700 test
cd backend && .venv/Scripts/python.exe -m pytest tests/test_x.py -q # un file
cd frontend && npm test                                             # vitest, lib/*.test.js
```

- La suite completa supera i 2 minuti del timeout: lanciala con `run_in_background` e
  aspetta la notifica. **Non toccare l'albero di lavoro mentre gira** (niente
  `git stash`, niente edit): i test leggerebbero un codice a metà.
- Mentre lavori, fai girare prima i file mirati (vedi la mappa sotto), la suite
  completa una volta alla fine.
- Un test che fallisce: prima di attribuirlo alla tua modifica verifica se fallisce
  anche su `HEAD` pulito — a suite **ferma**, con `git stash` / `git stash pop`.
- I test girano su SQLite in memoria, con "oggi" fissato a lunedì (`oggi_e_lunedi` in
  `conftest.py`) e il modello sostituito: `monkeypatch.setattr(planner, "get_client",
  lambda db, user, role: FakeModel(user))`, con `FakeModel` in `tests/test_flow.py`.
  Fixture utili: `client` (admin già loggato), `guest_client` (secondo account),
  `diet` (dieta a tre pasti senza PDF).

## Quale test guarda cosa

| Tocchi | Fai girare |
|---|---|
| prompt, chat | `test_chat.py`, `test_chat_spesa.py`, `test_cucine.py`, `test_genera_su_richiesta.py` |
| generazione | `test_flow.py`, `test_genera_selezione.py`, `test_regenerate_week.py`, `test_diario_generazione.py`, `test_reasoning_budget.py` |
| spesa, dispensa | `test_dispensa.py`, `test_spesa_multisettimana.py`, `test_reparti.py` |
| nomi, catalogo | `test_normalizzazione.py`, `test_regole_normalizzazione.py`, `test_catalog.py` |
| pasti saltati/fissi | `test_pasti_saltati.py`, `test_giorni_saltati.py`, `test_pasti_fissi.py`, `test_elimina_pasto_tracciato.py` |
| account, admin | `test_due_account.py`, `test_delete_user.py`, `test_make_admin.py` |
| ricette condivise | `test_ricette_doppie.py`, `test_dettaglio_pasto.py` |
| dieta | `test_cambio_dieta.py`, `test_questionario.py` |
| una rotta qualsiasi | `test_concurrency.py` (le rotte devono essere `def`) |
