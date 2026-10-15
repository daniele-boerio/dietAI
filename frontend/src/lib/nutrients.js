// Gli altri valori di una ricetta o di una stima, oltre a calorie e macro: fibre,
// zuccheri, grassi saturi, alcol, caffeina. Arrivano dal backend per porzione, e
// ognuno può essere null — «non si sa», che non è zero: un ingrediente senza quel
// valore lo lascia aperto. Qui diventano la riga che sta sotto i macro.
//
// Fibre, zuccheri e saturi si scrivono anche quando sono zero (uno zero di zuccheri
// è un'informazione). Alcol e caffeina solo quando ci sono: «alcol 0 g» sotto ogni
// insalata sarebbe rumore.

const VOCI = [
  { key: 'fiber_g', label: 'Fibre', unit: 'g', sempre: true },
  { key: 'sugar_g', label: 'Zuccheri', unit: 'g', sempre: true },
  { key: 'saturated_fat_g', label: 'Saturi', unit: 'g', sempre: true },
  { key: 'alcohol_g', label: 'Alcol', unit: 'g', sempre: false },
  { key: 'caffeine_mg', label: 'Caffeina', unit: 'mg', sempre: false },
];

function numero(value, unit) {
  // I mg all'intero, i grammi a un decimale tolto se è zero: «4,2 g», «9 g».
  const arrotondato = unit === 'mg' ? Math.round(value) : Math.round(value * 10) / 10;
  return String(arrotondato).replace('.', ',');
}

export function otherNutrients(source) {
  if (!source) return [];
  return VOCI.filter(({ key, sempre }) => {
    const v = source[key];
    return v != null && (sempre || v > 0);
  }).map(({ key, label, unit }) => ({
    key,
    label,
    text: `${label} ${numero(source[key], unit)} ${unit}`,
  }));
}

export function otherNutrientsLine(source) {
  return otherNutrients(source)
    .map((v) => v.text)
    .join(' · ');
}
