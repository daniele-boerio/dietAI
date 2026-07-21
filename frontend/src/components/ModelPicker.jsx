import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, Eye, X } from 'lucide-react';
import { formatNumber } from '../api';

// Quante righe disegnare nel menu. Il filtro lavora su tutto il catalogo: questo
// limita solo il DOM, e quando taglia qualcosa lo dice.
const RENDER_LIMIT = 120;

// Selettore di modello con ricerca. Il catalogo arriva dal provider, quindi comprende
// anche i modelli usciti dopo che questo codice è stato scritto: niente slug da
// digitare a memoria e nessun errore di battitura scoperto alla prima generazione.
export default function ModelPicker({ role, models, value, defaultModel, onChange }) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState('');
  const boxRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const close = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const current = value || defaultModel;
  const selected = models.find((m) => m.id === current);

  // Si filtra sul catalogo completo e si disegna solo la prima parte: qualche
  // centinaio di righe nel DOM rallenterebbe l'apertura del menu, ma il filtro deve
  // vedere tutto, altrimenti un modello in fondo all'alfabeto è introvabile.
  const { visible, hidden } = useMemo(() => {
    const t = term.trim().toLowerCase();
    const list = t
      ? models.filter((m) => m.id.toLowerCase().includes(t) || m.name.toLowerCase().includes(t))
      : models;
    return { visible: list.slice(0, RENDER_LIMIT), hidden: Math.max(0, list.length - RENDER_LIMIT) };
  }, [models, term]);

  const price = (m) =>
    m.completion_price == null
      ? null
      : `$${formatNumber(m.prompt_price, 2)} / $${formatNumber(m.completion_price, 2)} per Mtok`;

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <button
        className="btn btn-secondary btn-block"
        style={{ justifyContent: 'space-between' }}
        onClick={() => setOpen((v) => !v)}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selected ? selected.name : current}
          {!value && <span style={{ color: 'var(--text-muted)' }}> · predefinito</span>}
        </span>
        <ChevronDown size={15} />
      </button>

      {selected && (
        <div className="field-hint" style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span>{selected.id}</span>
          {price(selected) && <span>{price(selected)}</span>}
          {selected.supports_images && (
            <span style={{ color: 'var(--accent)' }}>
              <Eye size={11} style={{ verticalAlign: -1 }} /> legge le immagini
            </span>
          )}
        </div>
      )}

      {open && (
        <div
          className="card"
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            marginTop: 6,
            padding: 8,
            zIndex: 30,
            maxHeight: 340,
            overflowY: 'auto',
          }}
        >
          <input
            type="text"
            autoFocus
            placeholder="Cerca (glm, claude, deepseek, gemini...)"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            style={{ marginBottom: 8 }}
          />

          {value && (
            <button
              className="btn btn-ghost btn-block btn-sm"
              style={{ justifyContent: 'flex-start' }}
              onClick={() => {
                onChange(role, null);
                setOpen(false);
              }}
            >
              <X size={13} /> Torna al modello predefinito
            </button>
          )}

          {visible.map((m) => (
            <button
              key={m.id}
              className="btn btn-ghost btn-block btn-sm"
              style={{ justifyContent: 'flex-start', textAlign: 'left' }}
              onClick={() => {
                onChange(role, m.id);
                setOpen(false);
              }}
            >
              {m.id === current && <Check size={13} color="var(--accent)" />}
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {m.name}
                {price(m) && (
                  <small style={{ color: 'var(--text-muted)', marginLeft: 6 }}>{price(m)}</small>
                )}
              </span>
            </button>
          ))}

          {hidden > 0 && (
            <p className="field-hint" style={{ padding: '6px 10px' }}>
              Altri {hidden} modelli corrispondono: scrivi qualcosa per restringere.
            </p>
          )}

          {visible.length === 0 && (
            <p className="field-hint">Nessun modello trovato con questo nome.</p>
          )}
        </div>
      )}
    </div>
  );
}
