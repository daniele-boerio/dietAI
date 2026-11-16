import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  CalendarDays,
  CalendarOff,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import { api, formatDate } from '../api';
import DayMeals from '../components/DayMeals';
import EmptyState from '../components/EmptyState';
import LoadError from '../components/LoadError';
import { useGoBack } from '../lib/navigation';

// Il riepilogo di un giorno, aperto toccandolo nella settimana: quello che la home
// mostra per oggi — quanto si è mangiato contro la dieta, i macro, fibre e zuccheri,
// e i pasti da segnare — per un giorno qualsiasi. La parte della giornata è la stessa
// della home (`DayMeals`), così le due schermate non raccontano due giornate diverse.

const GIORNO_MS = 24 * 60 * 60 * 1000;

// Il giorno prima o dopo, in ISO, senza passare dal fuso: a mezzanotte e al cambio
// dell'ora un `new Date(iso)` locale scivolava sul giorno sbagliato.
function spostaGiorno(iso, delta) {
  const [a, m, g] = iso.split('-').map(Number);
  return new Date(Date.UTC(a, m - 1, g) + delta * GIORNO_MS).toISOString().slice(0, 10);
}

export default function DayPage() {
  const { date } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const tornaIndietro = useGoBack(data ? `/plan/${data.week_start_date}` : '/plan');

  const load = () =>
    api
      .getDay(date)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => {
    setLoading(true);
    load();
    const torna = () => document.visibilityState === 'visible' && load();
    document.addEventListener('visibilitychange', torna);
    return () => document.removeEventListener('visibilitychange', torna);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  if (loading && !data) return <div className="spinner" />;
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
        icon={CalendarDays}
        title="Nessuna dieta attiva"
        text="Carica la dieta per avere un piano da seguire."
        action={
          <Link className="btn btn-primary" to="/diet">
            Vai alla dieta
          </Link>
        }
      />
    );
  }

  // `replace`: sfogliare i giorni non deve riempire la cronologia, o «indietro»
  // ripercorrerebbe la settimana un giorno alla volta invece di tornarci.
  const vaiA = (delta) => navigate(`/day/${spostaGiorno(date, delta)}`, { replace: true });
  const settimana = `/plan/${data.week_start_date}`;

  const vuoto = data.is_past ? (
    <EmptyState
      icon={CalendarDays}
      title="Niente in questo giorno"
      text="Per questa giornata non c'era un piano."
    />
  ) : (
    <EmptyState
      icon={CalendarDays}
      title="Ancora niente in programma"
      text="Genera la settimana e i pasti di questo giorno compariranno qui."
      action={
        <Link className="btn btn-primary" to={settimana} state={{ genera: true }}>
          <Sparkles size={16} /> Genera la settimana
        </Link>
      }
    />
  );

  return (
    <>
      {/* Una riga sola: indietro, il giorno, e le frecce per il giorno prima e dopo.
          Il ritorno alla settimana è l'indietro (e la scheda in fondo): un terzo
          pulsante «Settimana» ripeteva un comando che c'è già. */}
      <div className="day-page-head">
        <button className="btn btn-secondary btn-icon" onClick={tornaIndietro} title="Indietro">
          <ArrowLeft size={16} />
        </button>
        <div className="day-page-title">
          <h1 className="page-title">
            {data.is_today ? 'Oggi' : `${data.day_name} ${Number(data.date.slice(8, 10))}`}
          </h1>
          <p className="page-subtitle">
            {data.is_today
              ? formatDate(data.date, { weekday: 'long', day: 'numeric', month: 'long' })
              : formatDate(data.date, { month: 'long' })}{' '}
            · {data.diet.daily_calories} kcal
          </p>
        </div>
        <button className="btn btn-secondary btn-icon" onClick={() => vaiA(-1)} title="Giorno prima">
          <ChevronLeft size={16} />
        </button>
        <button className="btn btn-secondary btn-icon" onClick={() => vaiA(1)} title="Giorno dopo">
          <ChevronRight size={16} />
        </button>
      </div>

      {data.is_skipped && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>Giornata saltata.</strong> Quello che c'era in programma si è accodato
            ai giorni dopo.
          </div>
        </div>
      )}

      <div className="page-main">
        <DayMeals
          meals={data.meals}
          onChanged={load}
          vuoto={vuoto}
          conAdesso={data.is_today}
          dettagli
        />
      </div>
    </>
  );
}
