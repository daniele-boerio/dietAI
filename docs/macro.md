# I macro delle ricette

Da dove vengono calorie e macro di una ricetta, e perché non li scrive più il modello.
Il perché di ogni scelta: le regole in breve stanno in `CLAUDE.md`, qui c'è la storia
che le giustifica.

**I macro si calcolano, non si credono.** Fino a ottobre 2026 calorie e macro di ogni
ricetta erano quelli che il modello scriveva in `nutrition`, e nessuno li controllava.
Il prompt chiede il ±10% del target, ma quella è una somma fatta a memoria: "650 kcal"
sotto una ricetta che ne pesa 820 non è un caso raro — il modello finto della suite,
scritto a mano, dichiarava 700 kcal per un pranzo che ne pesava 496, e nessuno se n'era
accorto in mesi. Sul numero dichiarato si reggono totali del giorno, aderenza, grafici.
Ora la somma la fa Python (`services/macros.py`) con la composizione per 100 g che
l'anagrafica porta su ogni `Ingredient` (`kcal_100g`, `protein_100g`, `carbs_100g`,
`fat_100g`, più `grams_per_unit` per chi si conta a pezzi e `density` per chi si misura
a volume). È lo stesso principio del sorteggio delle cucine: quello che si può
calcolare lo calcola il codice.

**La composizione viene da tre parti.** Il catalogo (`utils/composition.py`, una voce
per ogni alimento di `utils/pricing.py`: `test_macro_calcolati` pretende le stesse
chiavi) la porta per i nomi noti, e il seed la riscrive a ogni avvio. I nomi che il
catalogo non conosce la ricevono dal modello (`ensure_composition`, prompt
`COMPOSITION_SYSTEM`): **una chiamata per generazione**, per tutti i nomi nuovi
insieme, e poi restano in anagrafica per sempre (`composition_source = "ai"`). Quella
corretta a mano (`"utente"`) il seed non la tocca, come il reparto e il prezzo. I
valori sono del prodotto **come si compra** — pasta e legumi secchi, carne cruda — e
il contesto lo chiede al modello (riga PESI di `CONTEXT_TEMPLATE`): con "pasta cotta"
il conto verrebbe la metà.

**Un conto che ne lascia fuori uno non si fa.** Se anche un solo ingrediente non ha
composizione, o non si sa pesare (tre "fette" di un alimento senza `grams_per_unit`),
la ricetta tiene i numeri dichiarati e lo dice: `Recipe.nutrition_source` è
`"calcolata"`, `"dichiarata"` o `"utente"`, e il foglio della ricetta lo scrive sotto i
macro. Un totale che ne tiene fuori uno è peggio di un totale dichiarato, perché
sembra vero. Fanno eccezione le unità che non pesano niente per la dieta (`q.b.`,
`pizzichi`), contate zero.

**Fuori dal ±10% si ritoccano le grammature, sulle leve.** `fit_to_target` lavora sul
dizionario del modello prima che la ricetta nasca (così il gemello si cerca sulle
quantità vere). Si muovono solo le **leve**: la riga che porta più proteine, quella che
porta più carboidrati e quella che porta più grassi — il pollo, la pasta, l'olio. Tre
leve per tre macro sono un sistema 3×3 e lo si risolve; se due macro hanno la stessa
leva (la pasta in un piatto senza carne) si risolve ai minimi quadrati. Le calorie
tornano da sé, perché sono fatte dei tre macro; se un fattore è finito al limite, le
stesse leve si allungano insieme di quello che manca. Le altre righe restano come le ha
scritte il modello: le verdure e il limone non sono lì per i numeri, e scalarle — era
il primo tentativo — faceva salire le proteine con le zucchine.

Tre limiti, ognuno da un errore. Una ricetta già dentro il ±10% (e con le proteine
entro 5 g) **non si tocca**: cambiarle le grammature per niente. Nessuna riga si allunga
oltre 2,5 volte o sotto 0,4 (4 volte per le righe sotto i 20 g: un cucchiaino d'olio che
diventa un cucchiaio e mezzo è lo stesso piatto, la pasta quadruplicata no) — oltre, il
piatto è un altro, ed è meglio lasciarlo un po' fuori target e dire quanto. Le righe a
pezzi non si muovono (2 uova non diventano 2,7). E le quantità nuove si arrotondano
come le scriverebbe una persona: grammi a 5 sopra i 100, cucchiai al mezzo.

**Le ricette scritte a mano non passano da qui.** I numeri li ha scritti l'utente, come
nell'editor della dieta: il calcolo difende da una somma sbagliata del modello, non
discute quelle di chi la ricetta l'ha pesata.

**La suite gira coi macro dichiarati.** I modelli finti scrivono numeri tondi che con
le loro grammature non tornano; ricalcolarli cambierebbe ogni totale e ritoccare le
grammature ogni conto della dispensa. `macro_dichiarati` in `conftest.py` spegne
`macros.ATTIVO`, e `test_macro_calcolati.py` lo riaccende. La stessa suite misura la
tabella: per ogni voce kcal ≈ 4·P + 4·C + 9·G (tranne alcol, aceti e spezie secche,
dove alcol, acido acetico e fibra non stanno nei tre macro), che è la guardia contro un
numero scritto male.

