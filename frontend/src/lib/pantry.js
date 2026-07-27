/**
 * Il messaggio che dice cosa è appena uscito dalla dispensa.
 *
 * Cucinare la consuma, e una scorta che cala di nascosto è una scorta di cui non ci
 * si fida più: chi segna "l'ho seguito" deve vedere sparire il pesce spada. Oltre tre
 * nomi la frase non si legge, quindi si conta e basta.
 *
 * Sta qui e non in una pagina perché lo usano sia la home sia il dettaglio del pasto.
 */
export function scalatiDallaDispensa(used) {
  if (!used?.length) return '';
  if (used.length > 3) return `Tolti dalla dispensa ${used.length} ingredienti`;
  return `Tolti dalla dispensa: ${used.map((u) => `${u.name} (${u.label})`).join(', ')}`;
}

const MOTIVI = {
  assente: () => 'non è in dispensa',
  senza_quantita: () => 'in dispensa senza quantità',
  // È il caso che si sistema in dieci secondi, ma solo se si sa qual è: la scorta è
  // contata a unità e la ricetta pesa in grammi, o viceversa.
  unita: (s) => `dispensa in ${s.pantry_unit}, ricetta in ${s.recipe_unit}`,
  quantita_ricetta: () => 'la ricetta non dice quanto',
};

/**
 * Il messaggio per quando "l'ho seguito" non ha scalato niente.
 *
 * Senza, la dispensa resta ferma e il pulsante sembra rotto: il motivo però c'è
 * sempre, ed è quasi sempre qualcosa che si può correggere dalla dispensa. Due nomi
 * bastano — è un avviso, non un rapporto.
 */
export function nonScalatiDallaDispensa(skipped) {
  if (!skipped?.length) return '';
  const primi = skipped
    .slice(0, 2)
    .map((s) => `${s.name} (${(MOTIVI[s.reason] || (() => 'non scalabile'))(s)})`);
  const resto = skipped.length - primi.length;
  return `Dispensa invariata — ${primi.join(', ')}${resto > 0 ? ` e altri ${resto}` : ''}`;
}
