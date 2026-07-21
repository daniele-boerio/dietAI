import { Link } from 'react-router-dom';
import { Clock, Flame, MessageSquare, Pin, RefreshCw } from 'lucide-react';
import MacroBar from './MacroBar';

// Card di un incrocio giorno × pasto. Mostra sempre lo slot e il target, anche
// quando la casella è vuota: la struttura della dieta si legge prima delle ricette.
export default function MealCard({
  meal,
  locked,
  busy,
  onRegenerate,
  onToggleRecurring,
  style,
}) {
  const { recipe } = meal;

  return (
    // `style` porta la posizione nella griglia settimanale (riga e colonna): sui
    // monitor stretti il contenitore torna flex e queste proprietà vengono ignorate.
    <div className="meal-card" style={style}>
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
        ) : meal.self_managed ? (
          // Non è una casella vuota da riempire: è un pasto che l'utente ha già
          // risolto per conto suo, e i suoi macro contano nel totale del giorno.
          <div className="meal-empty" style={{ fontStyle: 'normal' }}>
            Lo prepari tu · {meal.target.calories} kcal
          </div>
        ) : (
          <div className="meal-empty">
            Da generare · {meal.target.calories} kcal
          </div>
        )}
      </Link>

      {(meal.is_recurring || meal.self_managed || meal.source === 'user_custom') && (
        <div className="meal-flags">
          {meal.self_managed && <span className="meal-flag custom">Tuo pasto</span>}
          {meal.is_recurring && <span className="meal-flag fixed">Fisso</span>}
          {!meal.self_managed && meal.source === 'user_custom' && (
            <span className="meal-flag custom">Tuo</span>
          )}
        </div>
      )}

      <div className="meal-actions">
        <button
          className="meal-action"
          title={
            meal.self_managed
              ? 'Questo pasto lo gestisci tu (cambia in Impostazioni → La mia dieta)'
              : locked
                ? 'Piano bloccato'
                : 'Rigenera'
          }
          disabled={locked || busy || meal.self_managed}
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
