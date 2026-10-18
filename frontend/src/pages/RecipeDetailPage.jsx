import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Heart, Pencil, Plus, Trash2, X } from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import LoadError from '../components/LoadError';
import Modal from '../components/Modal';
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
  const [editing, setEditing] = useState(false);

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

  // Senza try/catch un errore restava una promessa respinta e basta: nessun avviso,
  // e il voto sembrava semplicemente ignorato.
  const rate = async (rating) => {
    try {
      await api.rateRecipe(recipe.id, rating);
      setRecipe((r) => ({ ...r, rating }));
      addToast('Voto salvato ✓');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const toggleFavorite = async () => {
    const next = !recipe.is_favorite;
    try {
      await api.favoriteRecipe(recipe.id, next);
      setRecipe((r) => ({ ...r, is_favorite: next }));
    } catch (e) {
      addToast(e.message, 'error');
    }
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
                <button className="btn btn-secondary" onClick={() => setEditing(true)}>
                  <Pencil size={16} /> Modifica
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

      {editing && (
        <ModificaRicetta
          recipe={recipe}
          onSaved={(r) => {
            setRecipe(r);
            setEditing(false);
            addToast('Ricetta aggiornata ✓');
          }}
          onClose={() => setEditing(false)}
        />
      )}

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

// Le unità che la spesa sa sommare; si può scrivere anche altro, il server le normalizza.
const UNITA = ['g', 'ml', 'unità', 'cucchiai', 'cucchiaini', 'spicchi', 'fette', 'q.b.'];

const MACRO = [
  ['calories', 'Calorie (kcal)'],
  ['protein_g', 'Proteine (g)'],
  ['carbs_g', 'Carboidrati (g)'],
  ['fat_g', 'Grassi (g)'],
];

/**
 * Correggere la ricetta a mano: testi, tempi e ingredienti.
 *
 * Nasce per gli errori del modello — il cavolfiore «1 unità» invece che in grammi —
 * che prima si sistemavano solo chiedendolo alla chat di un pasto. Cambia la ricetta
 * del ricettario, quindi anche i pasti che la usano. Calorie e macro si rifanno dagli
 * ingredienti; solo chi li aveva scritti a mano (`nutrition_source === 'utente'`) li
 * corregge qui.
 */
function ModificaRicetta({ recipe, onSaved, onClose }) {
  const { addToast } = useApp();
  const mieiNumeri = recipe.nutrition_source === 'utente';
  const [form, setForm] = useState(() => ({
    title: recipe.title,
    description: recipe.description || '',
    prep_time_min: recipe.prep_time_min || 0,
    cook_time_min: recipe.cook_time_min || 0,
    difficulty: recipe.difficulty || 'medium',
    instructions: recipe.instructions || '',
    calories: recipe.calories,
    protein_g: recipe.protein_g,
    carbs_g: recipe.carbs_g,
    fat_g: recipe.fat_g,
  }));
  const [righe, setRighe] = useState(() =>
    recipe.ingredients.map((i, n) => ({
      key: n,
      name: i.name,
      quantity: i.quantity,
      unit: i.unit,
      notes: i.notes || '',
    })),
  );
  const [busy, setBusy] = useState(false);

  const campo = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const riga = (key, k) => (e) =>
    setRighe((rr) => rr.map((r) => (r.key === key ? { ...r, [k]: e.target.value } : r)));
  const aggiungi = () =>
    setRighe((rr) => [...rr, { key: Date.now(), name: '', quantity: '', unit: 'g', notes: '' }]);
  const togli = (key) => setRighe((rr) => rr.filter((r) => r.key !== key));

  const ingredienti = righe
    .filter((r) => r.name.trim())
    .map((r) => ({
      name: r.name.trim(),
      quantity: Number(r.quantity) || 0,
      unit: r.unit.trim() || 'unità',
      notes: r.notes.trim() || null,
    }));

  const salva = async () => {
    setBusy(true);
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        prep_time_min: Number(form.prep_time_min) || 0,
        cook_time_min: Number(form.cook_time_min) || 0,
        difficulty: form.difficulty,
        instructions: form.instructions,
        ingredients: ingredienti,
      };
      if (mieiNumeri) {
        for (const [k] of MACRO) {
          const v = form[k];
          payload[k] = v === '' || v === null ? null : Number(v);
        }
        if (payload.calories !== null) payload.calories = Math.round(payload.calories);
      }
      onSaved(await api.updateRecipe(recipe.id, payload));
    } catch (e) {
      addToast(e.message, 'error');
      setBusy(false);
    }
  };

  return (
    <Modal title="Modifica la ricetta" onClose={onClose} busy={busy} className="modal-lg">
      <div className="field">
        <label className="field-label" htmlFor="mr-titolo">
          Nome
        </label>
        <input
          id="mr-titolo"
          type="text"
          maxLength={200}
          value={form.title}
          onChange={campo('title')}
          disabled={busy}
        />
      </div>

      <div className="field">
        <label className="field-label" htmlFor="mr-descrizione">
          Descrizione
        </label>
        <input
          id="mr-descrizione"
          type="text"
          maxLength={1000}
          value={form.description}
          onChange={campo('description')}
          disabled={busy}
        />
      </div>

      <div className="edit-grid">
        <div className="field">
          <label className="field-label" htmlFor="mr-prep">
            Preparazione (min)
          </label>
          <input
            id="mr-prep"
            type="number"
            min="0"
            max="600"
            inputMode="numeric"
            value={form.prep_time_min}
            onChange={campo('prep_time_min')}
            disabled={busy}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="mr-cottura">
            Cottura (min)
          </label>
          <input
            id="mr-cottura"
            type="number"
            min="0"
            max="600"
            inputMode="numeric"
            value={form.cook_time_min}
            onChange={campo('cook_time_min')}
            disabled={busy}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="mr-difficolta">
            Difficoltà
          </label>
          <select
            id="mr-difficolta"
            value={form.difficulty}
            onChange={campo('difficulty')}
            disabled={busy}
          >
            <option value="easy">Facile</option>
            <option value="medium">Media</option>
            <option value="hard">Difficile</option>
          </select>
        </div>
      </div>

      <div className="field">
        <span className="field-label">Ingredienti, per una porzione</span>
        <div className="ing-edit">
          {righe.map((r) => (
            <div key={r.key} className="ing-edit-row">
              <input
                type="text"
                aria-label="Ingrediente"
                placeholder="cavolfiore"
                maxLength={120}
                value={r.name}
                onChange={riga(r.key, 'name')}
                disabled={busy}
              />
              <input
                type="number"
                aria-label="Quantità"
                min="0"
                step="any"
                inputMode="decimal"
                value={r.quantity}
                onChange={riga(r.key, 'quantity')}
                disabled={busy}
              />
              <input
                type="text"
                aria-label="Unità"
                list="mr-unita"
                maxLength={20}
                value={r.unit}
                onChange={riga(r.key, 'unit')}
                disabled={busy}
              />
              <button
                type="button"
                className="btn btn-ghost btn-icon"
                onClick={() => togli(r.key)}
                disabled={busy}
                title="Togli l'ingrediente"
                aria-label={`Togli ${r.name || 'questo ingrediente'}`}
              >
                <X size={16} />
              </button>
            </div>
          ))}
          <datalist id="mr-unita">
            {UNITA.map((u) => (
              <option key={u} value={u} />
            ))}
          </datalist>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={aggiungi}
          disabled={busy}
          style={{ marginTop: 8 }}
        >
          <Plus size={14} /> Aggiungi ingrediente
        </button>
        <p className="field-hint">
          {mieiNumeri
            ? 'Le calorie e i macro sono i tuoi: correggili qui sotto se cambi le dosi.'
            : 'Calorie e macro si ricalcolano dagli ingredienti, e la spesa segue le dosi nuove.'}
        </p>
      </div>

      {mieiNumeri && (
        <div className="edit-grid">
          {MACRO.map(([k, label]) => (
            <div key={k} className="field">
              <label className="field-label" htmlFor={`mr-${k}`}>
                {label}
              </label>
              <input
                id={`mr-${k}`}
                type="number"
                min="0"
                step="any"
                inputMode="decimal"
                value={form[k] ?? ''}
                onChange={campo(k)}
                disabled={busy}
              />
            </div>
          ))}
        </div>
      )}

      <div className="field">
        <label className="field-label" htmlFor="mr-procedimento">
          Procedimento
        </label>
        <textarea
          id="mr-procedimento"
          rows={8}
          maxLength={10000}
          value={form.instructions}
          onChange={campo('instructions')}
          disabled={busy}
        />
      </div>

      <div className="modal-actions">
        <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
          Annulla
        </button>
        <button
          className="btn btn-primary"
          onClick={salva}
          disabled={busy || !form.title.trim() || !form.instructions.trim() || !ingredienti.length}
        >
          {busy && <span className="spinner-inline" />}
          Salva
        </button>
      </div>
    </Modal>
  );
}
