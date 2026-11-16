import { describe, expect, it } from 'vitest';
import { dettagliMangiati, todayTotals } from './today';

const colazione = {
  target_calories: 400,
  is_followed: true,
  is_skipped: false,
  recipe: { calories: 400, protein_g: 20, carbs_g: 50, fat_g: 12 },
};
const pranzo = {
  target_calories: 1000,
  is_followed: true,
  is_skipped: false,
  recipe: { calories: 1000, protein_g: 50, carbs_g: 120, fat_g: 30 },
};
const cena = (extra) => ({
  target_calories: 600,
  is_followed: false,
  is_skipped: true,
  recipe: { calories: 600, protein_g: 45, carbs_g: 50, fat_g: 22 },
  ...extra,
});

describe('il totale di oggi', () => {
  it('conta la stima al posto del piatto rimandato, contro il target pieno', () => {
    const t = todayTotals([
      colazione,
      pranzo,
      cena({ eaten_nutrition: { calories: 850, protein_g: 32, carbs_g: 105, fat_g: 30 } }),
    ]);
    expect(t.calories).toBe(400 + 1000 + 850);
    expect(t.target).toBe(2000); // la dieta non cambia per una cena andata diversamente
    expect(t.protein_g).toBe(20 + 50 + 32);
    expect(t.stime).toBe(1);
  });

  it('«non ho mangiato niente» è uno zero, e il target resta', () => {
    const t = todayTotals([
      colazione,
      pranzo,
      cena({ eaten_nutrition: { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 } }),
    ]);
    expect(t.calories).toBe(1400);
    expect(t.target).toBe(2000);
    expect(t.mancanti).toBe(0);
    expect(t.stime).toBe(0); // uno zero saputo non è una stima
  });

  it('saltato senza stima: zero, target pieno, e lo dice', () => {
    const t = todayTotals([colazione, pranzo, cena({ eaten_nutrition: null })]);
    expect(t.calories).toBe(1400);
    expect(t.target).toBe(2000);
    expect(t.mancanti).toBe(1);
  });

  it('i pasti non ancora segnati contano il piatto in programma', () => {
    const t = todayTotals([colazione, { ...pranzo, is_followed: null }]);
    expect(t.calories).toBe(1400);
    expect(t.segnati).toBe(1);
  });

  it('«lo prepari tu» senza ricetta vale il target', () => {
    const t = todayTotals([{ target_calories: 300, is_followed: null, self_managed: true, recipe: null }]);
    expect(t.calories).toBe(300);
  });
});

describe('mangiato finora', () => {
  it('la mattina, niente segnato: zero', () => {
    const t = todayTotals([
      { ...colazione, is_followed: null },
      { ...pranzo, is_followed: null },
    ]);
    expect(t.mangiato.calories).toBe(0);
    expect(t.calories).toBe(1400); // il piano resta, sotto
  });

  it('cresce coi pasti segnati, coi loro valori e non col target', () => {
    const pranzoAbbondante = {
      ...pranzo,
      target_calories: 500,
      recipe: { calories: 700, protein_g: 30, carbs_g: 80, fat_g: 25 },
    };
    const t = todayTotals([colazione, pranzoAbbondante, { ...cena(), is_skipped: false, is_followed: null }]);
    expect(t.mangiato.calories).toBe(400 + 700);
    expect(t.mangiato.protein_g).toBe(20 + 30);
  });

  it('«ho mangiato altro» conta la stima', () => {
    const t = todayTotals([
      colazione,
      cena({ eaten_nutrition: { calories: 850, protein_g: 32, carbs_g: 105, fat_g: 30 } }),
    ]);
    expect(t.mangiato.calories).toBe(400 + 850);
    expect(t.stime).toBe(1);
  });
});

describe('dettagliMangiati', () => {
  const piatto = (extra) => ({
    is_followed: true,
    is_skipped: false,
    target_calories: 500,
    recipe: { calories: 500, protein_g: 20, carbs_g: 60, fat_g: 15, ...extra },
  });

  it('somma solo i pasti segnati', () => {
    const meals = [
      piatto({ fiber_g: 4, sugar_g: 10, saturated_fat_g: 2, alcohol_g: 0, caffeine_mg: 80 }),
      { ...piatto({ fiber_g: 9, sugar_g: 9, saturated_fat_g: 9 }), is_followed: null },
    ];
    const d = dettagliMangiati(meals);
    expect(d.map((v) => v.key)).toEqual(['fiber_g', 'sugar_g', 'saturated_fat_g', 'caffeine_mg']);
    expect(d[0]).toMatchObject({ valore: 4, parziale: false });
  });

  it('un valore che non si sa lascia la somma aperta, non conta zero', () => {
    const meals = [piatto({ fiber_g: 4 }), piatto({ fiber_g: null })];
    const fibre = dettagliMangiati(meals).find((v) => v.key === 'fiber_g');
    expect(fibre).toMatchObject({ valore: 4, parziale: true });
  });

  it('«ho mangiato altro» porta la sua stima', () => {
    const meals = [
      {
        is_followed: false,
        is_skipped: true,
        target_calories: 500,
        recipe: { calories: 500, fiber_g: 30 },
        eaten_nutrition: { calories: 800, fiber_g: 3, sugar_g: 5, saturated_fat_g: 6 },
      },
    ];
    const fibre = dettagliMangiati(meals).find((v) => v.key === 'fiber_g');
    expect(fibre.valore).toBe(3);
  });

  it('niente segnato, niente voci', () => {
    expect(dettagliMangiati([{ ...piatto({ fiber_g: 4 }), is_followed: null }])).toEqual([]);
  });
});