**Il resto dell'etichetta si conta allo stesso modo.** Calorie e tre macro bastavano
alla dieta, non a dire cosa si è mangiato: healthAI (vedi `docs/healthai.md`) vuole
anche fibre, zuccheri, grassi saturi, alcol (grammi di etanolo, non della bevanda) e
caffeina. Arrivano per 100 g sull'anagrafica (`fiber_100g` e compagni: il catalogo li
porta in `utils/composition.DETAILS`, `ALCOHOL`, `CAFFEINE_MG`, i nomi nuovi li
ricevono dal modello insieme ai macro) e per porzione sulla ricetta (`Recipe.fiber_g`
e compagni), con le regole dei macro: calcolati dagli ingredienti, dichiarati dal
modello o dall'utente dove il conto non si chiude. Con due differenze. Si contano
**valore per valore**: un ingrediente senza fibre lascia aperte le fibre della
ricetta, non i suoi zuccheri — perdere tutto per un valore che manca vorrebbe dire non
avere quasi mai niente, perché i nomi imparati dal modello prima che glieli si
chiedesse non li hanno. E **NULL non è zero**: zero = non ce n'è (il catalogo è stato
guardato voce per voce, e il vino è l'unico che porta alcol); NULL = non si sa, e a
healthAI arriva come «non so», non come «niente caffè». Zuccheri e saturi sono una
parte di carboidrati e grassi e non li superano mai (`coherent_details` li porta al
tetto, `test_macro_calcolati` lo pretende dal catalogo); le fibre sì, perché i
carboidrati delle tabelle CREA sono quelli disponibili, senza fibra — sui porcini
1 g di carboidrati, 2,5 di fibre. Non entrano nelle calorie né nel ritocco delle
grammature. Un nome imparato prima ha i macro e nessuno degli altri valori: alla prima
generazione che lo usa il modello li completa (`missing_composition` lo considera
incompleto solo se non ne ha **nessuno**, così una risposta parziale non si richiede a
ogni generazione), e i macro che aveva restano quelli. La sostituzione di un
ingrediente ora ricalcola anche i macro, come la chat: prima teneva quelli che il
modello scriveva in `updated_nutrition`, sbagliando la somma come ogni volta.

**L'archivio vecchio si ricalcola a mano.** Le ricette di prima hanno
`nutrition_source` NULL e i numeri dichiarati. `python -m app.recompute_macros` li
rifà dagli ingredienti senza toccare le grammature (quelle ricette sono già state
comprate e mangiate); senza `--yes` stampa solo quanto cambierebbe. Rifà anche gli
altri valori; con `--ai --yes` prima fa completare al modello (una chiamata ogni 40
nomi, chiave e modello dell'amministratore) quelli che mancano all'anagrafica. Dopo il
deploy della migrazione 0030: il seed riempie il catalogo da solo, poi
`python -m app.recompute_macros --ai --yes` per l'archivio. Cambia anche i
totali delle settimane passate e l'aderenza: è voluto, dicono il vero.

**E quelle già in programma si ritoccano a mano.** `python -m app.refit_macros` (anteprima senza `--yes`) applica `fit_to_target` alle ricette da oggi in avanti non segnate né saltate (`services/refit.py`): il passato non si riscrive, una ricetta usata anche fuori dal gruppo si copia prima di toccarla, quelle scritte a mano e quelle con ingredienti senza composizione si saltano, e quelle che nemmeno ritoccando tornano nel target si elencano da rigenerare. Guardia in `tests/test_refit.py`.

**Una fetta non è il pezzo intero** (`grams_of` in `services/macros.py`). Fette, spicchi
e foglie diventavano «1 unità» e si pesavano con `grams_per_unit`, cioè col pezzo
intero: «2 fette di mozzarella» erano 250 g, «3 fette di melanzana» 900 g, e il ritocco
correggeva le altre righe su numeri falsi. Ora hanno un peso tipico per famiglia di
alimenti (`_PEZZI_DI_PEZZO`); dove non c'è, il conto non si chiude e restano i macro
dichiarati, come per ogni ingrediente che non si sa contare. Allo stesso modo un
cucchiaio di polvere non pesa come uno d'acqua (`_CUCCHIAIO_DI`: parmigiano 6 g,
farina 9 g, zucchero 12 g). Guardia `test_fette_spicchi_e_cucchiai_pesano_il_giusto`.

**Una composizione stimata dal modello deve tornare** (`composizione_plausibile`). Gli
ingredienti fuori catalogo imparano la composizione da una stima del modello
(`composition_source="ai"`), e finisce nell'anagrafica condivisa. Prima si scartavano
solo negativi e kcal oltre 900; ora valgono gli stessi controlli che il catalogo passa
nei test: proteine + carboidrati + grassi non oltre 100 g, e kcal entro il 25% (almeno
15) da 4·P + 4·C + 9·G + 7·alcol. Una stima che non torna lascia l'ingrediente senza
composizione, e le ricette che lo usano tengono i macro dichiarati.
