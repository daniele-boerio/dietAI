import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarDays, ChefHat, ChevronRight, ShoppingCart, Sparkles } from 'lucide-react';
import { api, formatDate } from '../api';
import DayMeals from '../components/DayMeals';
import EmptyState from '../components/EmptyState';
import LoadError from '../components/LoadError';

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
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
  const daPrendere = shopping.total_items - shopping.checked_items;


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
          <DayMeals
            meals={today.meals}
            onChanged={load}
            vuoto={
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
            }
          />

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
    </>
  );
}
