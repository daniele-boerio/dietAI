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

const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

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

/** Riscala i pasti perché la somma di ogni campo torni ai totali dati. */
export function rescaleToTotals(meals, totals) {
  if (meals.length === 0) return [];

  const shares = {};
  for (const field of FIELDS) {
    shares[field] = shareOut(
      meals.map((m) => num(m[field])),
      totals[field] ?? 0,
      DECIMALS[field]
    );
  }

  return meals.map((meal, i) => ({
    ...meal,
    ...FIELDS.reduce((acc, field) => ({ ...acc, [field]: shares[field][i] }), {}),
  }));
}

/**
 * Toglie un pasto e ridistribuisce le sue calorie e i suoi macro sugli altri,
 * in proporzione a quanto pesavano già. Il totale giornaliero resta identico.
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
 * Il valore scritto si ferma al totale — chi batte 5000 kcal in un pasto solo non
 * vuole gli altri in negativo, vuole gli altri a zero.
 */
export function rebalanceField(meals, index, field, total) {
  const decimals = DECIMALS[field];
  const target = round(num(total), decimals);
  const edited = round(Math.min(num(meals[index][field]), target), decimals);

  // Con un pasto solo non c'è nessuno su cui spostare la differenza: il valore torna
  // ad essere il totale, che è l'unica cosa che il lucchetto promette.
  if (meals.length === 1) return meals.map((meal) => ({ ...meal, [field]: target }));

  const shares = shareOut(
    meals.filter((_, i) => i !== index).map((meal) => num(meal[field])),
    round(target - edited, decimals),
    decimals
  );

  let next = 0;
  return meals.map((meal, i) =>
    i === index ? { ...meal, [field]: edited } : { ...meal, [field]: shares[next++] }
  );
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
 */
export function addMeal(meals, name = 'Nuovo pasto') {
  const totals = dailyTotals(meals);

  if (meals.length === 0) {
    return [{ name, ...FIELDS.reduce((acc, f) => ({ ...acc, [f]: 0 }), {}) }];
  }

  const average = FIELDS.reduce(
    (acc, field) => ({ ...acc, [field]: totals[field] / meals.length }),
    {}
  );

  return rescaleToTotals([...meals, { name, ...average }], totals);
}
