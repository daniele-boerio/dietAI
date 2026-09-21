// Le quote delle cucine: quanta parte dei piatti prende ciascuna.
//
// È la stessa domanda del lucchetto nell'editor della dieta — *quanto* in totale e
// *come* si divide — con una differenza che semplifica tutto: qui il totale non è una
// scelta, è 100 per definizione. Non c'è nessun lucchetto da aprire, perché una
// percentuale che non somma a 100 non vuol dire niente.
//
// L'aritmetica è quella di `cuisines.clean()` nel backend, che è a sua volta quella di
// `_share_out` e di `lib/macros.js`: quote arrotondate e resto sulla più grande. Le due
// devono coincidere perché il numero che si vede mentre si tira il cursore è quello che
// verrà salvato — se il server ne restituisse un altro, i cursori salterebbero da soli
// appena finito di trascinarli.

// Quanto pesa poco una cucina che resta comunque in elenco. Zero non si usa: una voce
// spuntata che non può mai uscire è una voce che mente, e chi non la vuole più ha la
// X accanto. Di riflesso il massimo per una sola è 100 meno le altre.
export const QUOTA_MINIMA = 1;

const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

/** Il tetto di una singola cucina: quello che resta lasciando il minimo alle altre. */
export const tetto = (quote, chiave) =>
  100 - QUOTA_MINIMA * (Object.keys(quote).filter((k) => k !== chiave).length);

/**
 * Riporta le quote a interi che sommano **esattamente** a 100, nell'ordine dato.
 *
 * Il pareggio del resto non è pignoleria: arrotondando ogni quota per conto suo la
 * somma finisce quasi sempre a 99 o 101, e quel numero è scritto a schermo sotto la
 * parola «somma». Va sulla quota più grande, dove un punto si nota meno.
 *
 * Se c'è, è scelta: il numero dice solo quanto. Una voce a zero non si scarta — la si
 * porta al minimo — perché il cursore a fondo corsa non è un modo di togliere una
 * cucina, che ha la sua X apposta.
 */
export function normalizza(quote) {
  const chiavi = Object.keys(quote || {});
  if (chiavi.length === 0) return {};

  const totale = chiavi.reduce((s, k) => s + num(quote[k]), 0);
  const pesi = totale > 0 ? chiavi.map((k) => num(quote[k])) : chiavi.map(() => 1);
  const somma = pesi.reduce((a, b) => a + b, 0);

  const fuori = {};
  chiavi.forEach((k, i) => {
    fuori[k] = Math.max(Math.round((100 * pesi[i]) / somma), QUOTA_MINIMA);
  });

  // Il minimo si applica prima del pareggio, o riportarlo su romperebbe di nuovo la
  // somma. In diminuzione non si scende sotto il minimo: si passa alla successiva.
  let scarto = 100 - chiavi.reduce((s, k) => s + fuori[k], 0);
  const ordine = [...chiavi].sort((a, b) =>
    scarto > 0 ? fuori[b] - fuori[a] : fuori[a] - fuori[b]
  );
  for (const k of ordine) {
    if (scarto === 0) break;
    const passo = scarto > 0 ? scarto : Math.max(scarto, QUOTA_MINIMA - fuori[k]);
    fuori[k] += passo;
    scarto -= passo;
  }
  return fuori;
}

/**
 * Porta una cucina alla quota chiesta; le altre si stringono (o si allargano) in
 * proporzione a quanto pesavano.
 *
 * È il lucchetto dell'editor della dieta, senza il lucchetto: alzare l'italiana al 70%
 * ridivide i piatti, non ne aggiunge. Il valore si ferma al tetto, perché alle altre
 * deve restare almeno il minimo — se scendessero a zero sarebbero spuntate per finta.
 */
export function riparti(quote, chiave, valore) {
  const altre = Object.keys(quote).filter((k) => k !== chiave);
  if (altre.length === 0) return { [chiave]: 100 };

  const mia = Math.min(Math.max(Math.round(num(valore)), QUOTA_MINIMA), tetto(quote, chiave));
  const resto = 100 - mia;
  const somma = altre.reduce((s, k) => s + num(quote[k]), 0);

  // Tutte le altre a zero non hanno proporzioni da rispettare: parti uguali.
  const grezze = {};
  for (const k of Object.keys(quote)) {
    grezze[k] = k === chiave ? mia : (somma > 0 ? (resto * num(quote[k])) / somma : resto / altre.length);
  }
  // La normalizzazione tocca anche la quota appena scritta, che a quel punto però è
  // già giusta: gli arrotondamenti sono tutti nelle altre, che sono quelle mosse.
  const fuori = normalizza(grezze);
  const differenza = mia - fuori[chiave];
  if (differenza !== 0) {
    // Il numero scritto dall'utente vince sull'arrotondamento: è quello che sta
    // leggendo mentre trascina, e vederlo cambiare di un punto da solo è il modo più
    // rapido di non fidarsi più del cursore.
    const vittima = altre.reduce((a, b) => (fuori[b] > fuori[a] ? b : a));
    if (fuori[vittima] - differenza >= QUOTA_MINIMA) {
      fuori[chiave] = mia;
      fuori[vittima] -= differenza;
    }
  }
  return fuori;
}

/**
 * Aggiunge una cucina prendendole una quota media dalle altre, che si stringono in
 * proporzione. Il totale non cambia: aggiungere la coreana significa ridividere i
 * piatti, non cucinarne di più.
 */
export function aggiungi(quote, chiave) {
  const chiavi = Object.keys(quote);
  if (chiavi.includes(chiave)) return { ...quote };
  if (chiavi.length === 0) return { [chiave]: 100 };
  return normalizza({ ...quote, [chiave]: 100 / (chiavi.length + 1) });
}

/** Toglie una cucina; la sua quota torna alle altre, in proporzione. */
export function togli(quote, chiave) {
  const resto = Object.fromEntries(
    Object.entries(quote).filter(([k]) => k !== chiave)
  );
  return normalizza(resto);
}
