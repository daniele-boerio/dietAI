---
name: migrazione-db
description: Cambiare lo schema del database di DietAI con Alembic — nuova colonna, tabella, vincolo, backfill o conversione di dati. Usala ogni volta che si modifica backend/app/models.py o si scrive in backend/alembic/versions.
---

# Migrazioni del database

Lo schema lo gestisce **solo Alembic**: nessun `create_all` all'avvio (i test sì, su
SQLite, da `Base.metadata`). Quindi un modello cambiato senza migrazione passa i test e
rompe la produzione.

## Convenzioni del repo

- File numerati a mano: `backend/alembic/versions/00NN_nome_in_italiano.py`, con
  `revision = "00NN"` e `down_revision = "00NN-1"`. Guarda l'ultimo con
  `ls backend/alembic/versions | tail -1` e prosegui la numerazione — niente hash.
- Docstring in testa: cosa cambia **e perché**, come le altre (leggi `0020` per il
  tono). Se converti dati, spiega cosa diceva il vecchio valore.
- Le colonne JSON nel modello sono `JSONType` (JSON con variante JSONB su Postgres);
  nella migrazione si scrive `postgresql.JSONB(astext_type=sa.Text())`, come nelle
  altre.
- Le FK verso l'utente sono `ondelete="CASCADE"`: cancellare un account porta via tutto
  ed è voluto.
- `downgrade()` va scritto davvero.

## Procedura

1. Modifica `backend/app/models.py`.
2. Genera la bozza e **rileggila riga per riga** (DB locale su, vedi `avvia-dietai`):
   ```bash
   cd backend && .venv/Scripts/python.exe -m alembic revision --autogenerate -m "..."
   ```
   Poi rinomina il file e la revisione secondo la numerazione. L'autogenerate sbaglia
   spesso su JSONB, server_default e rinomine (le vede come drop + add: dati persi).
3. Backfill e conversioni nella stessa migrazione, **prima** del drop della colonna da
   cui si leggono. Se una conversione può cambiare forma ai dati già salvati, valuta se
   leggere entrambe le forme nel codice invece di migrare (è stato fatto per le cucine:
   `cuisines._as_shares` legge la lista vecchia e la mappa nuova).
4. `alembic upgrade head` in locale, poi `alembic downgrade -1` e di nuovo `upgrade head`.
5. Test: la suite completa (i modelli li usano tutti).
6. Se i dati vecchi vanno riallineati con logica Python complessa, fai uno script
   `python -m app.qualcosa` con anteprima di default e `--yes` per applicare (modello:
   `merge_recipes.py`, `delete_user.py`), e documenta in `CLAUDE.md` l'ordine rispetto
   alla migrazione.

## In produzione

Il container applica le migrazioni all'avvio, poi il seed. Una migrazione che fallisce
blocca il deploy: niente operazioni che dipendono da dati che potrebbero mancare senza
una guardia (`WHERE`, `COALESCE`).
