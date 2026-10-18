import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChefHat, Heart, Search, UtensilsCrossed } from 'lucide-react';
import { api } from '../api';
import EmptyState from '../components/EmptyState';
import LoadError from '../components/LoadError';
import MacroBar from '../components/MacroBar';
import StarRating from '../components/StarRating';

const DIFFICULTIES = [
  { key: '', label: 'Ogni difficoltà' },
  { key: 'easy', label: 'Facili' },
  { key: 'medium', label: 'Medie' },
  { key: 'hard', label: 'Impegnative' },
];

export default function RecipesPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [onlyFavorites, setOnlyFavorites] = useState(false);
  const [minRating, setMinRating] = useState(null);
  // Le votate male stanno a parte: restano (dicono al modello cosa evitare) ma non
  // sono piatti da rifare.
  const [soloBocciate, setSoloBocciate] = useState(false);
  const [page, setPage] = useState(1);
  const [error, setError] = useState(null);
  const [tentativo, setTentativo] = useState(0);

  useEffect(() => {
    setLoading(true);
    // Una risposta lenta per «pas» non deve arrivare dopo quella per «pasta» e
    // rimettere a schermo i risultati vecchi.
    let superata = false;
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
          scope: soloBocciate ? 'low' : null,
        })
        .then((d) => {
          if (superata) return;
          setData(d);
          setError(null);
        })
        // Un errore non è «Nessuna ricetta… genera un piano»: lo si dice per quello che è.
        .catch((e) => !superata && setError(e.message))
        .finally(() => !superata && setLoading(false));
    }, 250);
    return () => {
      superata = true;
      clearTimeout(t);
    };
  }, [search, difficulty, onlyFavorites, minRating, soloBocciate, page, tentativo]);

  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Ricettario</h1>
          <p className="page-subtitle">
            {data ? `${data.total} ricette · ` : ''}le preferite, quelle che hai votato e le
            tue: i voti guidano le generazioni future
          </p>
        </div>
        {/* La ricerca sta nella testata, non in mezzo ai filtri: cercare per nome e
            filtrare per voto sono due gesti diversi — il primo si fa quando si sa già
            cosa si vuole, gli altri per guardarsi intorno. */}
        <div className="page-actions">
          <div className="search-field">
            <Search />
            <input
              type="text"
              className="search-field-input"
              placeholder="Cerca una ricetta..."
              aria-label="Cerca una ricetta"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
      </div>

      <div className="filters">
        <button
          className={`chip ${!onlyFavorites && minRating === null && difficulty === '' && !soloBocciate ? 'active' : ''}`}
          onClick={() => {
            setOnlyFavorites(false);
            setMinRating(null);
            setDifficulty('');
            setSoloBocciate(false);
            setPage(1);
          }}
        >
          Tutte
        </button>

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

        <button
          className={`chip ${soloBocciate ? 'active' : ''}`}
          onClick={() => {
            setSoloBocciate((v) => !v);
            setPage(1);
          }}
        >
          Votate male
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
      ) : error && !data ? (
        <LoadError message={error} onRetry={() => setTentativo((n) => n + 1)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={ChefHat}
          title="Nessuna ricetta salvata"
          text="Qui restano le ricette che metti fra le preferite, che voti o che scrivi tu. Quelle generate e mai valutate escono dal ricettario: dai un voto a quelle che ti piacciono, dal pasto o prima di generare la settimana dopo."
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
                {/* Il piatto non ha una fotografia: al suo posto un segnaposto
                    dichiarato. In una griglia da dieci a farsi riconoscere è il nome,
                    che infatti è la cosa più grande della card. */}
                <div className="dish">
                  <UtensilsCrossed />
                  {r.is_favorite && (
                    <span className="dish-fav" title="Preferita">
                      <Heart size={13} fill="currentColor" />
                    </span>
                  )}
                </div>
                <div className="recipe-card-title">{r.title}</div>
                <MacroBar protein={r.protein_g} carbs={r.carbs_g} fat={r.fat_g} />
                <div className="recipe-card-foot">
                  <StarRating value={r.rating} readOnly />
                  <span className="meal-facts">
                    {r.calories} kcal · {r.prep_time_min + r.cook_time_min} min
                  </span>
                </div>
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
