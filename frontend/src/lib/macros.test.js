import { describe, expect, it } from 'vitest';
import {
  addMeal,
  dailyTotals,
  rebalanceField,
  removeMeal,
  rescaleToTotals,
  splitByWeights,
} from './macros';

const DIETA = [
  { name: 'Colazione', calories: 400, protein_g: 20, carbs_g: 50, fat_g: 12 },
  { name: 'Pranzo', calories: 700, protein_g: 40, carbs_g: 80, fat_g: 20 },
  { name: 'Cena', calories: 600, protein_g: 45, carbs_g: 50, fat_g: 22 },
];

// Il totale giornaliero è la prescrizione del nutrizionista: qualunque cosa si
// faccia ai pasti, questo non deve muoversi.
const TOTALI = { calories: 1700, protein_g: 105, carbs_g: 180, fat_g: 54 };

describe('totali giornalieri', () => {
  it('somma tutti i pasti', () => {
    expect(dailyTotals(DIETA)).toEqual(TOTALI);
  });

  it('ignora i valori non numerici scritti a mano nel form', () => {
    const totals = dailyTotals([...DIETA, { name: 'Vuoto', calories: '', protein_g: null }]);
    expect(totals.calories).toBe(1700);
  });
});

describe('rimozione di un pasto', () => {
  it('mantiene identico il totale della giornata', () => {
    const dopo = removeMeal(DIETA, 0);

    expect(dopo).toHaveLength(2);
    expect(dailyTotals(dopo)).toEqual(TOTALI);
  });

  it('ridistribuisce in proporzione a quanto pesavano già', () => {
    const [pranzo, cena] = removeMeal(DIETA, 0);

    // Pranzo valeva 700 su 1300 delle calorie rimaste: 700/1300 * 1700 ≈ 915
    expect(pranzo.calories).toBe(915);
    expect(cena.calories).toBe(785);
    expect(pranzo.calories + cena.calories).toBe(TOTALI.calories);
    // Il pranzo resta il pasto più grande: le proporzioni non si ribaltano.
    expect(pranzo.calories).toBeGreaterThan(cena.calories);
  });

  it('ridistribuisce anche i macro, non solo le calorie', () => {
    const dopo = removeMeal(DIETA, 0);
    const totali = dailyTotals(dopo);

    expect(totali.protein_g).toBe(TOTALI.protein_g);
    expect(totali.carbs_g).toBe(TOTALI.carbs_g);
    expect(totali.fat_g).toBe(TOTALI.fat_g);
  });

  it('non perde nemmeno un grammo per gli arrotondamenti', () => {
    // Numeri scelti apposta perché la divisione non sia mai esatta.
    const scomodi = [
      { name: 'A', calories: 333, protein_g: 11.1, carbs_g: 33.3, fat_g: 7.7 },
      { name: 'B', calories: 667, protein_g: 22.2, carbs_g: 66.6, fat_g: 14.4 },
      { name: 'C', calories: 501, protein_g: 33.3, carbs_g: 49.9, fat_g: 11.1 },
    ];
    const attesi = dailyTotals(scomodi);

    for (let i = 0; i < scomodi.length; i++) {
      expect(dailyTotals(removeMeal(scomodi, i))).toEqual(attesi);
    }
  });

  it('con pasti tutti a zero divide in parti uguali senza dividere per zero', () => {
    const vuoti = [
      { name: 'A', calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
      { name: 'B', calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
    ];
    expect(removeMeal(vuoti, 0)).toHaveLength(1);
    expect(dailyTotals(removeMeal(vuoti, 0)).calories).toBe(0);
  });

  it("togliendo l'ultimo pasto restituisce una lista vuota", () => {
    expect(removeMeal([DIETA[0]], 0)).toEqual([]);
  });

  it('conserva il nome degli altri pasti', () => {
    expect(removeMeal(DIETA, 1).map((m) => m.name)).toEqual(['Colazione', 'Cena']);
  });
});

describe('aggiunta di un pasto', () => {
  it('mantiene identico il totale della giornata', () => {
    const dopo = addMeal(DIETA, 'Spuntino');

    expect(dopo).toHaveLength(4);
    expect(dailyTotals(dopo)).toEqual(TOTALI);
  });

  it('dà al nuovo pasto una quota di partenza sensata', () => {
    const dopo = addMeal(DIETA, 'Spuntino');
    const spuntino = dopo.at(-1);

    expect(spuntino.name).toBe('Spuntino');
    // Una quota media: né zero né la metà della giornata.
    expect(spuntino.calories).toBeGreaterThan(300);
    expect(spuntino.calories).toBeLessThan(500);
  });

  it('stringe gli altri pasti in proporzione', () => {
    const [colazione, pranzo] = addMeal(DIETA, 'Spuntino');

    expect(colazione.calories).toBeLessThan(400);
    expect(pranzo.calories).toBeLessThan(700);
    expect(pranzo.calories).toBeGreaterThan(colazione.calories);
  });

  it('partendo da zero pasti non esplode', () => {
    expect(addMeal([], 'Colazione')).toEqual([
      { name: 'Colazione', calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
    ]);
  });
});

describe('lucchetto: un pasto cambia, il totale no', () => {
  it('sposta sugli altri quello che si è aggiunto a un pasto', () => {
    // La colazione da 400 passa a 500: le 100 kcal in più le mettono pranzo e cena.
    const scritta = DIETA.map((m, i) => (i === 0 ? { ...m, calories: 500 } : m));
    const dopo = rebalanceField(scritta, 0, 'calories', TOTALI.calories);

    expect(dopo[0].calories).toBe(500);
    expect(dailyTotals(dopo).calories).toBe(TOTALI.calories);
    expect(dopo[1].calories).toBeLessThan(700);
    expect(dopo[2].calories).toBeLessThan(600);
  });

  it('tocca solo il campo modificato', () => {
    const scritta = DIETA.map((m, i) => (i === 1 ? { ...m, protein_g: 50 } : m));
    const dopo = rebalanceField(scritta, 1, 'protein_g', TOTALI.protein_g);

    expect(dailyTotals(dopo).protein_g).toBe(TOTALI.protein_g);
    // Le calorie non le ha chieste nessuno: restano quelle scritte a mano.
    expect(dopo.map((m) => m.calories)).toEqual([400, 700, 600]);
  });

  it('mantiene le proporzioni fra gli altri pasti', () => {
    const scritta = DIETA.map((m, i) => (i === 0 ? { ...m, calories: 300 } : m));
    const [, pranzo, cena] = rebalanceField(scritta, 0, 'calories', TOTALI.calories);

    // Pranzo pesava 700/1300 di quello che restava, e continua a pesare tanto.
    expect(pranzo.calories / cena.calories).toBeCloseTo(700 / 600, 1);
  });

  it('non manda gli altri in negativo quando si esagera', () => {
    const assurda = DIETA.map((m, i) => (i === 0 ? { ...m, calories: 9000 } : m));
    const dopo = rebalanceField(assurda, 0, 'calories', TOTALI.calories);

    expect(dopo[0].calories).toBe(TOTALI.calories);
    expect(dopo[1].calories).toBe(0);
    expect(dopo[2].calories).toBe(0);
  });

  it("con un pasto solo il valore torna a essere il totale", () => {
    const dopo = rebalanceField([{ name: 'Pranzo', calories: 1200 }], 0, 'calories', 1700);
    expect(dopo[0].calories).toBe(1700);
  });

  it('riparte da zero senza dividere per zero', () => {
    const spenti = [
      { name: 'A', calories: 500 },
      { name: 'B', calories: 0 },
      { name: 'C', calories: 0 },
    ];
    const dopo = rebalanceField(spenti, 0, 'calories', 1000);

    expect(dopo[1].calories).toBe(250);
    expect(dopo[2].calories).toBe(250);
  });
});

// «Lo faccio io» non è solo un pasto che l'AI non genera: i suoi numeri li ha scritti
// l'utente, e riorganizzare la giornata non può riscriverglieli. Il caso vero: colazione
// e spuntino li preparo io, correggo la colazione e mi ritrovo lo spuntino cambiato.
describe('i pasti «lo faccio io» non li tocca nessuno', () => {
  const MISTA = [
    { name: 'Colazione', calories: 400, protein_g: 20, carbs_g: 50, fat_g: 12,
      auto_generate: false },
    { name: 'Spuntino', calories: 200, protein_g: 10, carbs_g: 25, fat_g: 6,
      auto_generate: false },
    { name: 'Pranzo', calories: 700, protein_g: 40, carbs_g: 80, fat_g: 20 },
    { name: 'Cena', calories: 600, protein_g: 45, carbs_g: 50, fat_g: 22 },
  ];
  const TOTALE = dailyTotals(MISTA).calories; // 1900

  it('correggendo un pasto mio, gli altri miei restano identici', () => {
    // La colazione passa da 400 a 500: le 100 kcal le mettono pranzo e cena.
    const scritta = MISTA.map((m, i) => (i === 0 ? { ...m, calories: 500 } : m));
    const dopo = rebalanceField(scritta, 0, 'calories', TOTALE);

    expect(dopo[0].calories).toBe(500);
    expect(dopo[1].calories).toBe(200); // lo spuntino non si è mosso
    expect(dopo[2].calories).toBeLessThan(700);
    expect(dopo[3].calories).toBeLessThan(600);
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });

  it('vale per ogni campo, non solo per le calorie', () => {
    const scritta = MISTA.map((m, i) => (i === 0 ? { ...m, protein_g: 30 } : m));
    const dopo = rebalanceField(scritta, 0, 'protein_g', dailyTotals(MISTA).protein_g);

    expect(dopo[1].protein_g).toBe(10);
    expect(dailyTotals(dopo).protein_g).toBe(dailyTotals(MISTA).protein_g);
  });

  it('anche cambiando un pasto di DietAI i miei restano fermi', () => {
    const scritta = MISTA.map((m, i) => (i === 2 ? { ...m, calories: 900 } : m));
    const dopo = rebalanceField(scritta, 2, 'calories', TOTALE);

    expect(dopo.slice(0, 2).map((m) => m.calories)).toEqual([400, 200]);
    expect(dopo[3].calories).toBe(400); // solo la cena assorbe
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });

  it('il valore scritto si ferma a quello che resta, non al totale', () => {
    // 5000 kcal a pranzo: pranzo e cena insieme valgono 1300, non 1900.
    const assurda = MISTA.map((m, i) => (i === 2 ? { ...m, calories: 5000 } : m));
    const dopo = rebalanceField(assurda, 2, 'calories', TOTALE);

    expect(dopo[2].calories).toBe(1300);
    expect(dopo[3].calories).toBe(0);
    expect(dopo.slice(0, 2).map((m) => m.calories)).toEqual([400, 200]);
  });

  it('se li preparo tutti io il valore torna indietro invece di spostare', () => {
    // Non c'è nessun pasto libero: col totale bloccato non resta un grado di libertà.
    const tutti = MISTA.map((m) => ({ ...m, auto_generate: false }));
    const scritta = tutti.map((m, i) => (i === 0 ? { ...m, calories: 900 } : m));
    const dopo = rebalanceField(scritta, 0, 'calories', TOTALE);

    expect(dopo[0].calories).toBe(400);
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });

  it('togliendo un pasto le sue calorie vanno solo su quelli di DietAI', () => {
    const dopo = removeMeal(MISTA, 3); // via la cena

    expect(dopo.slice(0, 2).map((m) => m.calories)).toEqual([400, 200]);
    expect(dopo[2].calories).toBe(1300); // pranzo si prende tutta la cena
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });

  it('togliendo un pasto mio la giornata resta intera lo stesso', () => {
    const dopo = removeMeal(MISTA, 1); // via lo spuntino, che era mio

    expect(dopo[0].calories).toBe(400);
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });

  it('se li preparo tutti io togliere un pasto accorcia la giornata', () => {
    const tutti = MISTA.map((m) => ({ ...m, auto_generate: false }));
    const dopo = removeMeal(tutti, 1);

    expect(dopo.map((m) => m.calories)).toEqual([400, 700, 600]);
    expect(dailyTotals(dopo).calories).toBe(TOTALE - 200);
  });

  it('il pasto aggiunto prende la sua quota solo dai pasti di DietAI', () => {
    const dopo = addMeal(MISTA, 'Spuntino sera');

    expect(dopo.slice(0, 2).map((m) => m.calories)).toEqual([400, 200]);
    expect(dopo.at(-1).calories).toBeGreaterThan(0);
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });

  it('se li preparo tutti io il pasto aggiunto nasce a zero', () => {
    const tutti = MISTA.map((m) => ({ ...m, auto_generate: false }));
    const dopo = addMeal(tutti, 'Spuntino sera');

    expect(dopo.at(-1).calories).toBe(0);
    expect(dopo.slice(0, 4).map((m) => m.calories)).toEqual([400, 200, 700, 600]);
    expect(dailyTotals(dopo).calories).toBe(TOTALE);
  });
});

describe('divisione per pesi (i pasti scelti nel questionario)', () => {
  const CATALOGO = [
    { key: 'colazione', name: 'Colazione', weight: 0.2 },
    { key: 'pranzo', name: 'Pranzo', weight: 0.33 },
    { key: 'cena', name: 'Cena', weight: 0.3 },
  ];

  it('divide tutto il totale, senza perderne un pezzo', () => {
    const righe = splitByWeights(CATALOGO, TOTALI);

    expect(righe.map((r) => r.name)).toEqual(['Colazione', 'Pranzo', 'Cena']);
    expect(dailyTotals(righe)).toEqual(TOTALI);
  });

  it('rispetta i pesi: il pranzo è il pasto più grande', () => {
    const [colazione, pranzo, cena] = splitByWeights(CATALOGO, TOTALI);

    expect(pranzo.calories).toBeGreaterThan(cena.calories);
    expect(cena.calories).toBeGreaterThan(colazione.calories);
    // 0.2 su 0.83 di peso totale: poco meno di un quarto della giornata.
    expect(colazione.calories).toBe(Math.round((1700 * 0.2) / 0.83));
  });

  it('togliendo la colazione la giornata resta intera', () => {
    const senza = splitByWeights(
      CATALOGO.filter((m) => m.key !== 'colazione'),
      TOTALI
    );

    expect(senza).toHaveLength(2);
    expect(dailyTotals(senza)).toEqual(TOTALI);
    // Quello che non si fa a colazione si mangia a pranzo e a cena.
    expect(senza[0].calories).toBeGreaterThan(splitByWeights(CATALOGO, TOTALI)[1].calories);
  });

  it('con i totali scritti a mano (stringhe dal form) non esplode', () => {
    const righe = splitByWeights(CATALOGO, {
      calories: '1800',
      protein_g: '',
      carbs_g: 200,
      fat_g: 60,
    });

    expect(dailyTotals(righe).calories).toBe(1800);
    expect(dailyTotals(righe).protein_g).toBe(0);
  });
});

describe('riscalatura verso totali diversi', () => {
  it('adegua i pasti a un nuovo totale giornaliero', () => {
    const dimezzata = rescaleToTotals(DIETA, {
      calories: 850,
      protein_g: 52.5,
      carbs_g: 90,
      fat_g: 27,
    });

    expect(dailyTotals(dimezzata).calories).toBe(850);
    expect(dimezzata[0].calories).toBe(200);
  });
});
