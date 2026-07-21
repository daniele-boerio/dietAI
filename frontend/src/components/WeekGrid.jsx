import MealCard from './MealCard';

const todayIso = () => new Date().toISOString().slice(0, 10);

// Sette colonne su desktop; sotto i 1000px il CSS le fa scorrere come schede di
// giorno, così su telefono si legge un giorno alla volta senza zoom.
export default function WeekGrid({ week, busyMealId, onRegenerate, onToggleRecurring }) {
  const today = todayIso();

  return (
    <div className="week-grid">
      {week.days.map((day) => (
        <div key={day.id} className={`day-column ${day.date === today ? 'today' : ''}`}>
          <div className="day-head">
            <div className="day-name">{day.day_name}</div>
            <div className="day-date">
              {new Date(day.date).toLocaleDateString('it-IT', {
                day: 'numeric',
                month: 'short',
              })}
            </div>
          </div>

          {day.meals.map((meal) => (
            <MealCard
              key={meal.id}
              meal={meal}
              locked={week.is_locked}
              busy={busyMealId === meal.id}
              onRegenerate={onRegenerate}
              onToggleRecurring={onToggleRecurring}
            />
          ))}

          <div className="day-total">
            {day.totals.calories} / {day.totals.target_calories} kcal
          </div>
        </div>
      ))}
    </div>
  );
}
