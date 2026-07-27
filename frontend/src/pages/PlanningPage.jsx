import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Archive,
  CalendarDays,
  CalendarOff,
  ChevronLeft,
  ChevronRight,
  Lock,
  RefreshCw,
  Sparkles,
  Unlock,
} from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import GenerationLog from '../components/GenerationLog';
import LoadError from '../components/LoadError';
import WeekGrid from '../components/WeekGrid';
import { scalatiDallaDispensa } from '../lib/pantry';

const GIORNO_MS = 86400000;

// Le date qui si scrivono e si leggono nel fuso locale: `toISOString()` passa da UTC
// e a fine giornata restituirebbe il lunedì sbagliato.
const isoOf = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')}`;

const parseIso = (iso) => {
  const [y, m, d] = (iso || '').split('-').map(Number);
  return y && m && d ? new Date(y, m - 1, d) : null;
};

const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

const mondayOf = (d) => addDays(d, -((d.getDay() + 6) % 7));

const todayIso = () => isoOf(new Date());

// "Lunedì e martedì", con le maiuscole al posto giusto per stare in mezzo a una frase.
function elencaGiorni(nomi) {
  const [primo, ...resto] = nomi.map((n, i) => (i === 0 ? n : n.toLowerCase()));
  if (!resto.length) return primo;
  return [primo, ...resto.slice(0, -1)].join(', ') + ' e ' + resto[resto.length - 1];
}

// Le settimane vicine hanno un nome, le altre si contano.
function etichettaSettimana(offset) {
  if (offset === 0) return 'Questa settimana';
  if (offset === 1) return 'Settimana prossima';
  if (offset === -1) return 'Settimana scorsa';
  return offset < 0 ? `${-offset} settimane fa` : `Fra ${offset} settimane`;
}

