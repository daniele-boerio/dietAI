// Un pallino per pasto: com'è andata una giornata, in quattordici pixel.
//
// Serve in due posti che devono dire la stessa cosa — l'intestazione del giorno nella
// griglia e la striscia dei sette giorni in cima al piano sul telefono — ed è lì che
// guadagna: la settimana si legge senza scorrerla, che era il motivo per cui bisognava
// arrivare in fondo alla pagina per sapere se sabato era stato tracciato.

export function statoPasto(meal) {
  // "Ho mangiato altro" mette `is_skipped`: il piatto è stato rimandato altrove.
  if (meal.is_skipped) return 'moved';
  if (meal.is_followed === true) return 'done';
  return meal.recipe ? 'planned' : 'empty';
}

const PAROLE = {
  done: ['seguito', 'seguiti'],
  moved: ['rimandato', 'rimandati'],
  planned: ['in programma', 'in programma'],
  empty: ['da generare', 'da generare'],
};

// Lo stesso riassunto a parole, per chi non vede i colori (o non vede): lime,
// terracotta e grigio su cinque pixel erano l'unico modo di saperlo.
export function riassuntoGiorno(day) {
  if (day.is_skipped) return 'giornata saltata';
  const conti = {};
  day.meals.forEach((m) => {
    const s = statoPasto(m);
    conti[s] = (conti[s] || 0) + 1;
  });
  return Object.entries(PAROLE)
    .filter(([s]) => conti[s])
    .map(([s, [uno, tanti]]) => `${conti[s]} ${conti[s] === 1 ? uno : tanti}`)
    .join(', ');
}

export default function DayDots({ day }) {
  return (
    <span
      className={`day-dots ${day.is_skipped ? 'off' : ''}`}
      role="img"
      aria-label={riassuntoGiorno(day)}
    >
      {day.meals.map((meal) => (
        <i key={meal.id} className={`day-dot ${statoPasto(meal)}`} />
      ))}
    </span>
  );
}
