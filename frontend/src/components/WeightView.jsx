import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Calculator, Save, Scale, Trash2 } from "lucide-react";
import { api, formatNumber } from "../api";
import { useApp } from "../App";
import EmptyState from "./EmptyState";
import LoadError from "./LoadError";

// Lo storico del peso. Il questionario fotografa il peso di un giorno; qui c'è il
// film, e il momento in cui i target calcolati appartengono a un peso che non c'è più.
// L'app non ricalcola da sola — cambierebbe la dieta sotto i piedi — ma lo propone,
// con un pulsante che riapre il questionario già compilato col peso nuovo.
export default function WeightView() {
  const { addToast } = useApp();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [kg, setKg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api
      .getWeight()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  const salva = async (e) => {
    e.preventDefault();
    const valore = Number(String(kg).replace(",", "."));
    if (!valore) return;
    setBusy(true);
    try {
      setData(await api.saveWeight(valore));
      setKg("");
      addToast("Peso di oggi segnato ✓");
    } catch (err) {
      addToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const togli = async (day) => {
    try {
      setData(await api.deleteWeight(day));
    } catch (err) {
      addToast(err.message, "error");
    }
  };

  if (error) return <LoadError message={error} onRetry={load} />;
  if (!data) return <div className="spinner" />;

  const { entries, recalc, target_weight: riferimento } = data;
  const ultimo = entries[entries.length - 1];

  return (
    <div className="page-split" style={{ "--aside": "380px" }}>
      <div className="page-main">
        {recalc && (
          <div className="notice notice-ok weight-recalc">
            <Calculator />
            <div>
              <strong>
                Hai {recalc.delta < 0 ? "perso" : "preso"}{" "}
                {formatNumber(Math.abs(recalc.delta), 1)} kg
              </strong>{" "}
              da quando i target sono stati calcolati (
              {formatNumber(recalc.target_weight, 1)} kg). Ricalcolarli col peso
              di adesso li riporta ai tuoi numeri.
              <div style={{ marginTop: 10 }}>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    navigate("/diet", {
                      state: { ricalcolaConPeso: recalc.latest_weight },
                    })
                  }
                >
                  <Calculator size={14} /> Ricalcola i target
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-title">
            <Scale /> Peso
          </div>
          {entries.length < 2 ? (
            <EmptyState
              icon={Scale}
              title={
                entries.length
                  ? "Una pesata, ancora nessuna linea"
                  : "Nessuna pesata"
              }
              text="Segna il peso ogni tanto, alla stessa ora: dalla seconda pesata qui compare l'andamento."
            />
          ) : (
            <WeightChart entries={entries} riferimento={riferimento} />
          )}
        </div>
      </div>

      <aside className="page-aside">
        <form className="card settings-section" onSubmit={salva}>
          <div className="card-title">Peso di oggi</div>
          <div className="weight-input">
            <input
              type="text"
              inputMode="decimal"
              placeholder={ultimo ? formatNumber(ultimo.weight_kg, 1) : "70,0"}
              value={kg}
              aria-label="Peso di oggi in chili"
              onChange={(e) => setKg(e.target.value)}
            />
            <span>kg</span>
            <button className="btn btn-primary btn-sm" disabled={busy || !kg}>
              {busy ? <span className="spinner-inline" /> : <Save size={14} />}
              Segna
            </button>
          </div>
          <p className="field-hint">
            Ripesarti lo stesso giorno corregge il numero, non ne aggiunge un
            altro.
          </p>
        </form>

        {entries.length > 0 && (
          <div className="card settings-section">
            <div className="card-title">Pesate</div>
            <ul className="weight-list">
              {[...entries].reverse().map((e) => (
                <li key={e.day}>
                  <span className="weight-day">{giorno(e.day)}</span>
                  <span className="weight-kg">
                    {formatNumber(e.weight_kg, 1)} kg
                  </span>
                  <button
                    className="btn btn-ghost btn-icon btn-sm"
                    aria-label={`Togli la pesata del ${giorno(e.day)}`}
                    onClick={() => togli(e.day)}
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}

function giorno(iso) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

// Una linea sola, quindi niente legenda: il titolo della card dice cos'è. L'asse x è il
// tempo vero (le pesate non sono equidistanti, e disegnarle a passo fisso mentirebbe
// sulla velocità), l'asse y parte poco sotto il minimo e non da zero: su 70 kg una
// variazione di 2 è tutto quello che c'è da vedere. Il peso dei target, se c'è, è una
// riga tratteggiata di riferimento.
function WeightChart({ entries, riferimento }) {
  const [hover, setHover] = useState(null);
  const W = 640;
  const H = 240;
  const PAD = { top: 16, right: 16, bottom: 28, left: 44 };

  const punti = useMemo(() => {
    const tempi = entries.map((e) => new Date(`${e.day}T12:00:00`).getTime());
    const valori = entries
      .map((e) => e.weight_kg)
      .concat(riferimento ? [riferimento] : []);
    const t0 = Math.min(...tempi);
    const t1 = Math.max(...tempi);
    const lo = Math.floor(Math.min(...valori) - 1);
    const hi = Math.ceil(Math.max(...valori) + 1);
    const x = (t) =>
      PAD.left + ((t - t0) / (t1 - t0 || 1)) * (W - PAD.left - PAD.right);
    const y = (v) =>
      PAD.top + ((hi - v) / (hi - lo || 1)) * (H - PAD.top - PAD.bottom);
    return {
      lista: entries.map((e, i) => ({
        ...e,
        x: x(tempi[i]),
        y: y(e.weight_kg),
      })),
      y,
      lo,
      hi,
    };
  }, [entries, riferimento]);

  const { lista, y, lo, hi } = punti;
  const passo = Math.max(1, Math.ceil((hi - lo) / 4));
  const tacche = [];
  for (let v = lo; v <= hi; v += passo) tacche.push(v);
  const percorso = lista
    .map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`)
    .join(" ");
  const attivo = hover != null ? lista[hover] : null;

  return (
    <div className="weight-chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Andamento del peso: da ${formatNumber(lista[0].weight_kg, 1)} a ${formatNumber(
          lista[lista.length - 1].weight_kg,
          1,
        )} kg`}
        onMouseLeave={() => setHover(null)}
      >
        {tacche.map((v) => (
          <g key={v}>
            <line
              className="wc-grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(v)}
              y2={y(v)}
            />
            <text
              className="wc-axis"
              x={PAD.left - 8}
              y={y(v) + 4}
              textAnchor="end"
            >
              {v}
            </text>
          </g>
        ))}
        {riferimento && (
          <g>
            <line
              className="wc-ref"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(riferimento)}
              y2={y(riferimento)}
            />
            <text
              className="wc-axis"
              x={W - PAD.right}
              y={y(riferimento) - 6}
              textAnchor="end"
            >
              peso dei target
            </text>
          </g>
        )}
        <text className="wc-axis" x={PAD.left} y={H - 8}>
          {giorno(lista[0].day)}
        </text>
        <text className="wc-axis" x={W - PAD.right} y={H - 8} textAnchor="end">
          {giorno(lista[lista.length - 1].day)}
        </text>
        {attivo && (
          <line
            className="wc-cross"
            x1={attivo.x}
            x2={attivo.x}
            y1={PAD.top}
            y2={H - PAD.bottom}
          />
        )}
        <path className="wc-line" d={percorso} />
        {lista.map((p, i) => (
          <g
            key={p.day}
            onMouseEnter={() => setHover(i)}
            onFocus={() => setHover(i)}
          >
            {/* Il bersaglio è più grande del punto: 8px si mirano male col dito. */}
            <circle cx={p.x} cy={p.y} r={14} fill="transparent" />
            <circle
              className={`wc-dot ${hover === i ? "on" : ""}`}
              cx={p.x}
              cy={p.y}
              r={4}
            />
          </g>
        ))}
      </svg>
      {attivo && (
        <div
          className="wc-tip"
          style={{
            left: `${(attivo.x / W) * 100}%`,
            top: `${(attivo.y / H) * 100}%`,
          }}
        >
          <strong>{formatNumber(attivo.weight_kg, 1)} kg</strong>
          <span>{giorno(attivo.day)}</span>
        </div>
      )}
    </div>
  );
}