// Una sola pagina per tutte le settimane: cambia solo il lunedì che si chiede.
// Il piano si sfoglia in tutte e due le direzioni — indietro per rivedere cos'è
// stato (e segnare com'è andata), avanti quanto si vuole pianificare. La settimana
// prossima resta modificabile anche quando quella corrente è bloccata.
export default function PlanningPage() {
  const { addToast } = useApp();
  const navigate = useNavigate();
  const { weekStart } = useParams();
  const [week, setWeek] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [busyMealId, setBusyMealId] = useState(null);
  // Separato da `busyMealId`: la card è occupata in tutti e due i casi, ma l'icona
  // che gira è quella della rigenerazione e solo lì ha senso.
  const [followingMealId, setFollowingMealId] = useState(null);
  const [busyDayId, setBusyDayId] = useState(null);
  const [confirmUnlock, setConfirmUnlock] = useState(false);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  // Serve a distinguere "non sta generando" da "ha appena finito", per il messaggio.
  const wasGenerating = useRef(false);

  // Quale settimana si sta guardando. `/plan` è quella corrente e `/plan/next` la
  // prossima — i due indirizzi di prima, che restano validi ovunque siano linkati;
  // le altre si scrivono col loro lunedì.
  const { lunedi, offset } = useMemo(() => {
    const corrente = mondayOf(new Date());
    const scelto =
      weekStart === 'next'
        ? addDays(corrente, 7)
        : mondayOf(parseIso(weekStart) || corrente);
    return {
      lunedi: scelto,
      offset: Math.round((scelto - corrente) / (7 * GIORNO_MS)),
    };
  }, [weekStart]);

  const lunediIso = isoOf(lunedi);
  const domenicaIso = isoOf(addDays(lunedi, 6));

  const load = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setLoading(true);
      try {
        const data = await api.getWeekByDate(lunediIso);
        setWeek(data);
        setError(null);
        return data;
      } catch (e) {
        // Il polling della generazione non deve cancellare la settimana già a
        // schermo per un buco di rete: lì si riprova e basta.
        if (!silent) {
          setError(e.message);
          addToast(e.message, 'error');
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [lunediIso, addToast]
  );

  // Tornando sulla settimana corrente si rimette l'indirizzo corto: è quello che sta
  // nel menu, e con la data esplicita resterebbe "giusto" anche il giorno dopo, quando
  // quel lunedì non è più questa settimana.
  const vaiA = (delta) => {
    const meta = addDays(lunedi, delta * 7);
    navigate(delta === -offset ? '/plan' : `/plan/${isoOf(meta)}`);
  };

  useEffect(() => {
    load();
  }, [load]);

  // La generazione vive sul server, non in questa pagina: se cambi scheda, torni
  // indietro o ricarichi, il lavoro prosegue. Finché il server la dà per in corso si
  // ricontrolla ogni pochi secondi, e al termine si avvisa — anche se il pulsante
  // l'aveva premuto un'altra sessione.
  useEffect(() => {
    if (!week?.is_generating) {
      if (wasGenerating.current) {
        wasGenerating.current = false;
        addToast('Settimana pronta ✓');
      }
      return;
    }
    wasGenerating.current = true;
    const timer = setInterval(() => load({ silent: true }), 4000);
    return () => clearInterval(timer);
  }, [week?.is_generating, load, addToast]);

  const generate = async (regenerateAll = false) => {
    setGenerating(true);
    setConfirmRegenerate(false);
    try {
      const data = await api.generateWeek(week.id, regenerateAll);
      setWeek(data);
      const { filled, missing } = data.generation || {};
      addToast(
        missing
          ? `Generati ${filled} pasti (${missing} non riusciti, riprova)`
          : `${filled} ricette pronte ✓`
      );
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setGenerating(false);
    }
  };

  const regenerate = async (meal) => {
    setBusyMealId(meal.id);
    try {
      await api.regenerateMeal(meal.id);
      await load();
      addToast('Nuova ricetta pronta ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusyMealId(null);
    }
  };

  // "L'ho seguito" / "Ho mangiato altro" dalla griglia, senza aprire il pasto.
  // La risposta è il singolo pasto, ma la settimana va riletta lo stesso: "ho
  // mangiato altro" accoda la ricetta su un'altra casella (o sulla settimana dopo),
  // e quella casella qui è a schermo.
  const setFollowed = async (meal, value) => {
    setFollowingMealId(meal.id);
    try {
      const updated = await api.setFollowed(meal.id, value);
      await load({ silent: true });
      if (updated.moved_to) {
        addToast(
          `Ricetta rimandata a ${updated.moved_to.day_name.toLowerCase()}` +
            (updated.moved_to.next_week ? ' della settimana prossima' : '')
        );
      } else {
        addToast(value ? 'Segnato: seguito ✓' : 'Segnato: hai mangiato altro');
      }
      // La dispensa si scala mangiando: se cala di nascosto, del numero non si fida
      // più nessuno.
      if (updated.pantry_used?.length) {
        addToast(scalatiDallaDispensa(updated.pantry_used), 'info');
      }
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setFollowingMealId(null);
    }
  };

  const toggleDaySkip = async (day) => {
    setBusyDayId(day.id);
    try {
      setWeek(await api.setDaySkipped(day.id, !day.is_skipped));
      addToast(
        day.is_skipped
          ? `${day.day_name} torna in programma ✓`
          : `${day.day_name} saltato: le ricette si sono accodate ai giorni dopo ✓`
      );
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusyDayId(null);
    }
  };

  const unlock = async () => {
    try {
      const data = await api.unlockWeek(week.id);
      setWeek(data);
      setConfirmUnlock(false);
      addToast('Piano sbloccato');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  if (loading) return <div className="spinner" />;
  if (!week) return <LoadError message={error} onRetry={load} />;

  const emptySlots = week.meals_total - week.meals_filled;
  // Solo i giorni saltati perché la spesa non è arrivata in tempo, cioè quelli già
  // passati: le giornate saltate a mano sono da oggi in avanti e non c'entrano con
  // questo avviso, che parla di spesa.
  const skipped = week.days.filter((d) => d.is_skipped && d.date < todayIso());
  // `generating` è la richiesta partita da qui; `is_generating` è quella che il
  // server sa essere in corso — comprese quelle avviate prima di ricaricare.
  const busy = generating || week.is_generating;
  // Una settimana passata in cui non si è mai pianificato niente: non viene creata
  // solo perché la si è sfogliata, quindi arriva senza id e senza giorni.
  const mai = week.id == null;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">{etichettaSettimana(offset)}</h1>
          <p className="page-subtitle">
            Dal {formatDate(lunediIso)} al {formatDate(domenicaIso)}
            {mai
              ? ' · nessun piano'
              : ` · ${week.meals_filled} di ${week.meals_total} pasti pianificati`}
          </p>
        </div>

        {/* Il passato si consulta: niente pulsanti che spendono una chiamata al
            modello per rifare giorni già passati. */}
        {!week.is_past && (
          <div className="page-actions">
            {week.is_locked ? (
              <button className="btn btn-secondary" onClick={() => setConfirmUnlock(true)}>
                <Unlock size={16} /> Sblocca
              </button>
            ) : (
              <>
                {/* Rifare tutto costa una chiamata al modello su tutta la settimana:
                    sta in secondo piano e passa da una conferma. */}
                {week.meals_filled > 0 && (
                  <button
                    className="btn btn-secondary"
                    onClick={() => setConfirmRegenerate(true)}
                    disabled={busy}
                  >
                    <RefreshCw size={16} /> Rigenera tutto
                  </button>
                )}
                {emptySlots > 0 && (
                  <button
                    className="btn btn-primary"
                    onClick={() => generate(false)}
                    disabled={busy}
                  >
                    {busy ? <span className="spinner-inline" /> : <Sparkles size={16} />}
                    {emptySlots === week.meals_total
                      ? 'Genera la settimana'
                      : `Riempi i ${emptySlots} vuoti`}
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Il piano si sfoglia una settimana alla volta, indietro e avanti senza
          limite: indietro per rivedere cos'è stato, avanti per pianificare quanto si
          vuole. Le frecce restano sempre attive — una settimana mai pianificata si
          apre lo stesso, e dice che è vuota. */}
      <div className="week-toolbar">
        <div className="week-nav">
          <button
            className="week-nav-btn"
            onClick={() => vaiA(-1)}
            title="Settimana precedente"
            aria-label="Settimana precedente"
          >
            <ChevronLeft />
          </button>
          <span className="week-nav-label">
            {formatDate(lunediIso, { day: 'numeric', month: 'short' })} –{' '}
            {formatDate(domenicaIso, { day: 'numeric', month: 'short' })}
          </span>
          <button
            className="week-nav-btn"
            onClick={() => vaiA(1)}
            title="Settimana successiva"
            aria-label="Settimana successiva"
          >
            <ChevronRight />
          </button>
        </div>

        {offset !== 0 && (
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/plan')}>
            <CalendarDays size={15} /> Torna a questa settimana
          </button>
        )}

        {!mai && !week.is_past && (
          <span className="week-progress">
            {emptySlots > 0 ? `${emptySlots} pasti da riempire` : 'Piano completo'}
          </span>
        )}
      </div>

      {week.is_past && !mai && (
        <div className="notice notice-lock">
          <Archive />
          <div>
            <strong>Settimana passata.</strong> È archiviata: le ricette si rileggono e
            si possono ancora votare o segnare come seguite dal dettaglio del pasto, ma
            il piano non si rigenera — quei giorni sono già stati.
          </div>
        </div>
      )}

      {/* Il piano segue la spesa, non il calendario: i giorni passati senza spesa
          sono già stati saltati e le loro ricette scalate in avanti. Va detto, o
          l'utente si ritrova la settimana rimescolata senza sapere perché. */}
      {!week.is_past && !week.is_locked && skipped.length > 0 && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>
              {elencaGiorni(skipped.map((d) => d.day_name))}{' '}
              {skipped.length === 1 ? 'saltato' : 'saltati'}: la spesa non risulta fatta.
            </strong>{' '}
            Le ricette sono slittate in avanti — quelle che non ci stavano più sono
            passate alla <Link to="/plan/next">settimana prossima</Link> — e quei giorni
            non entrano nella lista della spesa. Quando vai a fare la spesa segnalalo
            dalla <Link to="/shopping">lista</Link>: da lì il piano si blocca com'è.
          </div>
        </div>
      )}

      {!week.is_past && week.is_locked && (
        <div className="notice notice-lock">
          <Lock />
          <div>
            <strong>Piano bloccato fino al {formatDate(week.lock_expires_at)}.</strong> La
            spesa è fatta: cambiare le ricette adesso vorrebbe dire buttare il cibo. Se ti
            serve modificare qualcosa, lavora sulla{' '}
            <Link to="/plan/next">settimana prossima</Link>.
          </div>
        </div>
      )}

      {mai ? (
        <EmptyState
          icon={CalendarOff}
          title="Nessun piano per questa settimana"
          text="In questi giorni non hai pianificato niente — o l'app non c'era ancora. Le settimane passate restano come sono: si sfogliano, non si riempiono."
          action={
            <button className="btn btn-secondary" onClick={() => navigate('/plan')}>
              <CalendarDays size={16} /> Torna a questa settimana
            </button>
          }
        />
      ) : busy ? (
        <div className="generating">
          <div className="spinner" style={{ padding: 0 }} />
          <h3>Sto costruendo la settimana</h3>
          <p>
            L'AI sta incastrando macro, stagionalità e avanzi per non farti buttare
            mezza zucchina. Ci vogliono da trenta secondi a un paio di minuti.
          </p>
          <GenerationLog weekId={week.id} />
        </div>
      ) : (
        <WeekGrid
          week={week}
          busyMealId={busyMealId}
          followingMealId={followingMealId}
          busyDayId={busyDayId}
          onRegenerate={regenerate}
          onFollowed={setFollowed}
          onToggleDaySkip={toggleDaySkip}
        />
      )}

      {confirmRegenerate && (
        <ConfirmDialog
          title={`Rigenerare tutte e ${week.meals_filled} le ricette?`}
          text={
            `Butti via il piano attuale e ne fai scrivere uno nuovo da zero: è una ` +
            `chiamata al modello su tutta la settimana, la cosa più costosa che fa ` +
            `l'app. Le ricette di adesso restano nel ricettario, e i pasti fissi o ` +
            `che gestisci tu non vengono toccati. Se ti serve cambiare un piatto solo, ` +
            `conviene rigenerare quello dalla sua card.`
          }
          confirmLabel="Sì, rigenera tutto"
          busy={busy}
          onConfirm={() => generate(true)}
          onCancel={() => setConfirmRegenerate(false)}
        />
      )}

      {confirmUnlock && (
        <ConfirmDialog
          title="Sbloccare il piano?"
          text="Il blocco esiste perché la spesa è già stata fatta: sbloccando potresti ritrovarti con ingredienti comprati e mai usati. Di solito conviene modificare la settimana prossima."
          confirmLabel="Sblocca comunque"
          danger
          onConfirm={unlock}
          onCancel={() => setConfirmUnlock(false)}
        />
      )}
    </>
  );
}
