import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

// Campo con suggerimenti dall'anagrafica. Suggerire (invece di lasciare testo libero)
// evita di creare "pomodori" e "pomodoro" come due ingredienti diversi, che poi in
// lista della spesa diventano due righe.
export default function IngredientInput({ value, onChange, placeholder = 'Ingrediente...' }) {
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const campo = useRef(null);
  // Il nome appena scelto dal menu: cambia `value`, e senza questo segno la ricerca
  // ripartiva e riapriva il menu sopra la riga, anche col campo già lasciato.
  const scelto = useRef(null);

  useEffect(() => {
    clearTimeout(timer.current);
    if (value.trim().length < 2 || value === scelto.current) {
      setSuggestions([]);
      return undefined;
    }
    let superata = false;
    // Debounce: si scrive più velocemente di quanto il server risponda.
    timer.current = setTimeout(() => {
      api
        .searchIngredients(value)
        .then((rows) => {
          if (superata) return;
          setSuggestions(rows);
          // Il menu si apre solo per chi sta scrivendo qui.
          setOpen(rows.length > 0 && document.activeElement === campo.current);
        })
        .catch(() => !superata && setSuggestions([]));
    }, 250);
    return () => {
      superata = true;
      clearTimeout(timer.current);
    };
  }, [value]);

  return (
    // La larghezza la decide chi lo usa: qui dentro c'era un `minWidth: 160` che in
    // una colonna stretta — la riga della dispensa in modifica — impediva al campo
    // di stringersi, e la riga andava a capo storta invece di comprimersi.
    <div className="ingredient-input">
      <input
        ref={campo}
        type="text"
        value={value}
        placeholder={placeholder}
        aria-label={placeholder.replace(/[.…]+$/, '')}
        aria-autocomplete="list"
        aria-expanded={open}
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
                scelto.current = s.name;
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
