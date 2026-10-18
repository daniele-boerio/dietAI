import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  CalendarDays,
  Check,
  ChefHat,
  ChevronRight,
  MessageCircle,
  ShoppingCart,
  Sparkles,
  UtensilsCrossed,
  X,
} from 'lucide-react';
import { api, formatDate, formatNumber } from '../api';
import { useApp } from '../App';
import EatenInsteadDialog from '../components/EatenInsteadDialog';
import EmptyState from '../components/EmptyState';
import LoadError from '../components/LoadError';
import MacroBar from '../components/MacroBar';
import { nonScalatiDallaDispensa, scalatiDallaDispensa } from '../lib/pantry';
import { useTelefono } from '../lib/schermo';
import { niente, todayTotals } from '../lib/today';

// Quanto si mangia oggi, sommando i piatti in programma. Un pasto rimandato non
// conta (si cucina un altro giorno) e uno che prepara l'utente conta col suo target:
// è la stessa aritmetica di `serialize_week`, e senza la seconda metà la giornata
// sembrerebbe più corta di quello che è.
// Cosa dice la riga di un pasto «ho mangiato altro»: la stima, se c'è, al posto del
// piatto rimandato — è quello che conta nel totale qui sopra.
function altroMangiato(meal) {
  if (!(meal.is_skipped || meal.is_followed === false)) return null;
  const stima = meal.eaten_nutrition;
  if (!stima) return { kcal: null, testo: 'Hai mangiato altro: cosa?' };
  // «Non ho mangiato niente» è uno zero saputo, non una stima: niente «≈».
  if (niente(meal)) return { kcal: 0, niente: true, testo: 'Non hai mangiato niente' };
  return { kcal: stima.calories, testo: meal.deviation_notes || 'Hai mangiato altro' };
}

