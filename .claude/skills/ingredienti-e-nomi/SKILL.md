---
name: ingredienti-e-nomi
description: Lavorare sull'anagrafica ingredienti di DietAI — catalogo prezzi e reparti (utils/pricing.py), normalizzazione dei nomi (services/ingredients.py), accorpamenti, doppioni in lista della spesa o in dispensa, reparti sbagliati. Usala quando un ingrediente compare due volte, finisce nel reparto sbagliato, non ha prezzo, o quando si aggiunge un alimento al catalogo o una regola di accorpamento.
---

# Ingredienti, nomi e catalogo

`Ingredient` è un dizionario condiviso da tutti gli account (nome, reparto, prezzo al
kg/l/unità), non un dato personale. Ogni nome che entra passa da
`services/ingredients.normalize_name`; chi ha una sessione in mano passa sempre
`load_rules(db)` (le regole aggiunte dalle Impostazioni).

## Prima di cambiare qualcosa, guarda cosa succede oggi

```bash
cd backend && .venv/Scripts/python.exe -c "
from app.services.ingredients import normalize_name
from app.utils.pricing import guess_category, catalog_entry
for n in ['salsa di ostriche', 'Peperoni rossi', 'penne integrali']:
    k = normalize_name(n); print(repr(n), '->', repr(k), guess_category(k), catalog_entry(k))
"
```

Molti "bug di accorpamento" non sono nella normalizzazione ma nel prompt (il modello
scrive un nome diverso o sostituisce l'alimento): verifica prima di toccare le regole.

## Aggiungere un alimento al catalogo (`utils/pricing.py`)

- Formato: `"nome": ("reparto", prezzo, "kg" | "l" | "unità")`; reparti validi in
  `services/shopping.CATEGORY_ORDER`.
- Il nome va scritto **come lo produce `normalize_name`**, o diventa una riga che
  nessuna ricetta userà mai, ricreata dal seed a ogni avvio. Occhio all'elisione
  automatica: "di" davanti a vocale diventa "d'" (`salsa d'ostriche`,
  `olio extravergine d'oliva`).
- `tests/test_normalizzazione.py` rende ogni voce del catalogo e pretende che esca
  identica e che due voci non finiscano sulla stessa riga: fallo girare sempre.
- Un nome di una parola genera da solo le forme singolare/plurale (`_catalog_forms`):
  se il test sulle forme fallisce, c'è una collisione col nome di un altro alimento.
- Il catalogo serve anche a correggere `guess_category`, che lavora a parole chiave in
  ordine e sbaglia sui composti ("salsa di pesce" → pesce, "pasta di curry" →
  cereali, "latte di cocco" → latticini).
- In produzione il seed gira a ogni avvio del container; in locale `python -m app.seed`.
  Il seed non tocca reparto e prezzo corretti a mano (`category_by_user`,
  `price_by_user`).

## Accorpare due nomi

Prima chiediti se sono **lo stesso alimento** per la dieta e per la spesa. La linea:
via com'è messo (conservazione, taglio, calibro, marca, glosse fra parentesi), resta
cos'è (integrale, magro, light, al naturale, sott'olio — cambiano i macro).

- **Una regola d'uso** (un formato di pasta nuovo, un sinonimo): non serve codice.
  Impostazioni → Nomi e accorpamenti (admin), che mostra l'anteprima e riallinea.
- **Una regola di serie**: nel codice (`_PASTA_NAMES`, `_DA_GRATTUGIA`, `_VARIANTI`,
  `_NOISE_GROUPS`...). Le unificazioni confrontano il **nome intero**; le varianti di
  scrittura la **parola**. Se il nome fabbricato è nuovo, aggiungilo al catalogo; se
  ne inghiotte altri, toglili dal catalogo.
- **Unire è un danno che si disfa a mano**: la fusione cancella la riga e somma le
  scorte in dispensa. Riso, cous cous, farro, orzo dentro la pasta sono già successi
  (riparati con `app.repair_cereals`). Nel dubbio non unire.
- Cambiata una regola di serie, le righe già in tabella si riallineano con
  `python -m app.merge_ingredients` (in produzione, dal container): anteprima prima.

## Chiusura

`test_normalizzazione.py`, `test_regole_normalizzazione.py`, `test_reparti.py`,
`test_dispensa.py`; aggiorna in `CLAUDE.md` gli elenchi citati se cambi una regola di
serie.
