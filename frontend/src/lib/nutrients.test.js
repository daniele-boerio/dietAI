import { describe, expect, it } from 'vitest';
import { otherNutrients, otherNutrientsLine } from './nutrients';

describe('gli altri valori', () => {
  it('scrive fibre, zuccheri e saturi anche a zero, alcol e caffeina solo se ci sono', () => {
    const riga = otherNutrientsLine({
      fiber_g: 4.25,
      sugar_g: 0,
      saturated_fat_g: 2.4,
      alcohol_g: 0,
      caffeine_mg: 0,
    });
    expect(riga).toBe('Fibre 4,3 g · Zuccheri 0 g · Saturi 2,4 g');
  });

  it('non inventa uno zero dove il valore non si sa', () => {
    expect(otherNutrients({ fiber_g: null, sugar_g: 9, saturated_fat_g: undefined })).toEqual([
      { key: 'sugar_g', label: 'Zuccheri', text: 'Zuccheri 9 g' },
    ]);
  });

  it("dice l'alcol e la caffeina quando ci sono", () => {
    expect(otherNutrientsLine({ alcohol_g: 15.8, caffeine_mg: 65.4 })).toBe(
      'Alcol 15,8 g · Caffeina 65 mg',
    );
  });

  it('senza niente, niente', () => {
    expect(otherNutrientsLine(null)).toBe('');
    expect(otherNutrientsLine({ calories: 500 })).toBe('');
  });
});