// Le calorie di un pasto «ho mangiato altro», come le dice la riga.
function kcalAltro(altro) {
  if (altro.kcal == null) return 'non stimato';
  return altro.niente ? '0 kcal' : `≈ ${altro.kcal} kcal stimate`;
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
  const altro = altroMangiato(meal);
  return (
    <Link className={`meal-row ${stato}`} to={`/meals/${meal.meal_id}`}>
      <span className={`meal-tondo ${stato} ${meal.self_managed ? 'mine' : ''}`}>
        <Icona />
      </span>
      <span className="meal-row-testo">
        <span className="meal-slot">
          {meal.slot_name} ·{' '}
          {altro
            ? kcalAltro(altro)
            : `${meal.recipe ? meal.recipe.calories : meal.target_calories} kcal`}
        </span>
        <span className="meal-row-titolo">
          {altro
            ? altro.testo
            : meal.recipe
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

// Le barre dicono l'aderenza col colore: a parole, quante giornate in ogni stato.
function riassuntoAderenza(giorni) {
  const conti = {};
  giorni.forEach((g) => {
    conti[g.state] = (conti[g.state] || 0) + 1;
  });
  const parti = Object.entries(conti)
    .filter(([stato]) => ETICHETTE_ADERENZA[stato])
    .map(([stato, n]) => `${n} ${ETICHETTE_ADERENZA[stato].toLowerCase()}`);
  return `Ultime quattro settimane: ${parti.join(', ') || 'niente segnato'}`;
}

export default function DashboardPage() {
  const { addToast } = useApp();
  const navigate = useNavigate();
  // Sul telefono i pasti già decisi sono righe di elenco, non card: vedi
  // `lib/schermo.js`. Il pasto di adesso resta una card in tutti e due i casi.
  const telefono = useTelefono();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  // Il pasto appena segnato «ho mangiato altro»: la modale chiede cosa.
  const [altro, setAltro] = useState(null);

  const [error, setError] = useState(null);
  // Il pasto che si sta segnando: due tocchi rapidi su «l'ho seguito» mandavano due
  // richieste e due avvisi sulla dispensa.
  const [segnando, setSegnando] = useState(null);

  const load = () =>
    api
      .getDashboard()
      .then((d) => {
        setData(d);
        setError(null);
      })
      // Senza dati la pagina diceva «Nessuna dieta attiva»: a chi apre l'app senza
      // rete chiedeva di caricare una dieta che ha già.
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
    // Riaperta dal background (su iPhone succede di continuo) la home mostrava
    // l'«oggi» di ieri: si rilegge quando torna visibile.
    const torna = () => document.visibilityState === 'visible' && load();
    document.addEventListener('visibilitychange', torna);
    return () => document.removeEventListener('visibilitychange', torna);
  }, []);

  const markFollowed = async (mealId, followed) => {
    if (segnando) return;
    // Già «ho mangiato altro»: ripremerlo riapre la domanda invece di rimandarlo al
    // server, che cancellerebbe la nota scritta.
    const prima = data?.today?.meals?.find((m) => m.meal_id === mealId);
    if (followed === false && prima?.is_followed === false) {
      setAltro({ id: mealId, slot_name: prima.slot_name, deviation_notes: prima.deviation_notes });
      return;
    }
    setSegnando(mealId);
    try {
      const updated = await api.setFollowed(mealId, followed);
      if (followed === false) setAltro(updated);
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
    } finally {
      setSegnando(null);
    }
  };

  if (loading) return <div className="spinner" />;
  if (!data) {
    return (
      <LoadError
        message={error}
        onRetry={() => {
          setLoading(true);
          load();
        }}
      />
    );
  }
  if (!data.has_diet) {
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
  // Le vuote da oggi in avanti, quelle che la dialog proporrà: contando anche i
  // giorni passati il pulsante prometteva più pasti di quanti se ne generano.
  const emptySlots = week.meals_to_generate ?? week.meals_total - week.meals_filled;
  const totali = todayTotals(today.meals);
  const daPrendere = shopping.total_items - shopping.checked_items;

  // Il pasto che viene adesso è l'unico messo in evidenza: è quello per cui si è
  // aperta l'app, e in una fila di card tutte uguali si perdeva fra le altre. È il
  // primo della giornata che ha una ricetta e su cui non si è ancora detto niente —
  // quelli già segnati sono storia, e una casella vuota non è un piatto.
  const adesso = today.meals.find((m) => m.recipe && !m.is_skipped && m.is_followed === null);


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
                  {/* Con una stima dentro il numero non è più solo il piano: è un
                      misto di piatti e di cose mangiate, e va detto. */}
                  {totali.stime > 0 ? 'con le stime' : 'in programma'}
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

          {today.meals.length === 0 ? (
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
              {today.meals.map((meal) =>
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
                    {/* Il cappello dice che quel pasto lo prepari tu — è lo stesso
                        segno della griglia della settimana. Distinguerli basta: la
                        giornata è una sola, e un pasto che mangi conta come gli
                        altri, quindi va segnato come gli altri. */}
                    {meal.self_managed && (
                      <ChefHat className="meal-mark mine" aria-label="Lo prepari tu" />
                    )}
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
                          {altroMangiato(meal)
                            ? altroMangiato(meal).niente
                              ? 'non hai mangiato niente · 0 kcal'
                              : altroMangiato(meal).kcal != null
                                ? `al suo posto ≈ ${altroMangiato(meal).kcal} kcal: ${altroMangiato(meal).testo}`
                                : 'hai mangiato altro: non stimato'
                            : `${meal.recipe.calories} kcal`}{' '}
                          · target {meal.target_calories} ·{' '}
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
                  ) : meal.self_managed ? (
                    /* Non è una casella vuota da riempire: è un pasto che hai già
                       risolto per conto tuo. Non ha una ricetta e non ne avrà una,
                       ma lo mangi — quindi le due risposte ci vogliono uguali, e
                       contano nella giornata e nell'aderenza come tutte le altre. */
                    <>
                      {/* Il segnaposto non è tratteggiato come quello di una
                          casella vuota: qui non manca niente da riempire, il pasto
                          c'è e lo cucini tu. */}
                      <Link className="dish mio" to={`/meals/${meal.meal_id}`} aria-label="Lo prepari tu">
                        <ChefHat />
                      </Link>
                      <div className="today-card-title">Lo prepari tu</div>
                      <div className="today-card-foot">
                        <span className="meal-facts">{meal.target_calories} kcal · lo fai tu</span>
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
                  ? 'per il piano da oggi in avanti'
                  : 'quello che il piano chiede è già in dispensa'}
              </span>
            </div>
            <ChevronRight />
          </Link>
        </div>

        <aside className="page-aside">
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
            <div
              className="spark"
              role="img"
              aria-label={riassuntoAderenza(adherence.days)}
            >
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

      {altro && (
        <EatenInsteadDialog meal={altro} onSaved={() => load()} onClose={() => setAltro(null)} />
      )}
    </>
  );
}
