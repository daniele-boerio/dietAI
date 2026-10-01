---
name: interfaccia
description: Disegnare o correggere l'interfaccia React di DietAI — pagine, componenti, CSS in index.css, versione telefono, tema scuro/chiaro, pulsanti, card dei pasti, stati vuoti. Usala per ogni modifica visiva o di layout nel frontend, anche piccola ("sposta il pulsante", "su iPhone si vede male").
---

# Interfaccia di DietAI

Testo UI **in italiano**. Un solo foglio, `frontend/src/index.css`, con custom
properties: niente CSS modules, niente Tailwind, niente librerie UI. Icone Lucide.
Le ragioni di ogni regola sono in `docs/interfaccia.md` (le convenzioni visive e i paragrafi
sulla home, il piano, la spesa): leggi quello della schermata che tocchi.

## Checklist

**Colori e tipi**
- App scura: fondo `#14130f`, accento lime. Nessuna superficie crema.
- `--accent` si **scrive** (testo, icone), `--accent-fill` si **riempie** (fondi con
  testo `--accent-contrast` sopra). `--accent-hover` scurisce in tutti e due i temi.
- Ogni colore nuovo è un token, definito anche per `data-theme="light"`.
- Tre caratteri: `--font-display` (Instrument Serif, solo peso 400: niente bold) per
  piatti e numeri grossi, `--font-body` per il testo, `--font-mono` per etichette e cifre.
- Terracotta per "ho mangiato altro"; `--danger` solo per le azioni distruttive.

**Pulsanti**
- Ogni variante ha un bordo da 1px, anche trasparente, o si disallinea.
- Chi chiama il modello si vede: `.btn-primary` o `.btn-ai` + icona `Sparkles`
  (eccezione: l'icona tonda della griglia, `RefreshCw`, che gira mentre lavora).
- Più azioni in uno stato vuoto → `.empty-actions` (in colonna, larghe uguali).

**Telefono (è il caso normale)**
- Altezze a schermo pieno in `dvh`, mai `100vh`.
- Ciò che è `fixed`/sticky somma `env(safe-area-inset-*)`.
- Niente che compaia solo `:hover`: correzioni nel blocco `@media (pointer: coarse)`,
  bersagli da 44px.
- Navigazione dalle cinque schede in fondo; non sul dettaglio del pasto.
- Strisce che scorrono di lato devono mostrare dove sei (meglio `flex-wrap`).
- Tabelle → una scheda per riga, ogni cella con la sua etichetta.
- `useDueColonne()`/`useTelefono()` solo quando cambia *cosa* è un componente; per il
  resto basta il CSS.

**Struttura**
- Due colonne con `.page-split` / `.page-main` / `.page-aside` (larghezza fissa via
  `--aside`), sotto i 1100px la colonna scende.
- Nella griglia settimanale ogni cella dichiara riga e colonna inline.
- Stato di una card detto **una volta**: anello (`box-shadow` inset) + parola nel piede.

## Verifica

Dopo la modifica guarda la pagina davvero (skill `avvia-dietai`, frontend su :3000)
a due larghezze: monitor (~1400px) e telefono (~390px), e se tocchi i colori anche col
tema chiaro. Il typecheck non dice niente di un layout.
