import MealCard from './MealCard';

const todayIso = () => new Date().toISOString().slice(0, 10);

// Sui monitor larghi la settimana è una griglia vera a due dimensioni: sette colonne
// (i giorni) per N righe (i pasti). Il CSS scioglie le colonne con `display: contents`
// e ogni cella dichiara la propria riga, così i pranzi stanno tutti sulla stessa linea
// anche quando un piatto ha il nome lungo il doppio degli altri.
//
// Sotto i 1100px le colonne diventerebbero troppo strette: lì il CSS rimette ogni
// giorno come blocco a sé, dove l'allineamento fra giorni non serve più.
export default function WeekGrid({ week, busyMealId, onRegenerate, onToggleRecurring }) {
  const today = todayIso();

  return (
    <div className="week-grid">
      {week.days.map((day, dayIndex) => {
        const column = dayIndex + 1;
        const isToday = day.date === today;

        return (
          <div key={day.id} className={`day-column ${isToday ? 'today' : ''}`}>
            <div className="day-head" style={{ gridColumn: column, gridRow: 1 }}>
              <div className="day-name">{day.day_name}</div>
              <div className="day-date">
                {new Date(day.date).toLocaleDateString('it-IT', {
                  day: 'numeric',
                  month: 'short',
                })}
              </div>
            </div>

            {day.meals.map((meal, mealIndex) => (
              <MealCard
                key={meal.id}
                meal={meal}
                locked={week.is_locked}
                busy={busyMealId === meal.id}
                onRegenerate={onRegenerate}
                onToggleRecurring={onToggleRecurring}
                style={{ gridColumn: column, gridRow: mealIndex + 2 }}
              />
            ))}

            <div
              className="day-total"
              style={{ gridColumn: column, gridRow: day.meals.length + 2 }}
            >
              {day.totals.calories} / {day.totals.target_calories} kcal
            </div>
          </div>
        );
      })}
    </div>
  );
}
