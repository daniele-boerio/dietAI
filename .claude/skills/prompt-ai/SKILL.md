---
name: prompt-ai
description: Cambiare come si comporta il modello in DietAI — prompt di generazione, rigenerazione, chat del pasto e della spesa, sostituzione, lettura della dieta, contesto utente, cucine. Usala ogni volta che si tocca services/prompts.py, utils/cuisines.py o build_context, o quando l'utente lamenta che l'AI "fa sempre X", "non rispetta Y", "sostituisce Z".
---

# Cambiare il comportamento dell'AI

## Dove sta cosa

- **Tutti i prompt** in `backend/app/services/prompts.py`. Mai un prompt scritto dentro
  un router o un servizio.
- La riga delle cucine e il vincolo sugli ingredienti in `backend/app/utils/cuisines.py`
  (`prompt_line`, `prompt_line_one`, `PER_GIORNO`, `INGREDIENTI_LOCALI`).
- Il contesto comune (dieta, dispensa, esclusi, regole libere, cucina, regola NOMI) lo
  compone `planner.build_context` su `CONTEXT_TEMPLATE`: generazione, rigenerazione e
  le due chat passano tutte da lì.

## La regola che si rompe più spesso: un vincolo, tutte le sue copie

Lo stesso vincolo è scritto in più prompt, e se ne cambi una copia sola il modello si
contraddice da una schermata all'altra. Prima di modificare, cerca la frase in tutto il
file e decidi copia per copia:

```bash
grep -n "supermercato\|±10%\|ESCLUSI\|NOMI\|stagionalità" backend/app/services/prompts.py backend/app/utils/cuisines.py
```

I prompt che condividono le regole: `WEEK_PLAN_SYSTEM`, `SINGLE_MEAL_SYSTEM`, la chat del
pasto (marcatore `[RECIPE_UPDATE]`), `SHOPPING_CHAT_SYSTEM` (`[RECIPES_UPDATE]`),
`SUBSTITUTE_SYSTEM`. Una differenza voluta va **dichiarata** (in `docs/` e in un
commento), es. la chat della spesa vuole il sostituto sullo scaffale perché l'utente è
in negozio.

## Trappole meccaniche

- I segnaposto si riempiono con `prompts.render(template, chiave=valore)`, **mai**
  `str.format()`: i prompt contengono JSON e format() muore sulle graffe.
  `tests/test_chat.py` rende tutti i template.
- In chat la ricetta va **dopo** il marcatore, mai nel messaggio; il messaggio è prosa.
  Se aggiungi istruzioni di formato, non indebolire quella regola né l'esempio di
  risposta corretta. `_needs_marker_retry` in `routers/chat.py` ritenta una volta.
- Cambia la forma del JSON atteso → aggiorna chi lo consuma: `planner.generate_week`,
  `recipes.create_recipe`, `RECIPE_JSON_SHAPE`, e i `FakeModel` dei test.
- Il sorteggio (cucine, quote) lo fa **Python**, non il modello: "alterna", "varia",
  "ogni tanto" scritti in un prompt sono auspici. Se serve una distribuzione, calcolala
  e scrivi l'assegnazione accanto al giorno (vedi `cuisines.draw`).
- Gli elenchi di esempi ("X sì, Y no") servono a tracciare un confine che il modello
  altrimenti giudica a sentimento: un esempio solo da una parte diventa una regola
  ("salsa di soia" unico condimento citato ⇒ tutte le salse diventano soia).
- Le parole in maiuscolo (NON, SOLO) pesano molto: un "usa SOLO" senza eccezioni
  dichiarate cancella tutte le eccezioni.

## Ingredienti nuovi che il prompt incoraggia

Se il prompt comincia a chiedere ingredienti per nome (salse, cereali, tagli), controlla
che arrivino bene in lista: `normalize_name` deve lasciarli distinti e
`guess_category` non deve mandarli nel reparto sbagliato. Se serve, aggiungili al
catalogo → skill `ingredienti-e-nomi`.

## Chiusura

1. Test mirati: `test_chat.py`, `test_chat_spesa.py`, `test_cucine.py`,
   `test_genera_su_richiesta.py`, più quelli della parte toccata.
2. Se cambia una regola dichiarata, aggiorna i testi che la spiegano all'utente
   (Impostazioni → Preferenze in `SettingsPage.jsx`, `OnboardingPage.jsx`) e il
   paragrafo di `docs/chat.md`, `docs/cucine.md` o `docs/generazione.md`, che racconta il **perché**: scrivi anche cosa non andava
   con la versione di prima.
3. Una guardia in un test che legga la frase o il comportamento nuovo: senza, il
   prossimo ritocco la toglie in silenzio.
