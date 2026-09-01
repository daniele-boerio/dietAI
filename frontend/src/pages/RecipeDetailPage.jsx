import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Heart, Trash2 } from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import LoadError from '../components/LoadError';
import RecipeView from '../components/RecipeView';
import StarRating from '../components/StarRating';
import { useGoBack } from '../lib/navigation';

export default function RecipeDetailPage() {
  const { recipeId } = useParams();
  const { addToast } = useApp();
  const navigate = useNavigate();
  const tornaIndietro = useGoBack('/recipes');
  const [recipe, setRecipe] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api
      .getRecipe(recipeId)
      .then((r) => {
        setRecipe(r);
        setError(null);
      })
      .catch((e) => {
        setError(e.message);
        addToast(e.message, 'error');
      })
      .finally(() => setLoading(false));
  }, [recipeId, addToast]);

  useEffect(() => {
    load();
  }, [load]);

  const rate = async (rating) => {
    await api.rateRecipe(recipe.id, rating);
    setRecipe((r) => ({ ...r, rating }));
    addToast('Voto salvato ✓');
  };

  const toggleFavorite = async () => {
    const next = !recipe.is_favorite;
    await api.favoriteRecipe(recipe.id, next);
    setRecipe((r) => ({ ...r, is_favorite: next }));
  };

  const remove = async () => {
    try {
      await api.deleteRecipe(recipe.id);
      addToast('Ricetta eliminata');
      navigate('/recipes');
    } catch (e) {
      addToast(e.message, 'error');
      setConfirmDelete(false);
    }
  };

  if (loading) return <div className="spinner" />;
  if (!recipe) return <LoadError message={error} onRetry={load} />;

  return (
    <>
      {/* Qui la ricetta è tutta la pagina: il titolo è sul foglio, l'indietro è sul
          foglio e i comandi del piatto sono in fondo al foglio. Una testata sopra
          direbbe una seconda volta le stesse cose. */}
      <div className="page-split" style={{ '--aside': '340px' }}>
        <div className="page-main">
          <RecipeView
            recipe={recipe}
            indietro={
              <button className="recipe-back" onClick={tornaIndietro} title="Indietro">
                <ArrowLeft />
              </button>
            }
            azioni={
              <>
                <div className="andata-rating">
                  <span>Voto</span>
                  <StarRating value={recipe.rating} onChange={rate} />
                </div>
                <button className="btn btn-secondary spinta" onClick={toggleFavorite}>
                  <Heart
                    size={16}
                    fill={recipe.is_favorite ? 'currentColor' : 'none'}
                    color={recipe.is_favorite ? 'var(--terracotta)' : 'currentColor'}
                  />
                  {recipe.is_favorite ? 'Preferita' : 'Aggiungi ai preferiti'}
                </button>
                <button
                  className="btn btn-secondary btn-icon"
                  onClick={() => setConfirmDelete(true)}
                  title="Elimina la ricetta"
                >
                  <Trash2 size={16} />
                </button>
              </>
            }
          />
        </div>

        <aside className="page-aside">
        {recipe.usage_history?.length > 0 && (
          <div className="card">
            <div className="card-title">Quando l'hai mangiata</div>
            <div className="list-rows">
              {recipe.usage_history.map((u) => (
                <div key={u.meal_id} className="list-row">
                  <div className="list-row-main">
                    <strong>{u.day_name}</strong>
                    <span>{formatDate(u.date, { day: 'numeric', month: 'long', year: 'numeric' })}</span>
                  </div>
                  {u.is_followed === true && <span className="badge badge-accent">Seguito</span>}
                  {u.is_followed === false && <span className="badge badge-danger">Saltato</span>}
                </div>
              ))}
            </div>
          </div>
        )}
        </aside>
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title="Eliminare la ricetta?"
          text="Sparisce dal ricettario. Se è usata in un piano non potrà essere eliminata."
          confirmLabel="Elimina"
          danger
          onConfirm={remove}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  );
}
