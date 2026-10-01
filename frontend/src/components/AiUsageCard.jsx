import { useEffect, useState } from 'react';
import { Coins } from 'lucide-react';
import { api } from '../api';

// Quanto è costata l'AI, account per account. Chi mette la chiave paga per tutti, e
// l'interruttore «funzioni AI» qui sotto è il suo freno: questo è il numero per
// decidere quando tirarlo. Il costo è in dollari perché è così che lo conta il
// provider; le chiamate di cui non si sa il costo si dichiarano invece di sparire.
const PERIODI = [7, 30, 90];

export default function AiUsageCard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);

  useEffect(() => {
    api
      .getAiUsage(days)
      .then(setData)
      .catch(() => setData(null));
  }, [days]);

  const dollari = (v) => (v == null ? '—' : `$${v.toFixed(v < 1 ? 3 : 2)}`);
  const token = (n) =>
    n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n);

  return (
    <div className="card settings-section">
      <div className="card-title">
        <Coins /> Quanto costa l'AI
      </div>
      <div className="segmented" style={{ marginBottom: 12 }}>
        {PERIODI.map((d) => (
          <button key={d} className={d === days ? 'on' : ''} onClick={() => setDays(d)}>
            {d} giorni
          </button>
        ))}
      </div>

      {!data ? (
        <div className="spinner" />
      ) : (
        <>
          <ul className="usage-list">
            {data.users.map((u) => (
              <li key={u.user_id}>
                <span className="usage-email">{u.email}</span>
                <span className="usage-num">{u.calls} chiamate</span>
                <span className="usage-num">
                  {token(u.input_tokens)} / {token(u.output_tokens)} token
                </span>
                <strong className="usage-num">{dollari(u.cost_usd)}</strong>
              </li>
            ))}
          </ul>
          <p className="field-hint">
            Totale {dollari(data.total_cost_usd)} negli ultimi {data.days} giorni.
            {data.users.some((u) => u.calls_without_cost) &&
              ' Alcune chiamate non hanno un costo noto (né dichiarato dal provider né nel listino dei modelli) e restano fuori dal totale.'}
          </p>
        </>
      )}
    </div>
  );
}
