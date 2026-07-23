import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  CalendarOff,
  Check,
  Heart,
  Lock,
  Pin,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import MealChat from '../components/MealChat';
import RecipeView from '../components/RecipeView';
import StarRating from '../components/StarRating';

export default function MealDetailPage() {
  const { mealId } = useParams();
  const { addToast } = useApp();
  const navigate = useNavigate();
  const [meal, setMeal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [substituting, setSubstituting] = useState(false);
  const [substitution, setSubstitution] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [picker, setPicker] = useState(false);

  const load = useCallback(async () => {
    try {
      setMeal(await api.getMeal(mealId));
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [mealId, addToast]);

  useEffect(() => {
    load();
  }, [load]);

  const regenerate = async () => {
    setBusy(true);
    try {
      setMeal(await api.regenerateMeal(mealId));
      addToast('Nuova ricetta pronta ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const rate = async (rating) => {
    try {
      await api.rateRecipe(meal.recipe.id, rating);
      setMeal((m) => ({ ...m, recipe: { ...m.recipe, rating } }));
      addToast('Voto salvato — ne terrò conto la prossima volta ✓');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const toggleFavorite = async () => {
    try {
      const next = !meal.recipe.is_favorite;
      await api.favoriteRecipe(meal.recipe.id, next);
      setMeal((m) => ({ ...m, recipe: { ...m.recipe, is_favorite: next } }));
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const toggleRecurring = async () => {
    try {
      setMeal(await api.setRecurring(mealId, !meal.is_recurring));
      addToast(meal.is_recurring ? 'Non è più fisso' : 'Pasto fisso ogni settimana ✓');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const setFollowed = async (value) => {
    try {
      const updated = await api.setFollowed(mealId, value);
      setMeal(updated);
      // "Ho mangiato altro" non è solo un appunto: il piatto si sposta, e dove è
      // finito va detto subito o l'utente lo cerca dov'era.
      if (updated.moved_to) {
        addToast(
          `Ricetta rimandata a ${updated.moved_to.day_name.toLowerCase()}` +
            (updated.moved_to.next_week ? ' della settimana prossima' : '')
        );
      } else if (value) {
        addToast('Rimessa al suo posto ✓');
      }
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const substitute = async (ingredient) => {
    setSubstituting(true);
    try {
      const result = await api.substituteIngredient(meal.recipe.id, ingredient.name, null);
      setSubstitution(result);
      await load();
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setSubstituting(false);
    }
  };

  const clearMeal = async () => {
    try {
      setMeal(await api.clearMeal(mealId));
      setConfirmClear(false);
      addToast('Casella svuotata');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  if (loading) return <div className="spinner" />;
  if (!meal) return null;

  const locked = meal.week.is_locked;
  // Un giorno saltato è in sola lettura come un piano bloccato, ma per il motivo
  // opposto: lì il cibo è già comprato, qui non lo è mai stato.
  const skipped = meal.day_is_skipped;
  const frozen = locked || skipped || meal.is_skipped;

  return (
    <>
      <div className="page-header">
        <div>
          <button className="btn btn-ghost" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Indietro
          </button>
          <h1 className="page-title" style={{ marginTop: 6 }}>
            {meal.slot_name} · {meal.day_name}
          </h1>
          <p className="page-subtitle">
            {formatDate(meal.date, { weekday: 'long', day: 'numeric', month: 'long' })} ·
            target {meal.target.calories} kcal
            {meal.target.notes ? ` · ${meal.target.notes}` : ''}
          </p>
        </div>

        <div className="page-actions">
          {meal.recipe && (
            <>
              <button
                className={`btn btn-secondary ${meal.recipe.is_favorite ? 'active' : ''}`}
                onClick={toggleFavorite}
                title="Aggiungi ai preferiti"
              >
                <Heart
                  size={16}
                  fill={meal.recipe.is_favorite ? 'currentColor' : 'none'}
                  color={meal.recipe.is_favorite ? 'var(--terracotta)' : 'currentColor'}
                />
                Preferita
              </button>
              <button
                className="btn btn-secondary"
                onClick={toggleRecurring}
                disabled={frozen}
                title="Ripeti questo pasto ogni settimana"
              >
                <Pin size={16} color={meal.is_recurring ? 'var(--accent)' : 'currentColor'} />
                {meal.is_recurring ? 'Fisso' : 'Rendi fisso'}
              </button>
            </>
          )}
          <button className="btn btn-primary" onClick={regenerate} disabled={busy || frozen}>
            {busy ? <span className="spinner-inline" /> : <RefreshCw size={16} />}
            Rigenera
          </button>
        </div>
      </div>

      {locked && (
        <div className="notice notice-lock">
          <Lock />
          <div>
            <strong>Piano bloccato.</strong> Puoi votare la ricetta e chiedere consigli in
            chat, ma non modificarla: gli ingredienti sono già stati comprati.
          </div>
        </div>
      )}

      {skipped && !locked && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>Giorno saltato.</strong> È passato senza che la spesa fosse fatta:
            quello che c'era in piano è slittato ai giorni successivi, e qui non c'è più
            niente da cambiare.
          </div>
        </div>
      )}

      {meal.is_skipped && !skipped && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>Pasto saltato.</strong> Hai segnato di aver mangiato altro: la ricetta
            qui sotto resta per memoria, ma è stata rimandata alla prima casella libera di
            questo pasto. Se invece l'hai cucinata, premi "L'ho seguito" e torna al suo
            posto.
          </div>
        </div>
      )}

      <div className="detail-layout">
        <div>
          {meal.recipe ? (
            <>
              <RecipeView
                recipe={meal.recipe}
                target={meal.target}
                onSubstitute={frozen ? null : substitute}
                substituting={substituting}
              />

              <div className="card" style={{ marginTop: 14 }}>
                <div className="card-title">Com'è andata?</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <button
                    className={`btn btn-sm ${
                      meal.is_followed === true ? 'btn-primary' : 'btn-secondary'
                    }`}
                    onClick={() => setFollowed(true)}
                  >
                    <Check size={14} /> L'ho seguito
                  </button>
                  <button
                    className={`btn btn-sm ${
                      meal.is_followed === false ? 'btn-danger' : 'btn-secondary'
                    }`}
                    onClick={() => setFollowed(false)}
                  >
                    <X size={14} /> Ho mangiato altro
                  </button>
                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      Voto
                    </span>
                    <StarRating value={meal.recipe.rating} onChange={rate} />
                  </div>
                </div>

                {!frozen && (
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ marginTop: 12 }}
                    onClick={() => setConfirmClear(true)}
                  >
                    <Trash2 size={14} /> Svuota questa casella
                  </button>
                )}
              </div>
            </>
          ) : (
            <EmptyState
              icon={RefreshCw}
              title="Nessuna ricetta per questo pasto"
              text={`Target: ${meal.target.calories} kcal, proteine ${meal.target.protein_g}g, carboidrati ${meal.target.carbs_g}g, grassi ${meal.target.fat_g}g.`}
              action={
                <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                  <button className="btn btn-primary" onClick={regenerate} disabled={busy || frozen}>
                    {busy && <span className="spinner-inline" />}
                    Generala con l'AI
                  </button>
                  <button className="btn btn-secondary" onClick={() => setPicker(true)}>
                    Scegli dal ricettario
                  </button>
                </div>
              }
            />
          )}
        </div>

        <MealChat
          mealId={meal.id}
          locked={frozen}
          onRecipeUpdated={(recipe) => setMeal((m) => ({ ...m, recipe }))}
        />
      </div>

      {substitution && (
        <div className="modal-overlay" onClick={() => setSubstitution(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Ingrediente sostituito</h2>
            <p className="modal-text">
              <strong>{substitution.original?.name}</strong> →{' '}
              <strong>{substitution.substitute?.name}</strong>{' '}
              ({substitution.substitute?.quantity} {substitution.substitute?.unit})
              <br />
              <br />
              {substitution.explanation}
            </p>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => setSubstitution(null)}>
                Ho capito
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmClear && (
        <ConfirmDialog
          title="Svuotare la casella?"
          text="La ricetta resta nel ricettario, ma questo pasto tornerà vuoto."
          confirmLabel="Svuota"
          danger
          onConfirm={clearMeal}
          onCancel={() => setConfirmClear(false)}
        />
      )}

      {picker && (
        <RecipePicker
          onCancel={() => setPicker(false)}
          onPick={async (recipeId) => {
            try {
              setMeal(await api.assignMeal(mealId, { recipe_id: recipeId }));
              setPicker(false);
              addToast('Ricetta assegnata ✓');
            } catch (e) {
              addToast(e.message, 'error');
            }
          }}
        />
      )}
    </>
  );
}

function RecipePicker({ onPick, onCancel }) {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const t = setTimeout(() => {
      api.getRecipes({ search, per_page: 30 }).then((d) => setItems(d.items)).catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal modal-lg" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">Scegli dal ricettario</h2>
        <input
          type="text"
          placeholder="Cerca..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        <div className="list-rows" style={{ maxHeight: 380, overflowY: 'auto' }}>
          {items.map((r) => (
            <div key={r.id} className="list-row">
              <div className="list-row-main">
                <strong>{r.title}</strong>
                <span>
                  {r.calories} kcal · P {r.protein_g}g · C {r.carbs_g}g · G {r.fat_g}g
                </span>
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => onPick(r.id)}>
                Scegli
              </button>
            </div>
          ))}
          {items.length === 0 && (
            <p className="field-hint">Nessuna ricetta trovata.</p>
          )}
        </div>
        <div className="modal-actions" style={{ marginTop: 16 }}>
          <button className="btn btn-secondary" onClick={onCancel}>
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}
