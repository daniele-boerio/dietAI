import { Clock, Flame, Replace, UtensilsCrossed } from 'lucide-react';
import { formatNumber } from '../api';
import MacroBar from './MacroBar';

const DIFFICULTY = { easy: 'Facile', medium: 'Media', hard: 'Impegnativa' };

function Nutrient({ label, value, target, unit = 'g' }) {
  // Lo scarto dal target è l'informazione utile: la dieta dà una tolleranza, non un
  // numero esatto, quindi si mostra quanto ci si discosta.
  const delta = target != null ? value - target : null;
  return (
    <div className="nutrition-cell">
      <div className="nutrition-value">
        {unit === 'kcal' ? Math.round(value) : formatNumber(value, 1)}
        <span style={{ fontSize: '0.75rem', fontWeight: 400 }}> {unit}</span>
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

export default function RecipeView({ recipe, target, onSubstitute, substituting }) {
  if (!recipe) return null;

  return (
    <div>
      <div className="recipe-head">
        <h1 className="recipe-title">{recipe.title}</h1>
        {recipe.description && <p className="recipe-description">{recipe.description}</p>}
        <div className="recipe-badges">
          <span className="badge">
            <Clock size={12} /> {recipe.prep_time_min} min prep
          </span>
          {recipe.cook_time_min > 0 && (
            <span className="badge">
              <Flame size={12} /> {recipe.cook_time_min} min cottura
            </span>
          )}
          <span className="badge">{DIFFICULTY[recipe.difficulty] || 'Media'}</span>
          {recipe.tags?.type && <span className="badge badge-accent">{recipe.tags.type}</span>}
          {recipe.is_custom && <span className="badge badge-terracotta">Ricetta tua</span>}
        </div>
      </div>

      <div className="nutrition-grid">
        <Nutrient label="Calorie" value={recipe.calories} target={target?.calories} unit="kcal" />
        <Nutrient label="Proteine" value={recipe.protein_g} target={target?.protein_g} />
        <Nutrient label="Carboidrati" value={recipe.carbs_g} target={target?.carbs_g} />
        <Nutrient label="Grassi" value={recipe.fat_g} target={target?.fat_g} />
      </div>

      <MacroBar protein={recipe.protein_g} carbs={recipe.carbs_g} fat={recipe.fat_g} legend />

      <div className="card" style={{ marginTop: 22 }}>
        <div className="card-title">
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

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-title">Procedimento</div>
        <div className="instructions">{recipe.instructions}</div>
      </div>
    </div>
  );
}
