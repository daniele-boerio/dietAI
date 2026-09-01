import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  Check,
  ChefHat,
  ChevronRight,
  MessageCircle,
  Pin,
  ShoppingCart,
  Sparkles,
  UtensilsCrossed,
  X,
} from 'lucide-react';
import { api, formatDate, formatMoney, formatNumber } from '../api';
import { useApp } from '../App';
import EmptyState from '../components/EmptyState';
import MacroBar from '../components/MacroBar';
import { nonScalatiDallaDispensa, scalatiDallaDispensa } from '../lib/pantry';
import { useTelefono } from '../lib/schermo';

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

// Le parole con cui la spia dell'aderenza si spiega passandoci sopra. Il colore da
// solo non basta — daltonismo, schermo al sole — ed è la stessa ragione per cui nella
// griglia della settimana lo stato è scritto accanto al filetto colorato.
const ETICHETTE_ADERENZA = {
  full: 'seguito',
  partial: 'in parte',
  missed: 'non seguito',
  untracked: 'non segnato',
  none: 'nessun piano',
};

// Un pasto della giornata, in riga. Il tondo a sinistra dice com'è andata — o che
// quel pasto non lo genera nessuno — poi il nome del pasto con le sue calorie in
// monospaziato e sotto il piatto. È la forma che il telefono chiede: quattro righe
// per una giornata, contro quattro card da 215px l'una.
function MealRow({ meal }) {
  const stato = meal.is_followed === true ? 'done' : meal.is_skipped ? 'moved' : '';
  const Icona =
    meal.is_followed === true
      ? Check
      : meal.is_skipped
        ? X
        : meal.self_managed
          ? ChefHat
          : UtensilsCrossed;
  return (
    <Link className={`meal-row ${stato}`} to={`/meals/${meal.meal_id}`}>
      <span className={`meal-tondo ${stato} ${meal.self_managed ? 'mine' : ''}`}>
        <Icona />
      </span>
      <span className="meal-row-testo">
        <span className="meal-slot">
          {meal.slot_name} · {meal.recipe ? meal.recipe.calories : meal.target_calories} kcal
        </span>
        <span className="meal-row-titolo">
          {meal.recipe
            ? meal.recipe.title
            : meal.self_managed
              ? 'Lo prepari tu'
              : 'Scegli cosa mangiare'}
        </span>
      </span>
      <ChevronRight className="meal-row-freccia" />
    </Link>
  );
}

