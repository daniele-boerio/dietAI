import { Link } from 'react-router-dom';
import { Clock, Flame, MessageSquare, Pin, RefreshCw } from 'lucide-react';
import MacroBar from './MacroBar';

// Card di un incrocio giorno × pasto. Mostra sempre lo slot e il target, anche
// quando la casella è vuota: la struttura della dieta si legge prima delle ricette.
export default function MealCard({ meal, locked, busy, onRegenerate, onToggleRecurring }) {
  const { recipe } = meal;

  return (
    <div className="meal-card">
      <Link to={`/meals/${meal.id}`} style={{ display: 'contents' }}>
        <div className="meal-slot">{meal.slot_name}</div>

        {recipe ? (
          <>
            <div className="meal-title">{recipe.title}</div>
            <div className="meal-meta">
              <span>
                <Flame /> {recipe.calories} kcal
              </span>
              <span>
                <Clock /> {recipe.prep_time_min + recipe.cook_time_min} min
              </span>
            </div>
            <MacroBar
              protein={recipe.protein_g}
              carbs={recipe.carbs_g}
              fat={recipe.fat_g}
            />
          </>
        ) : (
          <div className="meal-empty">
            Da generare · {meal.target.calories} kcal
          </div>
        )}
      </Link>

      {(meal.is_recurring || meal.source === 'user_custom') && (
        <div className="meal-flags">
          {meal.is_recurring && <span className="meal-flag fixed">Fisso</span>}
          {meal.source === 'user_custom' && <span className="meal-flag custom">Tuo</span>}
        </div>
      )}

      <div className="meal-actions">
        <button
          className="meal-action"
          title={locked ? 'Piano bloccato' : 'Rigenera'}
          disabled={locked || busy}
          onClick={() => onRegenerate(meal)}
        >
          <RefreshCw className={busy ? 'spinning' : ''} />
        </button>
        <Link className="meal-action" to={`/meals/${meal.id}`} title="Chat e dettaglio">
          <MessageSquare />
        </Link>
        <button
          className={`meal-action ${meal.is_recurring ? 'on' : ''}`}
          title={meal.is_recurring ? 'Non è più fisso' : 'Rendi fisso ogni settimana'}
          disabled={!recipe}
          onClick={() => onToggleRecurring(meal)}
        >
          <Pin />
        </button>
      </div>
    </div>
  );
}
