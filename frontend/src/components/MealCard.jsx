import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check,
  ChefHat,
  MoreHorizontal,
  Pencil,
  Pin,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import MacroBar from './MacroBar';

// Card di un incrocio giorno × pasto: sul telefono è una riga alta ~90px, nella
// griglia settimanale una cella incolonnata. Il markup è lo stesso, cambia il verso
// (vedi `.meal-card` in index.css): una card da 215px sul telefono voleva dire due
// pasti e mezzo per schermata, e la giornata non si vedeva mai intera.
//
// Com'è andata si segna da qui — è la cosa che si fa ogni sera, col telefono in mano —
// e le due risposte sono i soli comandi sempre a schermo. Rigenera ed elimina stanno
// dietro il «⋯»: si usano di rado, e in una griglia da 28 caselle quattro icone per
// cella sono centoventi bersagli che nessuno cerca.
export default function MealCard({
  meal,
  skipped,
  busy,
  regenerating,
  onRegenerate,
  onFollowed,
  onDelete,
  style,
}) {
  const { recipe } = meal;
  // Il pasto singolo saltato ("ho mangiato altro") tiene la ricetta scritta ma non
  // conta più: la si mostra spenta, con la sua etichetta.
  const off = skipped || meal.is_skipped;
  const [altro, setAltro] = useState(false);

  return (
    // `style` porta la posizione nella griglia settimanale (riga e colonna): sui
    // monitor stretti il contenitore torna flex e queste proprietà vengono ignorate.
    <div
      className={`meal-card ${meal.is_skipped ? 'skipped' : ''} ${
        meal.is_followed === true ? 'followed' : ''
      } ${meal.is_recurring || meal.self_managed ? 'quiet' : ''}`}
      style={style}
    >
      <Link className="meal-main" to={`/meals/${meal.id}`}>
        {/* Com'è fatta la casella si dice con un segno accanto al nome del pasto:
            prima erano pastiglie in fondo alla card — FISSO, TUO PASTO, TUO — che su
            sette giorni diventavano una parete di etichette tutte uguali. */}
        <div className="meal-slot">
          <span className="meal-slot-name">{meal.slot_name}</span>
          {meal.is_recurring && (
            <Pin className="meal-mark fixed">
              <title>Pasto fisso: si ripete ogni settimana</title>
            </Pin>
          )}
          {meal.self_managed && (
            <ChefHat className="meal-mark mine">
              <title>Questo pasto lo prepari tu</title>
            </ChefHat>
          )}
          {!meal.self_managed && meal.source === 'user_custom' && (
            <Pencil className="meal-mark own">
              <title>Ricetta scelta o scritta da te</title>
            </Pencil>
          )}
        </div>

        {recipe ? (
          <div className="meal-title">{recipe.title}</div>
        ) : off ? (
          // La giornata è saltata: la ricetta si è accodata più avanti, qui non
          // c'è niente da riempire.
          <div className="meal-empty">Giorno saltato</div>
        ) : meal.self_managed ? (
          // Non è una casella vuota da riempire: è un pasto che l'utente ha già
          // risolto per conto suo, e i suoi macro contano nel totale del giorno.
          <div className="meal-empty own">Lo prepari tu</div>
        ) : (
          <div className="meal-empty">Da riempire</div>
        )}

        {/* Numeri e stato sull'ultima riga, appesa in basso: così le celle di una
            stessa riga della griglia allineano i piedi anche se un titolo va a capo. */}
        <div className="meal-foot">
          <span className="meal-facts">
            {recipe
              ? `${recipe.calories} kcal · ${recipe.prep_time_min + recipe.cook_time_min} min`
              : `${meal.target.calories} kcal`}
          </span>
          {recipe && !off && (
            <MacroBar protein={recipe.protein_g} carbs={recipe.carbs_g} fat={recipe.fat_g} />
          )}
          {/* La parola resta, il colore la conferma: è la risposta alla domanda
              "com'è andata?", e si cerca scorrendo la settimana. */}
          {meal.is_followed === true && (
            <span className="meal-state done">
              <Check /> seguito
            </span>
          )}
          {meal.is_skipped && <span className="meal-state moved">rimandato</span>}
        </div>
      </Link>

      {recipe ? (
        <>
          <div className="meal-actions">
            <button
              className={`meal-action ok ${meal.is_followed === true ? 'on' : ''}`}
              title="L'ho seguito"
              disabled={skipped || busy}
              onClick={() => onFollowed(meal, true)}
            >
              <Check />
            </button>
            <button
              className={`meal-action no ${meal.is_followed === false ? 'on' : ''}`}
              title="Ho mangiato altro"
              disabled={skipped || busy}
              onClick={() => onFollowed(meal, false)}
            >
              <X />
            </button>
            <button
              className={`meal-action more ${altro ? 'on' : ''}`}
              title="Altro"
              disabled={busy}
              onClick={() => setAltro((v) => !v)}
            >
              {/* Gira solo se sta davvero rigenerando: mentre si salva "l'ho seguito"
                  la card è occupata lo stesso, ma questa icona direbbe un'altra cosa. */}
              {regenerating ? <RefreshCw className="spinning" /> : <MoreHorizontal />}
            </button>
          </div>

          {altro && (
            <div className="meal-more">
              <button
                className="meal-more-btn"
                disabled={off || busy || meal.self_managed}
                onClick={() => {
                  setAltro(false);
                  onRegenerate(meal);
                }}
              >
                <RefreshCw /> Rigenera
              </button>
              {onDelete && (
                <button
                  className="meal-more-btn danger"
                  disabled={off || busy}
                  onClick={() => {
                    setAltro(false);
                    onDelete(meal);
                  }}
                >
                  <Trash2 /> Elimina
                </button>
              )}
            </div>
          )}
        </>
      ) : (
        // Casella vuota: un solo comando, e dice cosa fa. Prima c'erano le stesse
        // quattro icone delle caselle piene, tre delle quali spente.
        !off &&
        !meal.self_managed && (
          <div className="meal-actions">
            <button className="meal-gen" disabled={busy} onClick={() => onRegenerate(meal)}>
              {regenerating ? <span className="spinner-inline" /> : <Sparkles />}
              Genera
            </button>
          </div>
        )
      )}
    </div>
  );
}
