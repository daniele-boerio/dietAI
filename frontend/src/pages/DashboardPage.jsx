import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  Check,
  ChefHat,
  Lock,
  ShoppingCart,
  Sparkles,
  X,
} from 'lucide-react';
import { api, formatDate, formatMoney } from '../api';
import { useApp } from '../App';
import EmptyState from '../components/EmptyState';
import MacroBar from '../components/MacroBar';

export default function DashboardPage() {
  const { addToast } = useApp();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () =>
    api
      .getDashboard()
      .then(setData)
      .catch((e) => addToast(e.message, 'error'))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const markFollowed = async (mealId, followed) => {
    try {
      await api.setFollowed(mealId, followed);
      load();
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  if (loading) return <div className="spinner" />;
  if (!data?.has_diet) {
    return (
      <EmptyState
        icon={ChefHat}
        title="Nessuna dieta attiva"
        text="Carica il PDF del nutrizionista per iniziare a generare i piani."
        action={
          <Link className="btn btn-primary" to="/settings/diet">
            Vai alla dieta
          </Link>
        }
      />
    );
  }

  const { today, week, shopping, diet } = data;
  const emptySlots = week.meals_total - week.meals_filled;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">{today.day_name}</h1>
          <p className="page-subtitle">
            {formatDate(today.date, { day: 'numeric', month: 'long', year: 'numeric' })} ·{' '}
            {diet.daily_calories} kcal al giorno su {diet.meals_count} pasti
          </p>
        </div>
        <div className="page-actions">
          <Link className="btn btn-secondary" to="/plan">
            <CalendarDays size={16} /> Settimana
          </Link>
          <Link className="btn btn-primary" to="/shopping">
            <ShoppingCart size={16} /> Lista della spesa
          </Link>
        </div>
      </div>

      {week.is_locked && (
        <div className="notice notice-lock">
          <Lock />
          <div>
            <strong>Piano bloccato.</strong> Hai già fatto la spesa: le ricette di questa
            settimana restano queste fino al{' '}
            {week.lock_expires_at ? formatDate(week.lock_expires_at) : '—'}. Le modifiche
            si fanno sulla <Link to="/plan/next">settimana prossima</Link>.
          </div>
        </div>
      )}

      {emptySlots > 0 && !week.is_locked && (
        <div className="notice">
          <Sparkles />
          <div>
            Mancano <strong>{emptySlots} pasti</strong> in questa settimana.{' '}
            <Link to="/plan" style={{ color: 'var(--accent)', fontWeight: 600 }}>
              Genera il piano
            </Link>
          </div>
        </div>
      )}

      <div className="stat-grid">
        <div className="stat-tile">
          <div className="stat-value">
            {week.meals_filled}
            <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
              /{week.meals_total}
            </span>
          </div>
          <div className="stat-label">Pasti pianificati questa settimana</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">
            {shopping.checked_items}
            <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
              /{shopping.total_items}
            </span>
          </div>
          <div className="stat-label">Articoli presi</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{formatMoney(shopping.estimated_cost) || '—'}</div>
          <div className="stat-label">Spesa stimata</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{data.recipes_count}</div>
          <div className="stat-label">
            Ricette in archivio · {data.favorites_count} preferite
          </div>
        </div>
      </div>

      <h2 className="section-title">Cosa si mangia oggi</h2>

      {today.meals.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title="Niente in programma per oggi"
          text="Genera il piano della settimana e i pasti compariranno qui."
          action={
            <Link className="btn btn-primary" to="/plan">
              Vai alla settimana
            </Link>
          }
        />
      ) : (
        <div className="recipe-grid">
          {today.meals.map((meal) => (
            <div key={meal.meal_id} className="card">
              <div className="meal-slot">{meal.slot_name}</div>

              {meal.recipe ? (
                <>
                  <div
                    className="recipe-card-title"
                    style={{ cursor: 'pointer', margin: '6px 0 8px' }}
                    onClick={() => navigate(`/meals/${meal.meal_id}`)}
                  >
                    {meal.recipe.title}
                  </div>
                  <div className="meal-meta" style={{ marginBottom: 8 }}>
                    <span>{meal.recipe.calories} kcal</span>
                    <span>
                      {meal.recipe.prep_time_min + meal.recipe.cook_time_min} min
                    </span>
                    <span style={{ color: 'var(--text-muted)' }}>
                      target {meal.target_calories} kcal
                    </span>
                  </div>
                  <MacroBar
                    protein={meal.recipe.protein_g}
                    carbs={meal.recipe.carbs_g}
                    fat={meal.recipe.fat_g}
                  />

                  <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
                    <button
                      className={`btn btn-sm ${
                        meal.is_followed === true ? 'btn-primary' : 'btn-secondary'
                      }`}
                      onClick={() => markFollowed(meal.meal_id, true)}
                    >
                      <Check size={14} /> Fatto
                    </button>
                    <button
                      className={`btn btn-sm ${
                        meal.is_followed === false ? 'btn-danger' : 'btn-secondary'
                      }`}
                      onClick={() => markFollowed(meal.meal_id, false)}
                    >
                      <X size={14} /> Saltato
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="meal-empty" style={{ margin: '8px 0' }}>
                    Nessuna ricetta · target {meal.target_calories} kcal
                  </div>
                  <Link className="btn btn-secondary btn-sm" to={`/meals/${meal.meal_id}`}>
                    Scegli cosa mangiare
                  </Link>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
