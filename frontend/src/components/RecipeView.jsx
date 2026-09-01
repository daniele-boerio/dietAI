import { Clock, Flame, Replace, UtensilsCrossed } from 'lucide-react';
import { formatNumber } from '../api';
import MacroBar from './MacroBar';

const DIFFICULTY = { easy: 'Facile', medium: 'Media', hard: 'Impegnativa' };

function Nutrient({ label, value, target, unit = 'g', tinta }) {
  // Lo scarto dal target è l'informazione utile: la dieta dà una tolleranza, non un
  // numero esatto, quindi si mostra quanto ci si discosta.
  const delta = target != null ? value - target : null;
  return (
    <div className="nutrition-cell">
      <div className="nutrition-value" style={tinta ? { color: tinta } : undefined}>
        {unit === 'kcal' ? Math.round(value) : formatNumber(value, 1)}
        <span className="nutrition-unit"> {unit}</span>
      </div>
      <div className="nutrition-label">{label}</div>
      {target != null && (
        <div className="nutrition-target">
          target {unit === 'kcal' ? Math.round(target) : formatNumber(target, 1)}
          {delta != null && Math.abs(delta) >= 1 && (
            <> · {delta > 0 ? '+' : ''}{formatNumber(delta, 0)}</>
          )}
        </div>
      )}
    </div>
  );
}

// Il procedimento arriva dal modello come testo, «un passo per riga» e già numerato
// (vedi `prompts.py`). Qui il numero si stacca dalla riga e diventa la cifra in
// colonna: è la stessa informazione, ma il passo comincia sempre allo stesso punto
// e si ritrova il segno dove si era rimasti mentre si cucina. Se le righe non sono
// numerate — un modello che scrive a modo suo — non si inventa niente: il testo
// resta com'è, a capo compresi.
function passi(testo) {
  const righe = (testo || '')
    .split('\n')
    .map((r) => r.trim())
    .filter(Boolean);
  if (righe.length < 2) return null;
  const spezzate = righe.map((r) => r.match(/^(\d{1,2})\s*[.)°-]?\s+(.+)$/));
  if (spezzate.some((m) => !m)) return null;
  return spezzate.map((m) => ({ n: m[1], testo: m[2] }));
}

/**
 * La ricetta.
 *
 * È il foglio che si tiene aperto sul piano mentre si cucina: la fascia del piatto,
 * il titolo, i numeri, e poi ingredienti e procedimento in due colonne.
 *
 * Tre parti si passano da fuori, perché cambiano col posto da cui si guarda la
 * ricetta — dal piano è un pasto di un giorno preciso, dal ricettario è un piatto e
 * basta:
 *  - `eyebrow`: la riga di contesto sopra il titolo («Pranzo di lunedì 1 settembre»)
 *  - `azioni`: la riga in fondo al foglio (com'è andata, rigenera, preferita)
 *  - `indietro`: il tondo in alto a sinistra sulla fascia del piatto
 *  - `preferita`: il tondo in alto a destra, sulla stessa fascia
 */
export default function RecipeView({
  recipe,
  target,
  onSubstitute,
  substituting,
  eyebrow,
  azioni,
  indietro,
  preferita,
}) {
  if (!recipe) return null;

  const elenco = passi(recipe.instructions);
  const minuti = (recipe.prep_time_min || 0) + (recipe.cook_time_min || 0);

  return (
    <div className="recipe-sheet card">
      {/* La fascia in cima non è una fotografia e non finge di esserlo: è un
          segnaposto dichiarato — il riquadro con l'icona delle posate — che tiene il
          posto all'immagine senza far sembrare rotta la pagina finché non c'è. */}
      <div className="recipe-hero dish">
        <UtensilsCrossed />
        {indietro}
        {preferita}
      </div>

      <div className="recipe-sheet-body">
        <div className="recipe-head">
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h1 className="recipe-title">{recipe.title}</h1>
          {recipe.description && <p className="recipe-description">{recipe.description}</p>}
          <div className="recipe-badges">
            <span className="badge badge-ink">
              {recipe.calories} kcal
              {target?.calories ? ` · target ${Math.round(target.calories)}` : ''}
            </span>
            <span className="badge">
              <Clock size={12} /> {minuti} min
            </span>
            <span className="badge">{DIFFICULTY[recipe.difficulty] || 'Media'}</span>
            {recipe.cook_time_min > 0 && (
              <span className="badge">
                <Flame size={12} /> {recipe.cook_time_min} min di cottura
              </span>
            )}
            {recipe.tags?.type && <span className="badge badge-accent">{recipe.tags.type}</span>}
            {recipe.is_custom && <span className="badge badge-terracotta">Ricetta tua</span>}
          </div>
        </div>

        {/* I tre macro, ognuno del colore che quel macro ha in tutta l'app. Le calorie
            non sono qui ma nella pastiglia lì sopra: sono il numero che si confronta
            col target del pasto, non uno dei tre pesi che si dividono il piatto. */}
        <div className="nutrition-grid">
          <Nutrient
            label="Proteine"
            value={recipe.protein_g}
            target={target?.protein_g}
            tinta="var(--macro-p)"
          />
          <Nutrient
            label="Carboidrati"
            value={recipe.carbs_g}
            target={target?.carbs_g}
            tinta="var(--macro-c)"
          />
          <Nutrient
            label="Grassi"
            value={recipe.fat_g}
            target={target?.fat_g}
            tinta="var(--macro-f)"
          />
        </div>

        <MacroBar protein={recipe.protein_g} carbs={recipe.carbs_g} fat={recipe.fat_g} />

        {/* Ingredienti e procedimento sono due colonne dello stesso foglio, non due
            riquadri impilati: si leggono insieme — «quanto farro» mentre si è al passo
            che dice di lessarlo — e uno sotto l'altro obbligavano a risalire la pagina
            a ogni passo. Sotto i 900px tornano in colonna, che è l'unico modo. */}
        <div className="recipe-body">
          <div className="recipe-col">
            <div className="eyebrow">
              <UtensilsCrossed /> Ingredienti · per 1 persona
            </div>
            <ul className="ingredient-list">
              {(recipe.ingredients || []).map((ing) => (
                <li key={ing.id} className="ingredient-row">
                  <span className="ingredient-name">
                    {ing.name}
                    {ing.notes && <small> · {ing.notes}</small>}
                  </span>
                  <span className="ingredient-qty">
                    {formatNumber(ing.quantity, ing.quantity % 1 === 0 ? 0 : 1)} {ing.unit}
                  </span>
                  {onSubstitute && (
                    <button
                      className="icon-button"
                      title="Sostituisci questo ingrediente"
                      disabled={substituting}
                      onClick={() => onSubstitute(ing)}
                    >
                      <Replace size={15} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="recipe-col">
            <div className="eyebrow">Procedimento</div>
            {elenco ? (
              <ol className="steps">
                {elenco.map((passo) => (
                  <li key={passo.n}>
                    <span className="step-n">{passo.n}</span>
                    <span>{passo.testo}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="instructions">{recipe.instructions}</div>
            )}
          </div>
        </div>

        {/* In fondo al foglio, dopo il procedimento: è il punto della pagina in cui
            ci si trova quando il piatto è cucinato, ed è lì che si risponde. */}
        {azioni && <div className="recipe-actions">{azioni}</div>}
      </div>
    </div>
  );
}
