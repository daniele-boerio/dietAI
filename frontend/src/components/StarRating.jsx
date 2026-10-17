import { Star } from 'lucide-react';

// Voto 1-5. Non è solo un ricordo: entra nel contesto delle generazioni successive,
// quindi vale la pena metterlo dove si vede (card e dettaglio).
export default function StarRating({ value, onChange, size = 'sm', readOnly = false }) {
  return (
    <div className={`star-rating ${size === 'lg' ? 'lg' : ''}`} role="group" aria-label="Voto">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          className={value >= n ? 'filled' : ''}
          disabled={readOnly}
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            onChange?.(n === value ? n : n);
          }}
          title={`${n} su 5`}
          aria-label={`${n} su 5`}
          aria-pressed={value === n}
        >
          <Star fill={value >= n ? 'currentColor' : 'none'} />
        </button>
      ))}
    </div>
  );
}
