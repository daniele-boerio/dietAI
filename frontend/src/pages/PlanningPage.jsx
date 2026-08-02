import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  Archive,
  CalendarDays,
  CalendarOff,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import GenerationLog from '../components/GenerationLog';
import LoadError from '../components/LoadError';
import WeekGrid from '../components/WeekGrid';
import { nonScalatiDallaDispensa, scalatiDallaDispensa } from '../lib/pantry';

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
// stato (e segnare com'è andata), avanti quanto si vuole pianificare — e si modifica
// sempre, passato compreso: quello che è stato comprato sta in dispensa, e la
// dispensa la corregge chi apre il frigo.
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
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  // Serve a distinguere "non sta generando" da "ha appena finito", per il messaggio.
  const wasGenerating = useRef(false);
  // La colonna di oggi e la settimana per cui ci si è già spostati (vedi sotto).
  const oggiRef = useRef(null);
  const scrollFatto = useRef(null);

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

  // Sul telefono i sette giorni stanno uno sotto l'altro, e la settimana si apre su
  // lunedì: di domenica vuol dire sei giorni di scorrimento prima di arrivare a quello
  // per cui si è entrati — vedere cosa si mangia stasera, o segnare com'è andata. La
  // pagina ci si porta da sé.
  //
  // Una volta sola per settimana aperta, ed è il motivo per cui la memoria sta qui e
  // non dentro `WeekGrid`: la griglia si smonta a ogni caricamento non silenzioso
  // (rigenerare un pasto ne fa uno), e ritrovarsi sbalzati su oggi dopo aver premuto
  // ↻ su sabato sembrerebbe che l'app abbia perso il segno.
  useEffect(() => {
    const colonna = oggiRef.current;
    // Niente colonna vuol dire che oggi non è in questa settimana: si sta sfogliando
    // il passato o il futuro, e non c'è nessun giorno da cercare.
    if (loading || !colonna || scrollFatto.current === lunediIso) return;
    // Sopra i 1100px i giorni sono affiancati e `.day-column` è `display: contents`:
    // non ha nemmeno un riquadro da misurare, e non c'è niente da raggiungere.
    if (window.matchMedia('(min-width: 1100px)').matches) return;

    scrollFatto.current = lunediIso;
    // Se oggi è già in vista — di lunedì, di solito — muovere la pagina sarebbe solo
    // un sussulto che nasconde la testata senza far vedere niente di nuovo.
    const { top } = colonna.getBoundingClientRect();
    if (top >= 0 && top < window.innerHeight * 0.6) return;
    colonna.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'auto'
        : 'smooth',
      block: 'start',
    });
    // I due momenti in cui la griglia compare: finito il caricamento e finita la
    // generazione. Le riletture silenziose non rientrano qui, e va bene così.
  }, [loading, lunediIso, week?.is_generating]);

  // La generazione vive sul server, non in questa pagina: se cambi scheda, torni
  // indietro o ricarichi, il lavoro prosegue. Finché il server la dà per in corso si
  // ricontrolla ogni pochi secondi, e al termine si avvisa — anche se il pulsante
  // l'aveva premuto un'altra sessione.
  //
  // Com'è andata lo dice la settimana, non la risposta della POST: quella viaggia su
  // una connessione che il proxy ha quasi sempre già chiuso (una generazione dura
  // minuti). Per questo l'esito va guardato qui, e "non sta più generando" da solo non
  // vuol dire riuscita: annunciare "Settimana pronta ✓" su un fallimento è come
  // l'abbiamo scoperto.
  useEffect(() => {
    if (!week?.is_generating) {
      if (wasGenerating.current) {
        wasGenerating.current = false;
        if (week?.generation_error) addToast(week.generation_error, 'error');
        else addToast('Settimana pronta ✓');
      }
      return;
    }
    wasGenerating.current = true;
    const timer = setInterval(() => load({ silent: true }), 4000);
    return () => clearInterval(timer);
  }, [week?.is_generating, week?.generation_error, load, addToast]);

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
      // La richiesta può morire molto prima della generazione: dura minuti, e davanti
      // c'è un proxy che chiude (nginx a 300s, Cloudflare a 100s). Un errore qui non
      // vuol dire che sia fallita — a saperlo è la settimana, non questa fetch — e
      // dirlo lo stesso manderebbe a ripremere il pulsante, cioè a pagare due volte.
      const dopo = await load({ silent: true });
      if (dopo?.is_generating) {
        addToast('Ci mette più del previsto: resto in ascolto, non serve ripremere');
      } else {
        addToast(dopo?.generation_error || e.message, 'error');
      }
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
      // più nessuno — e se non cala affatto va detto perché, o sembra un pulsante rotto.
      if (updated.pantry_used?.length) {
        addToast(scalatiDallaDispensa(updated.pantry_used), 'info');
      } else if (value && updated.pantry_skipped?.length) {
        addToast(nonScalatiDallaDispensa(updated.pantry_skipped), 'info');
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

  if (loading) return <div className="spinner" />;
  if (!week) return <LoadError message={error} onRetry={load} />;

  const emptySlots = week.meals_total - week.meals_filled;
  // Le giornate saltate: le loro ricette si sono accodate altrove, e va detto o la
  // settimana sembra rimescolata senza motivo.
  const skipped = week.days.filter((d) => d.is_skipped);
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

        <div className="page-actions">
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
            <button className="btn btn-primary" onClick={() => generate(false)} disabled={busy}>
              {busy ? <span className="spinner-inline" /> : <Sparkles size={16} />}
              {emptySlots === week.meals_total
                ? 'Genera la settimana'
                : `Riempi i ${emptySlots} vuoti`}
            </button>
          )}
        </div>
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
        <div className="notice">
          <Archive />
          <div>
            <strong>Settimana passata.</strong> La si legge, si segna com'è andata e si
            corregge come tutte le altre: quello che cambi qui però non entra nella
            lista della spesa, che guarda da oggi in avanti.
          </div>
        </div>
      )}

      {/* L'ultima generazione è fallita. Il toast se n'è andato dopo tre secondi — e
          quasi sempre nessuno era davanti allo schermo quando è arrivato, perché una
          generazione dura minuti — quindi il motivo resta scritto qui finché non se ne
          prova un'altra. Senza, la settimana è solo vuota e non si sa perché. */}
      {!busy && week.generation_error && (
        <div className="notice notice-error">
          <AlertTriangle />
          <div>
            <strong>L'ultima generazione non è andata a buon fine.</strong>{' '}
            {week.generation_error}
          </div>
        </div>
      )}

      {skipped.length > 0 && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>
              {elencaGiorni(skipped.map((d) => d.day_name))}{' '}
              {skipped.length === 1 ? 'saltato' : 'saltati'}.
            </strong>{' '}
            Le ricette di quelle giornate si sono accodate alle prime caselle libere —
            anche sulla <Link to="/plan/next">settimana prossima</Link>, se qui non ce
            n'erano più — e la spesa le compra dove sono finite.
          </div>
        </div>
      )}

      {mai ? (
        <EmptyState
          icon={CalendarOff}
          title="Nessun piano per questa settimana"
          text="In questi giorni non hai pianificato niente — o l'app non c'era ancora. Una settimana passata la si sfoglia com'è: non ne nasce una nuova solo perché la guardi."
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
          todayRef={oggiRef}
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

    </>
  );
}
