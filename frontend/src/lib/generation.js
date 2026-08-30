/**
 * Cosa c'è da generare in una settimana, e quanto ne resta scegliendo.
 *
 * Sta qui e non dentro la dialog perché è una conta che deve dare **lo stesso
 * risultato del server**: `generate_week` filtra le caselle esattamente con queste
 * condizioni, e il numero scritto sul pulsante ("Genera 9 pasti") è una promessa su
 * quanti pasti si stanno per pagare. Se le due parti si scostassero, la dialog
 * conterebbe caselle che poi nessuno genera — e nessuno se ne accorgerebbe, perché
 * la risposta arriva minuti dopo su una connessione che il proxy ha già chiuso.
 */

// Le stesse condizioni di `generate_week`, nello stesso ordine: giorno saltato,
// pasto rimandato altrove, pasto che prepara l'utente, pasto fisso (ricorrente o
// scritto a mano, che la generazione non tocca mai).
export const generabile = (day, meal) =>
  !day.is_skipped &&
  !meal.is_skipped &&
  !meal.self_managed &&
  !meal.is_recurring &&
  meal.source !== 'user_custom';

// La data di oggi nel fuso locale: `toISOString()` passa da UTC e a fine giornata
// direbbe domani, cioè marcherebbe come passato un giorno che passato non è.
export function oggiIso(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(
    now.getDate()
  ).padStart(2, '0')}`;
}

/**
 * Le caselle generabili della settimana, con quante ne tocca a ogni giorno e a ogni
 * pasto. Con `rifaiTutto` si contano anche quelle che una ricetta ce l'hanno già.
 *
 * Giorni e pasti escono **tutti**, anche quelli senza niente da fare: la dialog li
 * mostra spenti invece di farli sparire, o una colazione che nessuno genera
 * sembrerebbe un pasto perso dalla dieta.
 */
export function daGenerare(week, { rifaiTutto = false, oggi = oggiIso() } = {}) {
  const celle = [];
  const giorni = [];
  const pasti = new Map();

  for (const day of week.days || []) {
    const giorno = {
      dow: day.day_of_week,
      date: day.date,
      nome: day.day_name,
      saltato: day.is_skipped,
      passato: day.date < oggi,
      da_fare: 0,
    };
    giorni.push(giorno);

    for (const meal of day.meals || []) {
      if (!pasti.has(meal.slot_id)) {
        pasti.set(meal.slot_id, {
          id: meal.slot_id,
          nome: meal.slot_name,
          ordine: meal.slot_order,
          // "Lo faccio io": non si genera mai, e non è una scelta di questa dialog.
          mio: Boolean(meal.self_managed),
          da_fare: 0,
        });
      }
      if (!generabile(day, meal)) continue;
      if (!rifaiTutto && meal.recipe) continue;

      celle.push({ dow: day.day_of_week, slot: meal.slot_id });
      giorno.da_fare += 1;
      pasti.get(meal.slot_id).da_fare += 1;
    }
  }

  return { celle, giorni, pasti: [...pasti.values()].sort((a, b) => a.ordine - b.ordine) };
}

/** Quante caselle restano dentro la selezione: il numero sul pulsante. */
export const contaSelezione = (celle, giorni, pasti) =>
  celle.filter((c) => giorni.includes(c.dow) && pasti.includes(c.slot)).length;

/**
 * I giorni spuntati all'apertura: quelli che hanno qualcosa da fare, tolti i passati.
 *
 * Riempire un giorno già passato è una chiamata pagata per niente — quel pasto è
 * stato, o non è stato — ma se il da fare è tutto lì (una settimana archiviata che si
 * sta ricostruendo) si accendono lo stesso: altrimenti la dialog si aprirebbe col
 * pulsante spento e nessuna spiegazione del perché.
 */
export function giorniPredefiniti(giorni) {
  const conRoba = giorni.filter((g) => g.da_fare > 0);
  const futuri = conRoba.filter((g) => !g.passato);
  return (futuri.length ? futuri : conRoba).map((g) => g.dow);
}
