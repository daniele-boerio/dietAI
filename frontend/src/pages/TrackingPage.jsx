import { useEffect, useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { api, formatDate, formatNumber } from '../api';
import { useApp } from '../App';
import EmptyState from '../components/EmptyState';
import YearHeatmap from '../components/YearHeatmap';

// Gauge ad anello disegnato con conic-gradient: nessuna libreria di grafici per tre
// cerchi e sette barre, che qui è tutto quello che serve.
function Gauge({ label, value, target, color }) {
  const ratio = target ? Math.min(value / target, 1.35) : 0;
  const pct = Math.min(ratio * 100, 100);
  return (
    <div className="gauge">
      <div
        className="gauge-ring"
        style={{
          background: `conic-gradient(${color} ${pct}%, var(--bg-surface) ${pct}% 100%)`,
        }}
      >
        <span className="gauge-value">{formatNumber(value, 0)}g</span>
      </div>
      <div className="gauge-label">
        {label}
        <br />
        <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
          target {formatNumber(target, 0)}g
        </span>
      </div>
    </div>
  );
}

// Una pagina, due sguardi sugli stessi dati: la settimana in dettaglio e l'anno a
// colpo d'occhio. Il selettore in alto sceglie quale.
export default function TrackingPage() {
  const [view, setView] = useState('week');

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Andamento</h1>
          <p className="page-subtitle">
            {view === 'week'
              ? 'Quanto il piano generato aderisce alla dieta, giorno per giorno.'
              : "Quanto hai rispettato la dieta ogni giorno dell'anno."}
          </p>
        </div>
      </div>

      <div className="week-toolbar">
        <div className="week-tabs">
          <button
            className={`week-tab ${view === 'week' ? 'active' : ''}`}
            onClick={() => setView('week')}
          >
            Settimana
          </button>
          <button
            className={`week-tab ${view === 'year' ? 'active' : ''}`}
            onClick={() => setView('year')}
          >
            Anno
          </button>
        </div>
      </div>

      {view === 'week' ? <WeeklyView /> : <YearHeatmap />}
    </>
  );
}

function WeeklyView() {
  const { addToast } = useApp();
  const [weeks, setWeeks] = useState([]);
  const [selected, setSelected] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getWeeks().then(setWeeks).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .getTracking(selected || undefined)
      .then(setData)
      .catch((e) => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  }, [selected, addToast]);

  if (loading) return <div className="spinner" />;
  if (!data) return null;

  const summary = data.weekly_summary;
  const maxCalories = Math.max(
    ...data.days.map((d) => Math.max(d.totals.planned_calories, d.totals.target_calories)),
    1
  );
  const planned = data.days.some((d) => d.totals.planned_calories > 0);

  return (
    <>
      <div className="week-toolbar" style={{ marginTop: -4 }}>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          style={{ width: 'auto' }}
        >
          <option value="">Settimana corrente</option>
          {weeks
            .filter((w) => !w.is_current)
            .map((w) => (
              <option key={w.id} value={w.week_start_date}>
                Dal {formatDate(w.week_start_date)}
              </option>
            ))}
        </select>
      </div>

      {!planned ? (
        <EmptyState
          icon={TrendingUp}
          title="Ancora niente da misurare"
          text="Genera il piano della settimana: qui vedrai lo scarto tra quello che la dieta prescrive e quello che è finito nel piano."
        />
      ) : (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <div className="stat-value">{summary.avg_daily_calories_planned}</div>
              <div className="stat-label">
                kcal medie al giorno · target {summary.avg_daily_calories_target}
              </div>
            </div>
            <div className="stat-tile">
              <div className="stat-value">{summary.compliance_pct}%</div>
              <div className="stat-label">
                Pasti entro il ±10% ({summary.meals_in_range} su {summary.meals_planned})
              </div>
            </div>
            <div className="stat-tile">
              {/* I giorni saltati non finiscono al denominatore: non c'era niente
                  da seguire, la spesa non era ancora stata fatta. */}
              <div className="stat-value">
                {summary.days_followed}/{7 - (summary.days_skipped || 0)}
              </div>
              <div className="stat-label">Giorni seguiti davvero</div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">Calorie: pianificate vs prescritte</div>
            <div className="tracking-chart">
              {data.days.map((day) => (
                <div
                  key={day.date}
                  className={`tracking-day ${day.is_skipped ? 'skipped' : ''}`}
                >
                  <div className="tracking-bars">
                    <div
                      className="tracking-bar target"
                      style={{ height: `${(day.totals.target_calories / maxCalories) * 100}%` }}
                      title={`Target ${day.totals.target_calories} kcal`}
                    />
                    <div
                      className={`tracking-bar planned ${day.totals.color}`}
                      style={{ height: `${(day.totals.planned_calories / maxCalories) * 100}%` }}
                      title={`Pianificate ${day.totals.planned_calories} kcal`}
                    />
                  </div>
                  <div className="tracking-day-label">{day.day_name.slice(0, 3)}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">Macro medi della settimana</div>
            <div className="gauge-row">
              <Gauge
                label="Proteine"
                value={summary.macro_averages.protein_g}
                target={summary.macro_targets.protein_g}
                color="var(--macro-p)"
              />
              <Gauge
                label="Carboidrati"
                value={summary.macro_averages.carbs_g}
                target={summary.macro_targets.carbs_g}
                color="var(--macro-c)"
              />
              <Gauge
                label="Grassi"
                value={summary.macro_averages.fat_g}
                target={summary.macro_targets.fat_g}
                color="var(--macro-f)"
              />
            </div>
          </div>

          <div className="card">
            <div className="card-title">Giorno per giorno</div>
            {data.days.map((day) =>
              // Un giorno saltato non ha uno scarto da mostrare: non è andato male,
              // non c'è proprio stato.
              day.is_skipped || day.meals.every((m) => m.is_skipped) ? (
                <div key={day.date} className="day-compliance">
                  <span className="compliance-dot grey" />
                  <strong style={{ minWidth: 92, color: 'var(--text-muted)' }}>
                    {day.day_name}
                  </strong>
                  <span style={{ color: 'var(--text-muted)' }}>
                    Giornata saltata: non entra nelle medie
                  </span>
                </div>
              ) : (
                <div key={day.date} className="day-compliance">
                  <span className={`compliance-dot ${day.totals.color}`} />
                  <strong style={{ minWidth: 92 }}>{day.day_name}</strong>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    {day.totals.planned_calories} / {day.totals.target_calories} kcal
                  </span>
                  <span
                    style={{
                      marginLeft: 'auto',
                      color:
                        day.totals.delta > 0 ? 'var(--terracotta)' : 'var(--text-secondary)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {day.totals.delta > 0 ? '+' : ''}
                    {day.totals.delta} kcal
                  </span>
                  {day.is_followed && <span className="badge badge-accent">Seguito</span>}
                </div>
              )
            )}
          </div>
        </>
      )}
    </>
  );
}
