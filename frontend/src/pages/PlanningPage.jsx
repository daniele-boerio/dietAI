import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Lock, LockOpen, Sparkles, Unlock } from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import WeekGrid from '../components/WeekGrid';

// Una sola pagina per le due settimane: cambia solo quale endpoint si chiama.
// La settimana prossima è sempre modificabile, anche quando quella corrente è bloccata.
export default function PlanningPage({ nextWeek = false }) {
  const { addToast } = useApp();
  const navigate = useNavigate();
  const [week, setWeek] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [busyMealId, setBusyMealId] = useState(null);
  const [confirmUnlock, setConfirmUnlock] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = nextWeek ? await api.getNextWeek() : await api.getCurrentWeek();
      setWeek(data);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [nextWeek, addToast]);

  useEffect(() => {
    load();
  }, [load]);

  const generate = async () => {
    setGenerating(true);
    try {
      const data = await api.generateWeek(week.id);
      setWeek(data);
      const { filled, missing } = data.generation || {};
      addToast(
        missing
          ? `Generati ${filled} pasti (${missing} non riusciti, riprova)`
          : `Settimana generata: ${filled} ricette ✓`
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
            <button className="btn btn-primary" onClick={generate} disabled={generating}>
              {generating ? <span className="spinner-inline" /> : <Sparkles size={16} />}
              {emptySlots === week.meals_total ? 'Genera la settimana' : 'Riempi i vuoti'}
            </button>
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

      {generating ? (
        <div className="generating">
          <div className="spinner" style={{ padding: 0 }} />
          <h3>Sto costruendo la settimana</h3>
          <p>
            Claude sta incastrando macro, stagionalità e avanzi per non farti buttare
            mezza zucchina. Ci vogliono da trenta secondi a un paio di minuti.
          </p>
        </div>
      ) : (
        <WeekGrid
          week={week}
          busyMealId={busyMealId}
          onRegenerate={regenerate}
          onToggleRecurring={toggleRecurring}
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
