import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Flame } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import EmptyState from './EmptyState';

const MONTHS = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];
const WEEKDAYS = ['Lun', '', 'Mer', '', 'Ven', '', ''];

const STATUS_LABEL = {
  full: 'Seguita del tutto',
  partial: 'Seguita in parte',
  missed: 'Non seguita',
};

const toIso = (d) => {
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
};

// Lunedì della settimana che contiene `d` (0 = lunedì, come tutta l'app).
const mondayOf = (d) => {
  const out = new Date(d);
  out.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  out.setHours(0, 0, 0, 0);
  return out;
};

// Costruisce le colonne-settimana del calendario: una colonna per settimana, sette
// celle per colonna (lun→dom). Le celle dei giorni fuori dall'anno restano vuote, così
// gennaio e dicembre non partono a metà colonna sfalsati.
function buildCalendar(year, days, today) {
  const jan1 = new Date(year, 0, 1);
  const dec31 = new Date(year, 11, 31);
  const columns = [];

  for (let cursor = mondayOf(jan1); cursor <= dec31; cursor.setDate(cursor.getDate() + 7)) {
    const cells = [];
    for (let r = 0; r < 7; r++) {
      const d = new Date(cursor);
      d.setDate(cursor.getDate() + r);
      const inYear = d.getFullYear() === year;
      const iso = toIso(d);
      cells.push({
        iso,
        date: new Date(d),
        inYear,
        future: d > today,
        status: inYear ? days[iso] : undefined,
      });
    }
    columns.push(cells);
  }

  // Etichetta del mese sopra la colonna dove cade il suo primo giorno.
  const firstMonday = mondayOf(jan1);
  const monthAt = {};
  for (let m = 0; m < 12; m++) {
    const first = new Date(year, m, 1);
    const col = Math.floor((first - firstMonday) / (7 * 86400000));
    monthAt[col] = MONTHS[m];
  }

  return { columns, monthAt };
}

// Calendario annuale dell'aderenza: ogni giorno una casellina colorata come quanto la
// dieta è stata rispettata, per vedere l'anno intero a colpo d'occhio.
export default function YearHeatmap() {
  const { addToast } = useApp();
  const [data, setData] = useState(null);
  const [year, setYear] = useState(null); // null = "corrente", lo decide il backend
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .getYearTracking(year || undefined)
      .then(setData)
      .catch((e) => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  }, [year, addToast]);

  const today = useMemo(() => {
    const t = new Date();
    t.setHours(23, 59, 59, 999);
    return t;
  }, []);

  const calendar = useMemo(
    () => (data ? buildCalendar(data.year, data.days, today) : null),
    [data, today]
  );

  if (loading && !data) return <div className="spinner" />;
  if (!data) return null;

  const years = data.available_years || [data.year];
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const go = (delta) => setYear(data.year + delta);

  return (
    <>
      <div className="week-toolbar">
        <div className="year-nav">
          <button
            className="icon-button"
            onClick={() => go(-1)}
            disabled={data.year <= minYear}
            aria-label="Anno precedente"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="year-nav-label">{data.year}</span>
          <button
            className="icon-button"
            onClick={() => go(1)}
            disabled={data.year >= maxYear}
            aria-label="Anno successivo"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      {data.tracked_days === 0 ? (
        <EmptyState
          icon={Flame}
          title={`Nessun giorno tracciato nel ${data.year}`}
          text="Man mano che segni «l'ho seguito» o «ho mangiato altro» sui pasti, qui si riempie il calendario dell'anno."
        />
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <div className="stat-value">{data.score_pct}%</div>
              <div className="stat-label">
                Aderenza sull'anno · su {data.tracked_days} giorni tracciati
              </div>
            </div>
            <div className="stat-tile">
              <div className="stat-value">{data.counts.full}</div>
              <div className="stat-label">Giorni seguiti in pieno</div>
            </div>
            <div className="stat-tile">
              <div className="stat-value">
                {data.best_streak} <Flame size={18} style={{ verticalAlign: '-2px' }} />
              </div>
              <div className="stat-label">Serie più lunga di giorni pieni</div>
            </div>
          </div>

          <div className="card heatmap-card">
            <div className="heatmap-scroll">
              <div className="heatmap">
                <div className="heatmap-months">
                  <div className="heatmap-gutter" />
                  {calendar.columns.map((_, i) => (
                    <div key={i} className="heatmap-month">
                      {calendar.monthAt[i] || ''}
                    </div>
                  ))}
                </div>

                <div className="heatmap-body">
                  <div className="heatmap-weekdays">
                    {WEEKDAYS.map((w, i) => (
                      <span key={i}>{w}</span>
                    ))}
                  </div>

                  <div className="heatmap-columns">
                    {calendar.columns.map((cells, i) => (
                      <div key={i} className="heatmap-col">
                        {cells.map((cell) => {
                          if (!cell.inYear) return <div key={cell.iso} className="heatmap-cell pad" />;
                          const status = cell.status || (cell.future ? 'future' : 'untracked');
                          const label = STATUS_LABEL[cell.status] || (cell.future ? '' : 'Nessun dato');
                          return (
                            <div
                              key={cell.iso}
                              className={`heatmap-cell ${status}`}
                              title={
                                cell.future
                                  ? ''
                                  : `${cell.date.toLocaleDateString('it-IT', {
                                      day: 'numeric',
                                      month: 'long',
                                    })} · ${label}`
                              }
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="heatmap-legend">
              <span className="heatmap-legend-item">
                <span className="heatmap-cell missed" /> Non seguita ({data.counts.missed})
              </span>
              <span className="heatmap-legend-item">
                <span className="heatmap-cell partial" /> In parte ({data.counts.partial})
              </span>
              <span className="heatmap-legend-item">
                <span className="heatmap-cell full" /> Seguita ({data.counts.full})
              </span>
              <span className="heatmap-legend-item">
                <span className="heatmap-cell untracked" /> Nessun dato
              </span>
            </div>
          </div>
        </>
      )}
    </>
  );
}
