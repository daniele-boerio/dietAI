import { CalendarOff, Undo2 } from 'lucide-react';
import MealCard from './MealCard';

const todayIso = () => new Date().toISOString().slice(0, 10);

// Sui monitor larghi la settimana è una griglia vera a due dimensioni: sette colonne
// (i giorni) per N righe (i pasti). Il CSS scioglie le colonne con `display: contents`
// e ogni cella dichiara la propria riga, così i pranzi stanno tutti sulla stessa linea
// anche quando un piatto ha il nome lungo il doppio degli altri.
//
// Sotto i 1100px le colonne diventerebbero troppo strette: lì il CSS rimette ogni
// giorno come blocco a sé, dove l'allineamento fra giorni non serve più.
export default function WeekGrid({
  week,
  busyMealId,
  busyDayId,
  onRegenerate,
  onToggleRecurring,
  onToggleDaySkip,
}) {
  const today = todayIso();

  return (
    <div className="week-grid">
      {week.days.map((day, dayIndex) => {
        const column = dayIndex + 1;
        const isToday = day.date === today;
        // I giorni passati li salta il piano da sé quando manca la spesa, e lì le
        // ricette slittano invece di accodarsi: a mano si tocca solo da oggi in poi.
        // A piano bloccato resta possibile: il cibo è comprato, ma se sei fuori a
        // cena quel piatto lo cucini un altro giorno.
        const canSkip = onToggleDaySkip && day.date >= today;

        return (
          <div
            key={day.id}
            className={`day-column ${isToday ? 'today' : ''} ${
              day.is_skipped ? 'skipped' : ''
            }`}
          >
            <div className="day-head" style={{ gridColumn: column, gridRow: 1 }}>
              <div className="day-name">{day.day_name}</div>
              <div className="day-date">
                {day.is_skipped
                  ? 'Saltato'
                  : new Date(day.date).toLocaleDateString('it-IT', {
                      day: 'numeric',
                      month: 'short',
                    })}
              </div>
              {canSkip && (
                <button
                  className="day-skip"
                  title={
                    day.is_skipped
                      ? 'Rimetti in programma questa giornata'
                      : 'Salta la giornata: le ricette si accodano ai giorni dopo'
                  }
                  disabled={busyDayId === day.id}
                  onClick={() => onToggleDaySkip(day)}
                >
                  {day.is_skipped ? <Undo2 /> : <CalendarOff />}
                </button>
              )}
            </div>

            {day.meals.map((meal, mealIndex) => (
              <MealCard
                key={meal.id}
                meal={meal}
                locked={week.is_locked}
                skipped={day.is_skipped}
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
              {day.is_skipped
                ? '—'
                : `${day.totals.calories} / ${day.totals.target_calories} kcal`}
            </div>
          </div>
        );
      })}
    </div>
  );
}
