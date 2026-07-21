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
