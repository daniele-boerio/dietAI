# Andamento e aderenza

Come si legge com'è andata: calendario dell'anno e grafico della settimana. Il perché di ogni scelta: le regole in breve stanno in
`CLAUDE.md`, qui c'è la storia che le giustifica.

**L'aderenza dell'anno è un calendario a colpo d'occhio.** `GET /api/tracking/year`
(`year_adherence`) classifica ogni giorno da `PlannedMeal.is_followed`: tutti "sì" →
`full`, tutti "no" → `missed`, misto → `partial`; un giorno senza nessun pasto tracciato
resta **fuori** (non è un fallimento, è un buco di dati, e contarlo punirebbe chi non
annota). È la stessa lettura del riepilogo settimanale (`entry["is_followed"]`) estesa a
tre stati. Lo `score_pct` pesa full=1, partial=0.5, missed=0 sui soli giorni tracciati.
Il frontend (`YearHeatmap`, scheda "Anno" in Andamento) lo disegna come griglia
settimane×giorni riusando le tinte del tracking (`--success/--warning/--danger`).

**Nel grafico della settimana il colore dice l'aderenza, non lo scarto dal target.**
Una barra per giorno: l'altezza sono le calorie in programma, il colore è **verde se
il giorno è stato seguito, rosso se no, grigio se non è ancora arrivato** (o se la
giornata è saltata). Prima erano due barre — quella grigia del target dietro, quella
colorata da `compliance_color` davanti — e il colore diceva quanto il *piano* si
scostava dalla dieta: su un giorno che non avevi ancora segnato si accendeva di giallo
come se fosse andato storto qualcosa, mentre la domanda che ci si fa guardando quel
grafico è un'altra. Lo scarto dal target resta scritto in chiaro, in lettere, nella
lista «Giorno per giorno» a fianco e nelle tre piastrelle sopra. `compliance_color`
resta in uso per i pallini di quella lista e per il riepilogo settimanale.

Un conto da tenere presente: un giorno **passato e mai segnato** finisce rosso, perché
per l'app quella giornata una risposta non ce l'ha e non c'è modo di distinguerla da un
«no». È l'opposto della regola del calendario dell'anno, dove un giorno non tracciato
resta fuori — lì il numero è una media e contarlo falserebbe il conto, qui è una barra
in un grafico di sette e toglierla lascerebbe un buco nella settimana.
