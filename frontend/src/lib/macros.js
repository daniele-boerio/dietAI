// Ripartizione di calorie e macro tra i pasti della dieta.
//
// Il totale giornaliero è quello che ha prescritto il nutrizionista: è il numero che
// non deve cambiare. Come lo si divide durante la giornata è invece una scelta di
// organizzazione — salto la colazione, aggiungo uno spuntino — e quando cambia il
// numero di pasti il totale va ridistribuito, non perso.

export const FIELDS = ['calories', 'protein_g', 'carbs_g', 'fat_g'];

// Le calorie sono numeri interi, i macro hanno un decimale: arrotondare a caso
// farebbe ballare il totale di qualche unità a ogni modifica.
const DECIMALS = { calories: 0, protein_g: 1, carbs_g: 1, fat_g: 1 };

const round = (value, decimals) => {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
};

/** L'arrotondamento di un campo, per chi deve confrontarsi con quello che esce da qui. */
export const roundField = (value, field) => round(Number(value) || 0, DECIMALS[field]);

const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

/**
 * «Lo faccio io»: un pasto che l'utente prepara da sé.
 *
 * Non è solo una cosa che l'AI non genera — è un pasto di cui i numeri li ha decisi
 * lui, ed è l'unico che sa quanto pesa. La ridistribuzione lo salta: alzare la
 * colazione può ridivedere quello che cucina DietAI, non riscrivere la merenda che
 * l'utente si porta da casa. Chi resta senza nessun pasto libero non ha più dove
 * spostare la differenza, e a quel punto la strada è aprire il lucchetto.
 */
export const isMine = (meal) => meal?.auto_generate === false;

const sumMine = (meals, field) =>
  meals.reduce((total, meal) => (isMine(meal) ? total + num(meal[field]) : total), 0);

export function dailyTotals(meals) {
  return FIELDS.reduce((acc, field) => {
    acc[field] = round(
      meals.reduce((sum, meal) => sum + num(meal[field]), 0),
      DECIMALS[field]
    );
    return acc;
  }, {});
}

/**
 * Divide `total` tra `values` mantenendone le proporzioni.
 *
 * L'ultimo passaggio non è pignoleria: arrotondando ogni quota per conto suo la
 * somma finisce quasi sempre a ±1 dal totale, e il totale è proprio la cosa che
 * qui non deve muoversi. Il resto va sulla quota più grande, dove si nota meno.
 */
function shareOut(values, total, decimals) {
  if (values.length === 0) return [];

  const sum = values.reduce((a, b) => a + b, 0);
  // Se i pasti rimasti sono tutti a zero non ci sono proporzioni da rispettare:
  // si divide in parti uguali.
  const weights = sum > 0 ? values : values.map(() => 1);
  const weightSum = weights.reduce((a, b) => a + b, 0);

  const shares = weights.map((w) => round((total * w) / weightSum, decimals));
  const drift = round(total - shares.reduce((a, b) => a + b, 0), decimals);

  if (drift !== 0) {
    const biggest = shares.indexOf(Math.max(...shares));
    shares[biggest] = round(shares[biggest] + drift, decimals);
  }
  return shares;
}

/**
 * Riscala i pasti perché la somma di ogni campo torni ai totali dati, muovendo solo
 * quelli che genera DietAI.
 *
 * I pasti «lo faccio io» restano dove sono e quello che resta della giornata si
 * divide fra gli altri, in proporzione a quanto pesavano. Se di pasti liberi non ce
 * n'è nemmeno uno non c'è niente da riscalare: i numeri restano quelli e il totale con
 * loro — è il chiamante a doverlo dire a schermo, perché una giornata che cambia in
 * silenzio è il modo peggiore di scoprirlo.
 */
export function rescaleToTotals(meals, totals) {
  if (meals.length === 0) return [];

  const liberi = meals.map((_, i) => i).filter((i) => !isMine(meals[i]));
  if (liberi.length === 0) return meals.map((meal) => ({ ...meal }));

  const shares = {};
  for (const field of FIELDS) {
    shares[field] = shareOut(
      liberi.map((i) => num(meals[i][field])),
      Math.max(round(num(totals[field]) - sumMine(meals, field), DECIMALS[field]), 0),
      DECIMALS[field]
    );
  }

  const quota = new Map(liberi.map((i, k) => [i, k]));
  return meals.map((meal, i) => {
    const k = quota.get(i);
    if (k === undefined) return { ...meal };
    return {
      ...meal,
      ...FIELDS.reduce((acc, field) => ({ ...acc, [field]: shares[field][k] }), {}),
    };
  });
}

