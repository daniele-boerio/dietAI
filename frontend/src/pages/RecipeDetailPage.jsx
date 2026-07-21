import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Heart, Trash2 } from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import RecipeView from '../components/RecipeView';
import StarRating from '../components/StarRating';

export default function RecipeDetailPage() {
  const { recipeId } = useParams();
  const { addToast } = useApp();
  const navigate = useNavigate();
  const [recipe, setRecipe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    api
      .getRecipe(recipeId)
      .then(setRecipe)
      .catch((e) => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  }, [recipeId, addToast]);

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
  if (!recipe) return null;

  return (
    <>
      <div className="page-header">
        <div>
          <button className="btn btn-ghost" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Indietro
          </button>
        </div>
        <div className="page-actions">
          <StarRating value={recipe.rating} onChange={rate} size="lg" />
          <button className="btn btn-secondary" onClick={toggleFavorite}>
            <Heart
              size={16}
              fill={recipe.is_favorite ? 'currentColor' : 'none'}
              color={recipe.is_favorite ? 'var(--terracotta)' : 'currentColor'}
            />
            Preferita
          </button>
          <button className="btn btn-danger" onClick={() => setConfirmDelete(true)}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div style={{ maxWidth: 780 }}>
        <RecipeView recipe={recipe} />

        {recipe.usage_history?.length > 0 && (
          <div className="card" style={{ marginTop: 14 }}>
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
