// Il conto della giornata nella home: quanto si mangia oggi contro quanto chiede la
// dieta.
//
// Il target è sempre quello pieno della giornata: la dieta non cambia perché una cena
// è andata diversamente. Prima un pasto «ho mangiato altro» usciva da tutte e due le
// cifre — niente calorie, niente target — e una pizza al posto della cena dava
// «1400 / 1400», come se la giornata fosse andata a puntino. Ora quel pasto conta per
// quello che si è mangiato davvero, la stima del modello (o lo zero di «non ho
// mangiato niente»), contro i 2000 della dieta.
//
// Un pasto saltato senza stima conta zero, ma il suo target resta: il totale corto
// dice che manca un pezzo, e la riga del pasto dice quale.

const VUOTO = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };

// Il pasto saltato con «non ho mangiato niente»: il backend lo salva come una stima
// tutta a zero, senza chiamare il modello.
export const niente = (meal) => meal.eaten_nutrition?.calories === 0;

// Quello che un pasto porta al totale di oggi, e se è una stima.
export function mealContribution(meal) {
  if (meal.is_skipped || meal.is_followed === false) {
    const stima = meal.eaten_nutrition;
    if (!stima) return { ...VUOTO, stimato: false, mancante: true };
    return {
      calories: stima.calories || 0,
      protein_g: stima.protein_g || 0,
      carbs_g: stima.carbs_g || 0,
      fat_g: stima.fat_g || 0,
      // Uno zero non è una stima: è «non ho mangiato niente», un fatto. Contato come
      // stima, la home scriveva «≈ 0 kcal stimate» e «con le stime» su un totale in
      // cui di stimato non c'era niente.
      stimato: !niente(meal),
      mancante: false,
    };
  }
  const r = meal.recipe;
  if (r) {
    return {
      calories: r.calories,
      protein_g: r.protein_g,
      carbs_g: r.carbs_g,
      fat_g: r.fat_g,
      stimato: false,
      mancante: false,
    };
  }
  // «Lo prepari tu» senza ricetta: dato per centrato sul target, come nell'andamento.
  if (meal.self_managed) {
    return { ...VUOTO, calories: meal.target_calories, stimato: false, mancante: false };
  }
  return { ...VUOTO, stimato: false, mancante: false };
}

// Quanto si è mangiato davvero finora: solo i pasti segnati. Un pasto seguito porta il
// suo piatto (700 kcal se il piatto era da 700, anche se il target era 500), uno
// «ho mangiato altro» la sua stima. Quelli non ancora segnati non portano niente:
// prima il numero grande della home era il piano della giornata, e con solo
// colazione e pranzo mangiati diceva già 2000 su 2000.
export function eatenContribution(meal) {
  if (meal.is_followed === null || meal.is_followed === undefined) {
    if (!meal.is_skipped) return null;
  }
  return mealContribution(meal);
}

export function todayTotals(meals) {
  return meals.reduce(
    (somma, meal) => {
      const c = mealContribution(meal);
      const m = eatenContribution(meal);
      return {
        calories: somma.calories + c.calories,
        protein_g: somma.protein_g + c.protein_g,
        carbs_g: somma.carbs_g + c.carbs_g,
        fat_g: somma.fat_g + c.fat_g,
        target: somma.target + (meal.target_calories || 0),
        mangiato: {
          calories: somma.mangiato.calories + (m?.calories || 0),
          protein_g: somma.mangiato.protein_g + (m?.protein_g || 0),
          carbs_g: somma.mangiato.carbs_g + (m?.carbs_g || 0),
          fat_g: somma.mangiato.fat_g + (m?.fat_g || 0),
        },
        // Segnato lo è anche il pasto rimandato: è una risposta come l'altra.
        segnati: somma.segnati + (meal.is_followed === null ? 0 : 1),
        stime: somma.stime + (m?.stimato ? 1 : 0),
        mancanti: somma.mancanti + (c.mancante ? 1 : 0),
      };
    },
    {
      calories: 0,
      protein_g: 0,
      carbs_g: 0,
      fat_g: 0,
      target: 0,
      mangiato: { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
      segnati: 0,
      stime: 0,
      mancanti: 0,
    }
  );
}
