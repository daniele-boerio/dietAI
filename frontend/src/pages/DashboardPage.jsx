import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  Check,
  ChefHat,
  ChevronRight,
  ShoppingCart,
  Sparkles,
  X,
} from 'lucide-react';
import { api, formatDate, formatMoney, formatNumber } from '../api';
import { useApp } from '../App';
import EmptyState from '../components/EmptyState';
import MacroBar from '../components/MacroBar';
import { nonScalatiDallaDispensa, scalatiDallaDispensa } from '../lib/pantry';

// Quanto si mangia oggi, sommando i piatti in programma. Un pasto rimandato non
// conta (si cucina un altro giorno) e uno che prepara l'utente conta col suo target:
// è la stessa aritmetica di `serialize_week`, e senza la seconda metà la giornata
// sembrerebbe più corta di quello che è.
function totaliDiOggi(meals) {
  return meals.reduce(
    (somma, meal) => {
      // Segnato lo è anche il pasto rimandato: è una risposta come l'altra.
      const segnati = somma.segnati + (meal.is_followed === null ? 0 : 1);
      if (meal.is_skipped) return { ...somma, segnati };
      const r = meal.recipe;
      return {
        calories: somma.calories + (r ? r.calories : meal.self_managed ? meal.target_calories : 0),
        protein_g: somma.protein_g + (r ? r.protein_g : 0),
        carbs_g: somma.carbs_g + (r ? r.carbs_g : 0),
        fat_g: somma.fat_g + (r ? r.fat_g : 0),
        target: somma.target + meal.target_calories,
        segnati,
      };
    },
    { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0, target: 0, segnati: 0 }
  );
}

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
      const updated = await api.setFollowed(mealId, followed);
      // "Saltato" qui rimanda davvero il piatto: va detto dov'è finito.
      if (updated.moved_to) {
        addToast(
          `Ricetta rimandata a ${updated.moved_to.day_name.toLowerCase()}` +
            (updated.moved_to.next_week ? ' della settimana prossima' : '')
        );
      }
      if (updated.pantry_used?.length) {
        addToast(scalatiDallaDispensa(updated.pantry_used), 'info');
      } else if (followed && updated.pantry_skipped?.length) {
        addToast(nonScalatiDallaDispensa(updated.pantry_skipped), 'info');
      }
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
          <Link className="btn btn-primary" to="/diet">
            Vai alla dieta
          </Link>
        }
      />
    );
  }

  const { today, week, shopping, diet } = data;
  const emptySlots = week.meals_total - week.meals_filled;
  const totali = totaliDiOggi(today.meals);
  const daPrendere = shopping.total_items - shopping.checked_items;

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
        </div>
      </div>

      {emptySlots > 0 && (
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

      {/* La giornata in una riga sola. Erano quattro piastrelle di statistiche — pasti
          pianificati, articoli presi, spesa stimata, ricette in archivio — che sul
          telefono prendevano tutto lo spazio sopra la piega e spingevano sotto
          "cosa si mangia oggi", che è il motivo per cui si apre l'app. Quei numeri
          non sono spariti: sono scesi in fondo, dove si guardano una volta ogni tanto. */}
      {today.meals.length > 0 && (
        <div className="card day-summary">
          <div className="day-summary-top">
            <strong>{formatNumber(totali.calories)}</strong>
            <span>di {formatNumber(totali.target)} kcal in programma</span>
            <span className="day-summary-tracked">
              {totali.segnati} di {today.meals.length} segnati
            </span>
          </div>
          <MacroBar
            protein={totali.protein_g}
            carbs={totali.carbs_g}
            fat={totali.fat_g}
            legend
          />
        </div>
      )}

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
        <div className="recipe-grid fill">
          {today.meals.map((meal) => (
            <div
              key={meal.meal_id}
              className={`card today-card ${meal.is_skipped ? 'skipped' : ''} ${
                meal.is_followed === true ? 'followed' : ''
              }`}
            >
              <div className="meal-slot">
                <span className="meal-slot-name">{meal.slot_name}</span>
              </div>

              {meal.recipe ? (
                <>
                  {/* `title` perché il nome tagliato dall'ellissi resta leggibile
                      passandoci sopra, senza aprire il pasto. */}
                  <div
                    className="today-card-title"
                    title={meal.recipe.title}
                    onClick={() => navigate(`/meals/${meal.meal_id}`)}
                  >
                    {meal.recipe.title}
                  </div>
                  <div className="today-card-foot">
                    <div className="meal-foot">
                      <span className="meal-facts">
                        {meal.recipe.calories} kcal · target {meal.target_calories} kcal
                      </span>
                      {meal.is_followed === true && (
                        <span className="meal-state done">
                          <Check /> seguito
                        </span>
                      )}
                      {meal.is_skipped && <span className="meal-state moved">rimandato</span>}
                    </div>
                    <MacroBar
                      protein={meal.recipe.protein_g}
                      carbs={meal.recipe.carbs_g}
                      fat={meal.recipe.fat_g}
                    />

                    <div className="today-card-actions">
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
                          meal.is_followed === false ? 'btn-moved' : 'btn-secondary'
                        }`}
                        onClick={() => markFollowed(meal.meal_id, false)}
                      >
                        <X size={14} /> Ho mangiato altro
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="meal-empty">
                    Nessuna ricetta · target {meal.target_calories} kcal
                  </div>
                  <div className="today-card-foot">
                    <div className="today-card-actions">
                      <Link
                        className="btn btn-secondary btn-sm"
                        to={`/meals/${meal.meal_id}`}
                      >
                        Scegli cosa mangiare
                      </Link>
                    </div>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* La spesa non è una statistica, è la cosa che si fa dopo aver guardato i
          pasti: una riga che porta lì, col numero dentro. */}
      <Link className="shop-bar" to="/shopping">
        <ShoppingCart />
        <div>
          <strong>Lista della spesa</strong>
          <span>
            {daPrendere > 0
              ? `${daPrendere} ${daPrendere === 1 ? 'articolo' : 'articoli'} da prendere`
              : 'Niente da prendere'}
            {shopping.estimated_cost
              ? ` · ${formatMoney(shopping.estimated_cost)} stimati`
              : ''}
          </span>
        </div>
        <ChevronRight />
      </Link>

      <div className="home-stats">
        <span>
          Piano <strong>{week.meals_filled}</strong> di {week.meals_total}
        </span>
        <span>
          Ricettario <strong>{data.recipes_count}</strong>
        </span>
        <span>
          Preferite <strong>{data.favorites_count}</strong>
        </span>
      </div>
    </>
  );
}
