import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { CalendarOff, Lock, RefreshCw, Sparkles, Unlock } from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import WeekGrid from '../components/WeekGrid';

const todayIso = () => new Date().toISOString().slice(0, 10);

// "Lunedì e martedì", con le maiuscole al posto giusto per stare in mezzo a una frase.
function elencaGiorni(nomi) {
  const [primo, ...resto] = nomi.map((n, i) => (i === 0 ? n : n.toLowerCase()));
  if (!resto.length) return primo;
  return [primo, ...resto.slice(0, -1)].join(', ') + ' e ' + resto[resto.length - 1];
}

// Una sola pagina per le due settimane: cambia solo quale endpoint si chiama.
// La settimana prossima è sempre modificabile, anche quando quella corrente è bloccata.
export default function PlanningPage({ nextWeek = false }) {
  const { addToast } = useApp();
  const navigate = useNavigate();
  const [week, setWeek] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [busyMealId, setBusyMealId] = useState(null);
  const [busyDayId, setBusyDayId] = useState(null);
  const [confirmUnlock, setConfirmUnlock] = useState(false);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  // Serve a distinguere "non sta generando" da "ha appena finito", per il messaggio.
  const wasGenerating = useRef(false);

  const load = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setLoading(true);
      try {
        const data = nextWeek ? await api.getNextWeek() : await api.getCurrentWeek();
        setWeek(data);
        return data;
      } catch (e) {
        if (!silent) addToast(e.message, 'error');
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [nextWeek, addToast]
  );

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

  const toggleRecurring = async (meal) => {
    try {
      await api.setRecurring(meal.id, !meal.is_recurring);
      await load();
      addToast(
        meal.is_recurring
          ? 'Pasto non più fisso'
          : 'Pasto fisso: si ripeterà ogni settimana ✓'
      );
    } catch (e) {
      addToast(e.message, 'error');
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
  if (!week) return null;

  const emptySlots = week.meals_total - week.meals_filled;
  // Solo i giorni saltati perché la spesa non è arrivata in tempo, cioè quelli già
  // passati: le giornate saltate a mano sono da oggi in avanti e non c'entrano con
  // questo avviso, che parla di spesa.
  const skipped = week.days.filter((d) => d.is_skipped && d.date < todayIso());
  // `generating` è la richiesta partita da qui; `is_generating` è quella che il
  // server sa essere in corso — comprese quelle avviate prima di ricaricare.
  const busy = generating || week.is_generating;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">
            {nextWeek ? 'Settimana prossima' : 'Questa settimana'}
          </h1>
          <p className="page-subtitle">
            Dal {formatDate(week.week_start_date)} · {week.meals_filled} di{' '}
            {week.meals_total} pasti pianificati
          </p>
        </div>

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
      </div>

      <div className="week-toolbar">
        <div className="week-tabs">
          <button
            className={`week-tab ${!nextWeek ? 'active' : ''}`}
            onClick={() => navigate('/plan')}
          >
            Questa settimana
          </button>
          <button
            className={`week-tab ${nextWeek ? 'active' : ''}`}
            onClick={() => navigate('/plan/next')}
          >
            Prossima
          </button>
        </div>
        <span className="week-progress">
          {emptySlots > 0 ? `${emptySlots} pasti da riempire` : 'Piano completo'}
        </span>
      </div>

      {/* Il piano segue la spesa, non il calendario: i giorni passati senza spesa
          sono già stati saltati e le loro ricette scalate in avanti. Va detto, o
          l'utente si ritrova la settimana rimescolata senza sapere perché. */}
      {!week.is_locked && skipped.length > 0 && (
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

      {week.is_locked && (
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

      {busy ? (
        <div className="generating">
          <div className="spinner" style={{ padding: 0 }} />
          <h3>Sto costruendo la settimana</h3>
          <p>
            L'AI sta incastrando macro, stagionalità e avanzi per non farti buttare
            mezza zucchina. Ci vogliono da trenta secondi a un paio di minuti.
          </p>
        </div>
      ) : (
        <WeekGrid
          week={week}
          busyMealId={busyMealId}
          busyDayId={busyDayId}
          onRegenerate={regenerate}
          onToggleRecurring={toggleRecurring}
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
