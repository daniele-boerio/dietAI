import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

// Campo con suggerimenti dall'anagrafica. Suggerire (invece di lasciare testo libero)
// evita di creare "pomodori" e "pomodoro" come due ingredienti diversi, che poi in
// lista della spesa diventano due righe.
export default function IngredientInput({ value, onChange, placeholder = 'Ingrediente...' }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    if (value.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    // Debounce: si scrive più velocemente di quanto il server risponda.
    timer.current = setTimeout(() => {
      api
        .searchIngredients(value)
        .then((rows) => {
          setSuggestions(rows);
          setOpen(rows.length > 0);
        })
        .catch(() => setSuggestions([]));
    }, 250);
    return () => clearTimeout(timer.current);
  }, [value]);

  return (
    <div style={{ position: 'relative', flex: 1, minWidth: 160 }}>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setOpen(suggestions.length > 0)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (
        <div
          className="card"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 4,
            padding: 4,
            zIndex: 20,
            maxHeight: 220,
            overflowY: 'auto',
          }}
        >
          {suggestions.map((s) => (
            <button
              key={s.id}
              className="btn btn-ghost btn-block"
              style={{ justifyContent: 'flex-start' }}
              onMouseDown={() => {
                onChange(s.name);
                setOpen(false);
              }}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
