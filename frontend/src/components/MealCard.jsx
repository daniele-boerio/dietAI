import { Link } from 'react-router-dom';
import { Check, Clock, Flame, RefreshCw, X } from 'lucide-react';
import MacroBar from './MacroBar';

// Card di un incrocio giorno × pasto. Mostra sempre lo slot e il target, anche
// quando la casella è vuota: la struttura della dieta si legge prima delle ricette.
//
// In fondo ci stanno le tre cose che si fanno davanti alla griglia: cambiare il
// piatto e dire com'è andata. Chat e "rendi fisso" stanno dentro il dettaglio, che è
// a un tocco sulla card: da qui servivano di rado, e occupavano il posto di quello
// che invece si preme ogni sera.
export default function MealCard({
  meal,
  skipped,
  busy,
  regenerating,
  onRegenerate,
  onFollowed,
  style,
}) {
  const { recipe } = meal;
  // Il pasto singolo saltato ("ho mangiato altro") tiene la ricetta scritta ma non
  // conta più: la si mostra spenta, con la sua etichetta.
  const off = skipped || meal.is_skipped;

  return (
    // `style` porta la posizione nella griglia settimanale (riga e colonna): sui
    // monitor stretti il contenitore torna flex e queste proprietà vengono ignorate.
    <div className={`meal-card ${meal.is_skipped ? 'skipped' : ''}`} style={style}>
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
        ) : off ? (
          // La giornata è saltata: la ricetta si è accodata più avanti, qui non
          // c'è niente da riempire.
          <div className="meal-empty">Giorno saltato</div>
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

      {(meal.is_skipped ||
        meal.is_recurring ||
        meal.self_managed ||
        meal.source === 'user_custom') && (
        <div className="meal-flags">
          {meal.is_skipped && <span className="meal-flag skipped">Saltato</span>}
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
              ? 'Questo pasto lo gestisci tu (cambia da "La mia dieta")'
              : meal.is_skipped
                ? 'Pasto saltato: la ricetta è stata rimandata più avanti'
                : skipped
                  ? 'Giornata saltata: le sue ricette si sono accodate più avanti'
                  : 'Rigenera'
          }
          disabled={off || busy || meal.self_managed}
          onClick={() => onRegenerate(meal)}
        >
          {/* Gira solo se sta davvero rigenerando: mentre si salva "l'ho seguito"
              la card è occupata lo stesso, ma questa icona direbbe un'altra cosa. */}
          <RefreshCw className={regenerating ? 'spinning' : ''} />
        </button>

        {/* Com'è andata si segna da qui, senza aprire il pasto: è la cosa che si fa
            ogni sera, di solito col telefono in mano. Restano premibili anche sulle
            settimane passate — il tracking è proprio ciò per cui ci si torna — e su
            un pasto già rimandato, dove "l'ho seguito" annulla il rinvio. */}
        <button
          className={`meal-action ok ${meal.is_followed === true ? 'on' : ''}`}
          title="L'ho seguito"
          disabled={!recipe || skipped || busy}
          onClick={() => onFollowed(meal, true)}
        >
          <Check />
        </button>
        <button
          className={`meal-action no ${meal.is_followed === false ? 'on' : ''}`}
          title="Ho mangiato altro"
          disabled={!recipe || skipped || busy}
          onClick={() => onFollowed(meal, false)}
        >
          <X />
        </button>
      </div>
    </div>
  );
}