export default function DashboardPage() {
  const { addToast } = useApp();
  const navigate = useNavigate();
  // Sul telefono i pasti già decisi sono righe di elenco, non card: vedi
  // `lib/schermo.js`. Il pasto di adesso resta una card in tutti e due i casi.
  const telefono = useTelefono();
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
  // Il backend può non averla (una risposta più vecchia di questa schermata): meglio
  // una spia vuota che una pagina che non si disegna.
  const adherence = data.adherence || { days: [], tracked_days: 0, score_pct: 0 };
  const emptySlots = week.meals_total - week.meals_filled;
  const totali = totaliDiOggi(today.meals);
  const daPrendere = shopping.total_items - shopping.checked_items;

  // Il pasto che viene adesso è l'unico messo in evidenza: è quello per cui si è
  // aperta l'app, e in una fila di card tutte uguali si perdeva fra le altre. È il
  // primo della giornata che ha una ricetta e su cui non si è ancora detto niente —
  // quelli già segnati sono storia, e una casella vuota non è un piatto.
  const adesso = today.meals.find((m) => m.recipe && !m.is_skipped && m.is_followed === null);

  // I pasti che DietAI non genera non stanno in griglia: «lo prepari tu» non è una
  // casella da riempire, e dargli una card vuol dire una card con dentro niente.
  // Restano però scritti in colonna a destra — una giornata da cinque pasti che ne
  // mostra tre sembra una giornata a cui ne mancano due.
  const inGriglia = today.meals.filter((m) => !m.self_managed);
  const inDisparte = today.meals.filter((m) => m.self_managed);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Si mangia</h1>
          <p className="page-subtitle">
            {today.day_name} {formatDate(today.date, { day: 'numeric', month: 'long' })} ·{' '}
            {diet.daily_calories} kcal su {diet.meals_count} pasti
          </p>
        </div>
        <div className="page-actions">
          {/* Sul telefono no: la settimana è una scheda in fondo, e un pulsante che
              porta dove porta già una scheda è un comando che ripete un comando. */}
          <Link className="btn btn-secondary solo-largo" to="/plan">
            <CalendarDays size={16} /> Vai alla settimana
          </Link>
          {/* Porta alla settimana **con la finestra già aperta**: generare passa
              sempre da lì — è la schermata dove si sceglie cosa si sta per pagare —
              e un pulsante che promette sei pasti non può lasciare su una pagina in
              cui bisogna ancora cercare da dove si comincia. */}
          {emptySlots > 0 && (
            <Link className="btn btn-primary" to="/plan" state={{ genera: true }}>
              <Sparkles size={16} /> Genera {emptySlots} {emptySlots === 1 ? 'pasto' : 'pasti'}
            </Link>
          )}
        </div>
      </div>

      <div className="page-split" style={{ '--aside': '356px' }}>
        <div className="page-main">
          {today.meals.length > 0 && (
            <div className="day-summary">
              <div className="day-summary-top">
                <strong>{formatNumber(totali.calories)}</strong>
                <span>
                  / {formatNumber(totali.target)} kcal
                  <br />
                  in programma
                </span>
              </div>
              <MacroBar
                className="macro-holder"
                protein={totali.protein_g}
                carbs={totali.carbs_g}
                fat={totali.fat_g}
                legend
              />
              <span className="day-summary-tracked">
                {totali.segnati} di {today.meals.length} segnati
              </span>
            </div>
          )}

          {inGriglia.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="Niente in programma per oggi"
              text="Genera il piano della settimana e i pasti compariranno qui."
              action={
                <Link className="btn btn-primary" to="/plan" state={{ genera: true }}>
                  <Sparkles size={16} /> Genera la settimana
                </Link>
              }
            />
          ) : (
            <div className="today-grid">
              {inGriglia.map((meal) =>
                telefono && !(adesso && adesso.meal_id === meal.meal_id) ? (
                  <MealRow key={meal.meal_id} meal={meal} />
                ) : (
                <div
                  key={meal.meal_id}
                  className={`card today-card ${meal.is_skipped ? 'skipped' : ''} ${
                    meal.is_followed === true ? 'followed' : ''
                  } ${adesso && adesso.meal_id === meal.meal_id ? 'adesso' : ''}`}
                >
                  <div className="meal-slot">
                    <span className="meal-slot-name">
                      {meal.slot_name}
                      {adesso && adesso.meal_id === meal.meal_id && ' · adesso'}
                    </span>
                    {meal.is_followed === true && (
                      <span className="slot-state" title="L'hai seguito">
                        <Check />
                      </span>
                    )}
                    {meal.is_skipped && (
                      <span className="slot-state moved" title="Hai mangiato altro">
                        <X />
                      </span>
                    )}
                  </div>

                  {meal.recipe ? (
                    <>
                      {/* Il piatto non ha una fotografia: al suo posto un
                          segnaposto dichiarato, che tiene il posto all'immagine
                          senza far sembrare rotta la card finché non c'è. */}
                      <Link
                        className="dish"
                        to={`/meals/${meal.meal_id}`}
                        aria-label={meal.recipe.title}
                      >
                        <UtensilsCrossed />
                      </Link>
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
                        <span className="meal-facts">
                          {meal.recipe.calories} kcal · target {meal.target_calories} ·{' '}
                          {meal.recipe.prep_time_min + meal.recipe.cook_time_min} min
                        </span>
                        <div className="today-card-actions">
                          <button
                            className={`btn btn-sm ${
                              meal.is_followed === true ? 'btn-primary' : 'btn-secondary'
                            }`}
                            onClick={() => markFollowed(meal.meal_id, true)}
                          >
                            <Check size={14} /> L&rsquo;ho mangiato
                          </button>
                          <button
                            className={`btn btn-sm btn-icon ${
                              meal.is_followed === false ? 'btn-moved' : 'btn-secondary'
                            }`}
                            title="Ho mangiato altro"
                            onClick={() => markFollowed(meal.meal_id, false)}
                          >
                            <X size={15} />
                          </button>
                          <Link
                            className="btn btn-sm btn-secondary btn-icon"
                            title="Apri il pasto"
                            to={`/meals/${meal.meal_id}`}
                          >
                            <MessageCircle size={15} />
                          </Link>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <Link
                        className="dish vuoto"
                        to={`/meals/${meal.meal_id}`}
                        aria-label="Scegli cosa mangiare"
                      >
                        <UtensilsCrossed />
                      </Link>
                      <div className="today-card-title vuoto">Ancora niente</div>
                      <div className="today-card-foot">
                        <span className="meal-facts">target {meal.target_calories} kcal</span>
                        <div className="today-card-actions">
                          <Link className="btn btn-sm btn-secondary" to={`/meals/${meal.meal_id}`}>
                            Scegli cosa mangiare
                          </Link>
                        </div>
                      </div>
                    </>
                  )}
                </div>
                )
              )}
              {/* Anche i pasti che DietAI non genera sono righe della giornata: sul
                  monitor stanno in colonna a destra, ma su un telefono una colonna a
                  destra non c'è, e una giornata da cinque pasti che ne mostra tre
                  sembra una giornata a cui ne mancano due. */}
              {telefono && inDisparte.map((meal) => <MealRow key={meal.meal_id} meal={meal} />)}
            </div>
          )}

          {/* La spesa non è una statistica, è la cosa che si fa dopo aver guardato i
              pasti: una riga che porta lì, col numero dentro. */}
          <Link className="shop-bar" to="/shopping">
            <ShoppingCart />
            <div>
              <strong>
                {daPrendere > 0
                  ? `${daPrendere} ${daPrendere === 1 ? 'cosa da prendere' : 'cose da prendere'}`
                  : 'Non manca niente'}
              </strong>
              <span>
                {daPrendere > 0
                  ? shopping.estimated_cost
                    ? `${formatMoney(shopping.estimated_cost)} stimati`
                    : 'per il piano da oggi in avanti'
                  : 'quello che il piano chiede è già in dispensa'}
              </span>
            </div>
            <ChevronRight />
          </Link>
        </div>

        <aside className="page-aside">
          {inDisparte.length > 0 && (
            <div className="card solo-largo">
              <div className="card-title">Non generati</div>
              <div className="side-list">
                {inDisparte.map((meal) => (
                  <div key={meal.meal_id} className="side-row mine">
                    {meal.is_recurring ? <Pin /> : <ChefHat />}
                    <span>
                      {meal.slot_name} — {meal.is_recurring ? 'pasto fisso' : 'lo prepari tu'}
                    </span>
                    <em>{meal.target_calories}</em>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card solo-largo">
            <div className="adherence-head">
              <span className="card-title" style={{ marginBottom: 0 }}>
                Aderenza · 4 settimane
              </span>
              <span className="adherence-score">
                {adherence.tracked_days ? `${Math.round(adherence.score_pct)}%` : '—'}
              </span>
            </div>
            {/* Altezza = quanto pesava il piano di quel giorno sul suo target,
                colore = com'è andata davvero. Due domande, due canali: una giornata
                pianificata benissimo e mai seguita si legge alta e spenta. */}
            <div className="spark">
              {adherence.days.map((g) => (
                <span
                  key={g.date}
                  className={g.state}
                  style={{ height: `${Math.max(4, Math.round(g.ratio * 100))}%` }}
                  title={`${formatDate(g.date, { day: 'numeric', month: 'short' })} · ${
                    ETICHETTE_ADERENZA[g.state]
                  }`}
                />
              ))}
            </div>
            <div className="spark-foot">
              <span>4 sett. fa</span>
              <span>
                {adherence.tracked_days
                  ? `${adherence.tracked_days} giorni segnati`
                  : 'niente segnato'}
              </span>
              <span>oggi</span>
            </div>
          </div>

          <div className="mini-stats solo-largo">
            <Link className="mini-stat" to="/plan">
              <strong>
                {week.meals_filled}/{week.meals_total}
              </strong>
              piano
            </Link>
            <Link className="mini-stat" to="/recipes">
              <strong>{data.recipes_count}</strong>
              ricette
            </Link>
            <Link className="mini-stat" to="/recipes">
              <strong>{data.favorites_count}</strong>
              preferite
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}
