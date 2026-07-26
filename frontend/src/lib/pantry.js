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
