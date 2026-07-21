import { describe, expect, it } from 'vitest';
import { addMeal, dailyTotals, removeMeal, rescaleToTotals } from './macros';

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
