import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, Globe } from 'lucide-react';
import { api } from '../api';
import { QUOTA_MINIMA, aggiungi, normalizza, riparti, tetto, togli } from '../lib/quote';

// Lo stesso tetto del server, dove e' anche validato.
const MAX_CUCINE = 12;

/**
 * Le cucine da cui attingere le ricette: si cercano e si spuntano.
 *
 * Il catalogo arriva dal server (`/config/cuisines`) e non da una copia qui: è lo
 * stesso elenco su cui il backend valida e che finisce nel prompt, e due liste che
 * si allontanano fra loro sono un 400 in faccia all'utente per una voce aggiunta da
 * una parte sola.
 *
 * Le scelte si vedono **due volte** di proposito — in riga qui sopra e accese
 * nell'elenco — perché l'elenco scorre: con sessanta voci in sei gruppi, quello che
 * hai spuntato tre righe fa è già fuori campo, e un selettore che non sa dire cosa
 * ha dentro è un selettore da riaprire ogni volta.
 *
 * Ogni scelta si porta dietro la sua **quota**, che è quanta parte dei piatti prende.
 * È la domanda del lucchetto nell'editor della dieta senza il lucchetto: il totale
 * non è una scelta, è 100 per definizione, quindi alzare l'italiana al 70% stringe le
 * altre in proporzione invece di allungare la somma. L'aritmetica sta in `lib/quote.js`
 * ed è la stessa di `cuisines.clean()` nel backend: deve esserlo, perché il numero che
 * si legge mentre si trascina è quello che verrà salvato — se il server ne
 * restituisse un altro i cursori salterebbero da soli appena lasciati.
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

  // La preferenza è `{chiave: quota}`, ma dall'archivio può ancora arrivare il
  // semplice elenco della prima versione (`["italiana", "greca"]`), che vale «queste,
  // in parti uguali»: `normalizza` fa diventare le due cose la stessa, come
  // `clean()` di là.
  const quote = useMemo(() => {
    if (Array.isArray(value)) {
      return normalizza(Object.fromEntries(value.map((k) => [k, 1])));
    }
    return value && Object.keys(value).length ? value : {};
  }, [value]);

  // Le righe in cima seguono l'ordine del catalogo e non quello dei clic: è lo
  // stesso ordine in cui le legge il modello, e una lista che si rimescola a ogni
  // aggiunta costringe a rileggerla tutta per vedere cos'è cambiato.
  const scelteInOrdine = useMemo(() => {
    if (!groups) return [];
    return groups.flatMap((g) => g.cuisines).filter((c) => c.key in quote);
  }, [groups, quote]);

  // Le chiavi in ordine di catalogo: è l'ordine in cui vanno ricostruite le quote,
  // perché il server le riordina comunque così e i cursori non devono saltare.
  const inOrdine = (q) =>
    Object.fromEntries(
      scelteInOrdine.filter((c) => c.key in q).map((c) => [c.key, q[c.key]])
    );

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
    onChange(inOrdine(key in quote ? togli(quote, key) : aggiungi(quote, key)));
  };

  const muovi = (key, valore) => {
    if (disabled) return;
    onChange(inOrdine(riparti(quote, key, valore)));
  };

  const una = scelteInOrdine.length === 1;
  // Il tetto è quello del server (`cuisines.MAX_CUCINE`): oltre, le quote diventano
  // così piccole che sorteggiarle su una settimana non vuol dire più niente. Le
  // pastiglie si spengono invece di sparire, o la ricerca risponderebbe «nessun
  // risultato» a una cucina che c'è.
  const pieno = scelteInOrdine.length >= MAX_CUCINE;

  return (
    <div className="cuisine-picker">
      <div className="cuisine-chosen">
        {scelteInOrdine.map((c) => (
          <div key={c.key} className="cuisine-row">
            <span className="cuisine-row-name">{c.label}</span>
            {/* Con una cucina sola il cursore non avrebbe nulla da ripartire: il
                100% è un fatto, non una scelta, e un comando che non si muove è un
                comando rotto. */}
            <input
              type="range"
              min={QUOTA_MINIMA}
              max={una ? 100 : tetto(quote, c.key)}
              value={quote[c.key] ?? 0}
              disabled={disabled || una}
              aria-label={`Quota di ${c.label}`}
              onChange={(e) => muovi(c.key, Number(e.target.value))}
            />
            <span className="cuisine-row-share">{quote[c.key] ?? 0}%</span>
            <button
              type="button"
              className="cuisine-row-x"
              disabled={disabled}
              aria-label={`Togli ${c.label}`}
              onClick={() => toggle(c.key)}
            >
              <X size={14} />
            </button>
          </div>
        ))}
        {scelteInOrdine.length === 0 && (
          <span className="cuisine-none">
            <Globe size={14} />
            Nessuna scelta: il modello propone quello che vuole
          </span>
        )}
      </div>

      {/* La riga che spiega i cursori sta sotto le righe e non sopra: sopra la si
          leggerebbe prima di aver capito di cosa parla. Con una cucina sola non c'è
          niente da ripartire e la frase cambia, invece di restare lì a descrivere
          un comando spento. */}
      {scelteInOrdine.length > 0 && (
        <p className="cuisine-hint">
          {una
            ? 'Una cucina sola: tutti i piatti sono suoi.'
            : 'Alzarne una stringe le altre — la somma è sempre 100%.'}
          {pieno && ' Sei al massimo: per aggiungerne una, togline una.'}
        </p>
      )}

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
                  className={`chip ${c.key in quote ? 'active' : ''}`}
                  disabled={disabled || (!(c.key in quote) && pieno)}
                  aria-pressed={c.key in quote}
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
