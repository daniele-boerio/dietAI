import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, Globe } from 'lucide-react';
import { api } from '../api';

/**
 * Le cucine da cui attingere le ricette: si cercano e si spuntano.
 *
 * Il catalogo arriva dal server (`/config/cuisines`) e non da una copia qui: è lo
 * stesso elenco su cui il backend valida e che finisce nel prompt, e due liste che
 * si allontanano fra loro sono un 400 in faccia all'utente per una voce aggiunta da
 * una parte sola.
 *
 * Le scelte si vedono **due volte** di proposito — in pastiglia qui sopra e accese
 * nell'elenco — perché l'elenco scorre: con sessanta voci in sei gruppi, quello che
 * hai spuntato tre righe fa è già fuori campo, e un selettore che non sa dire cosa
 * ha dentro è un selettore da riaprire ogni volta.
 */

// Accenti via: si scrive "peru" nel campo di ricerca, non "perù". Vale anche al
// contrario, perché gli alias del catalogo qualche accento ce l'hanno.
const piatto = (s) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim();

export default function CuisinePicker({ value, onChange, disabled }) {
  const [groups, setGroups] = useState(null);
  const [errore, setErrore] = useState(false);
  const [q, setQ] = useState('');
  const campo = useRef(null);

  useEffect(() => {
    api
      .getCuisines()
      .then((d) => setGroups(d.groups))
      .catch(() => setErrore(true));
  }, []);

  const scelte = useMemo(() => new Set(value || []), [value]);

  // Le pastiglie in cima seguono l'ordine del catalogo e non quello dei clic: è lo
  // stesso ordine in cui le legge il modello, e una lista che si rimescola a ogni
  // aggiunta costringe a rileggerla tutta per vedere cos'è cambiato.
  const scelteInOrdine = useMemo(() => {
    if (!groups) return [];
    return groups
      .flatMap((g) => g.cuisines)
      .filter((c) => scelte.has(c.key));
  }, [groups, scelte]);

  const filtrati = useMemo(() => {
    if (!groups) return [];
    const cerca = piatto(q);
    if (!cerca) return groups;
    return groups
      .map((g) => ({
        ...g,
        // Si cerca per paese ("Giappone"), per piatto ("sushi") o per area
        // ("Asia"): l'aggettivo con cui la voce è scritta è l'unica delle quattro
        // cose che non viene in mente per prima.
        cuisines: g.cuisines.filter(
          (c) =>
            piatto(c.label).includes(cerca) ||
            piatto(g.label).includes(cerca) ||
            c.aliases.some((a) => piatto(a).includes(cerca))
        ),
      }))
      .filter((g) => g.cuisines.length > 0);
  }, [groups, q]);

  if (errore)
    return (
      <p className="field-hint">
        Non sono riuscito a caricare l'elenco delle cucine. Ricarica la pagina.
      </p>
    );
  if (!groups) return <div className="spinner" />;

  const toggle = (key) => {
    if (disabled) return;
    const next = scelte.has(key)
      ? (value || []).filter((k) => k !== key)
      : [...(value || []), key];
    onChange(next);
  };

  return (
    <div className="cuisine-picker">
      <div className="cuisine-chosen">
        {scelteInOrdine.map((c) => (
          <span key={c.key} className="tag">
            {c.label}
            <button
              type="button"
              disabled={disabled}
              aria-label={`Togli ${c.label}`}
              onClick={() => toggle(c.key)}
            >
              <X size={13} />
            </button>
          </span>
        ))}
        {scelteInOrdine.length === 0 && (
          <span className="cuisine-none">
            <Globe size={14} />
            Nessuna scelta: il modello propone quello che vuole
          </span>
        )}
      </div>

      <div className="search-field cuisine-search">
        <Search />
        <input
          ref={campo}
          className="search-field-input"
          type="text"
          value={q}
          disabled={disabled}
          placeholder="Cerca un paese, una cucina, un piatto…"
          onChange={(e) => setQ(e.target.value)}
        />
        {q && (
          <button
            type="button"
            className="cuisine-clear"
            aria-label="Cancella la ricerca"
            onClick={() => {
              setQ('');
              campo.current?.focus();
            }}
          >
            <X size={15} />
          </button>
        )}
      </div>

      <div className="cuisine-catalog">
        {filtrati.map((g) => (
          <div key={g.label} className="cuisine-group">
            <div className="cuisine-group-label">{g.label}</div>
            <div className="cuisine-options">
              {g.cuisines.map((c) => (
                <button
                  key={c.key}
                  type="button"
                  className={`chip ${scelte.has(c.key) ? 'active' : ''}`}
                  disabled={disabled}
                  aria-pressed={scelte.has(c.key)}
                  onClick={() => toggle(c.key)}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        ))}
        {filtrati.length === 0 && (
          <p className="field-hint">
            Nessuna cucina per «{q}». Se ti serve un vincolo che qui non c'è, scrivilo
            nelle regole libere qui sotto: quelle le legge il modello così come sono.
          </p>
        )}
      </div>
    </div>
  );
}
