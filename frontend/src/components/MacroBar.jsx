import { formatNumber } from '../api';

// Barra proporzionale P/C/G. Le proporzioni sono per grammi, non per calorie: è la
// lettura immediata ("quante proteine ha questo piatto") che serve guardando la card.
export default function MacroBar({ protein, carbs, fat, legend = false }) {
  const total = (protein || 0) + (carbs || 0) + (fat || 0);
  if (!total) return null;

  const pct = (v) => `${((v / total) * 100).toFixed(1)}%`;

  return (
    <div>
      <div className="macro-bar">
        <span className="macro-p" style={{ width: pct(protein) }} />
        <span className="macro-c" style={{ width: pct(carbs) }} />
        <span className="macro-f" style={{ width: pct(fat) }} />
      </div>
      {legend && (
        <div className="macro-legend">
          <span>
            <i className="macro-p" style={{ background: 'var(--macro-p)' }} />
            Proteine {formatNumber(protein, 1)} g
          </span>
          <span>
            <i style={{ background: 'var(--macro-c)' }} />
            Carboidrati {formatNumber(carbs, 1)} g
          </span>
          <span>
            <i style={{ background: 'var(--macro-f)' }} />
            Grassi {formatNumber(fat, 1)} g
          </span>
        </div>
      )}
    </div>
  );
}