/**
 * Toglie un pasto e ridistribuisce le sue calorie e i suoi macro sugli altri,
 * in proporzione a quanto pesavano già. Il totale giornaliero resta identico — a meno
 * che di pasti da muovere non ne resti nessuno, e allora la giornata cala davvero.
 */
export function removeMeal(meals, index) {
  const totals = dailyTotals(meals);
  const remaining = meals.filter((_, i) => i !== index);
  return rescaleToTotals(remaining, totals);
}

/**
 * Riporta la somma di un campo al totale bloccato dopo che un pasto è stato
 * modificato: la differenza va sugli **altri**, in proporzione a quanto pesano.
 *
 * È il lucchetto chiuso: alzare la colazione ridivide la giornata, non la allunga.
 * A muoversi però sono solo i pasti che genera DietAI: quelli segnati «lo faccio io»
 * sono fermi per definizione, e correggere la colazione non può riscrivere lo spuntino
 * che l'utente si è già organizzato.
 *
 * Il valore scritto si ferma perciò a quello che **resta** dopo i pasti fermi, non al
 * totale: chi batte 5000 kcal in un pasto solo non vuole gli altri in negativo, vuole
 * gli altri a zero. E se di pasti liberi non ce n'è nessuno il valore è già deciso —
 * col totale bloccato e tutto il resto fermo, di gradi di libertà non ne restano.
 */
export function rebalanceField(meals, index, field, total) {
  const decimals = DECIMALS[field];
  const target = round(num(total), decimals);
  const altri = meals.filter((_, i) => i !== index);
  // Quanto può prendersi il pasto che si sta scrivendo: il totale meno quello che è
  // fermo in mano all'utente.
  const spazio = round(Math.max(target - sumMine(altri, field), 0), decimals);

  const liberi = altri.filter((meal) => !isMine(meal));
  if (liberi.length === 0) {
    return meals.map((meal, i) => (i === index ? { ...meal, [field]: spazio } : { ...meal }));
  }

  const edited = round(Math.min(num(meals[index][field]), spazio), decimals);
  const shares = shareOut(
    liberi.map((meal) => num(meal[field])),
    round(spazio - edited, decimals),
    decimals
  );

  let next = 0;
  return meals.map((meal, i) => {
    if (i === index) return { ...meal, [field]: edited };
    if (isMine(meal)) return { ...meal };
    return { ...meal, [field]: shares[next++] };
  });
}

/**
 * Divide i totali fra i pasti dati, ciascuno col peso che si porta dietro.
 *
 * È la stessa aritmetica di `_share_out` nel backend (utils/nutrition.py) applicata
 * agli stessi pesi, che arrivano da `/diet/questionnaire/options`: il questionario
 * può mostrare la divisione mentre si spuntano i pasti, senza una chiamata per clic,
 * e quello che si vede è quello che verrà salvato.
 */
export function splitByWeights(meals, totals) {
  return rescaleToTotals(
    meals.map((meal) =>
      FIELDS.reduce((acc, field) => ({ ...acc, [field]: meal.weight }), { ...meal })
    ),
    FIELDS.reduce((acc, field) => ({ ...acc, [field]: num(totals[field]) }), {})
  );
}

/**
 * Aggiunge un pasto prendendo una quota media dagli altri, che si stringono in
 * proporzione. Anche qui il totale giornaliero non cambia: aggiungere uno spuntino
 * significa ridistribuire la giornata, non mangiare di più.
 *
 * La quota esce però dal budget dei soli pasti liberi — dai pasti «lo faccio io» non
 * si prende niente. Se tutta la giornata è in mano all'utente il pasto nuovo nasce a
 * zero: non c'era da dove prenderla.
 */
export function addMeal(meals, name = 'Nuovo pasto') {
  const totals = dailyTotals(meals);

  if (meals.length === 0) {
    return [{ name, ...FIELDS.reduce((acc, f) => ({ ...acc, [f]: 0 }), {}) }];
  }

  const liberi = meals.filter((meal) => !isMine(meal)).length;
  const average = FIELDS.reduce(
    (acc, field) => ({
      ...acc,
      [field]: Math.max(totals[field] - sumMine(meals, field), 0) / (liberi + 1),
    }),
    {}
  );

  return rescaleToTotals([...meals, { name, ...average }], totals);
}
