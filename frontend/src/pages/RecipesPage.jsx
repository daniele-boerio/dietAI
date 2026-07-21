import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChefHat, Clock, Heart, Search } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import EmptyState from '../components/EmptyState';
import MacroBar from '../components/MacroBar';
import StarRating from '../components/StarRating';

const DIFFICULTIES = [
  { key: '', label: 'Tutte' },
  { key: 'easy', label: 'Facili' },
  { key: 'medium', label: 'Medie' },
  { key: 'hard', label: 'Impegnative' },
];

export default function RecipesPage() {
  const { addToast } = useApp();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [minRating, setMinRating] = useState(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    // Debounce sulla ricerca: si scrive più in fretta di quanto il server risponda.
    const t = setTimeout(() => {
      api
        .getRecipes({
          page,
          per_page: 24,
          search: search.trim() || null,
          difficulty: difficulty || null,
          is_favorite: onlyFavorites || null,
          rating_min: minRating,
        })
        .then(setData)
        .catch((e) => addToast(e.message, 'error'))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [search, difficulty, onlyFavorites, minRating, page, addToast]);

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Ricettario</h1>
          <p className="page-subtitle">
            Tutto quello che è passato dalla tua cucina. I voti guidano le generazioni
            future.
          </p>
        </div>
      </div>

      <div className="filters">
        <div className="search-field">
          <Search />
          <input
            type="text"
            placeholder="Cerca una ricetta..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>

        <button
          className={`chip ${onlyFavorites ? 'active' : ''}`}
          onClick={() => {
            setOnlyFavorites((v) => !v);
            setPage(1);
          }}
        >
          <Heart size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
          Preferite
        </button>

        <button
          className={`chip ${minRating === 4 ? 'active' : ''}`}
          onClick={() => {
            setMinRating((v) => (v === 4 ? null : 4));
            setPage(1);
          }}
        >
          Voto 4+
        </button>

        {DIFFICULTIES.map((d) => (
          <button
            key={d.key}
            className={`chip ${difficulty === d.key ? 'active' : ''}`}
            onClick={() => {
              setDifficulty(d.key);
              setPage(1);
            }}
          >
            {d.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="spinner" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={ChefHat}
          title="Nessuna ricetta"
          text="Genera un piano settimanale: ogni ricetta creata finisce qui, pronta da riusare."
          action={
            <Link className="btn btn-primary" to="/plan">
              Vai alla settimana
            </Link>
          }
        />
      ) : (
        <>
          <div className="recipe-grid">
            {data.items.map((r) => (
              <Link key={r.id} to={`/recipes/${r.id}`} className="recipe-card">
                <div className="recipe-card-title">{r.title}</div>
                <div className="meal-meta">
                  <span>{r.calories} kcal</span>
                  <span>
                    <Clock size={12} /> {r.prep_time_min + r.cook_time_min} min
                  </span>
                  {r.is_favorite && <Heart size={13} color="var(--terracotta)" fill="currentColor" />}
                </div>
                <MacroBar protein={r.protein_g} carbs={r.carbs_g} fat={r.fat_g} />
                <StarRating value={r.rating} readOnly />
              </Link>
            ))}
          </div>

          {totalPages > 1 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 26 }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Precedente
              </button>
              <span style={{ alignSelf: 'center', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Pagina {page} di {totalPages}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Successiva
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
