import { useEffect, useState } from 'react';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import IngredientInput from '../components/IngredientInput';

// La dispensa non è una configurazione: è quello che c'è in casa adesso, e cambia ogni
// settimana. Sta accanto alla spesa perché ne è l'altra metà — la lista è ciò che manca,
// questa è ciò che c'è già, e la seconda si sottrae dalla prima.
export default function PantryPage() {
  const { addToast } = useApp();
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unit, setUnit] = useState('g');
  // La riga aperta in modifica, se c'è: una sola per volta.
  const [editing, setEditing] = useState(null);

  const load = () => api.getPantry().then(setItems).catch(() => {});

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    if (!draft.trim()) return;
    try {
      await api.addPantryItem({
        ingredient_name: draft.trim(),
        quantity: quantity ? Number(quantity) : null,
        unit: quantity ? unit : null,
      });
      setDraft('');
      setQuantity('');
      load();
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    // Un modulo e una lista di righe: sono le due cose che dallo spazio in più non
    // guadagnano niente — il nome finirebbe solo più lontano dalla sua quantità.
    <div className="page-narrow">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dispensa</h1>
          <p className="page-subtitle">
            Quello che hai già in casa: viene sottratto dalla lista della spesa e proposto
            per primo alle ricette.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="card-title">Aggiungi quello che hai</div>
        <p className="field-hint" style={{ marginBottom: 14 }}>
          Si riempie da sola quando segni una spesa come fatta: gli articoli spuntati
          finiscono qui. A mano serve per quello che era già in casa prima — il pacco di
          riso aperto, i legumi in barattolo, quello che ti hanno regalato.
        </p>

        <div className="inline-form">
          <IngredientInput value={draft} onChange={setDraft} />
          <input
            type="number"
            placeholder="Quantità"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            style={{ maxWidth: 110 }}
          />
          <select value={unit} onChange={(e) => setUnit(e.target.value)} style={{ maxWidth: 100 }}>
            <option value="g">g</option>
            <option value="ml">ml</option>
            <option value="unità">unità</option>
          </select>
          <button className="btn btn-secondary" onClick={add}>
            Aggiungi
          </button>
        </div>

        <div className="list-rows" style={{ marginTop: 14 }}>
          {items.map((i) =>
            editing === i.id ? (
              <PantryRowEditor
                key={i.id}
                item={i}
                onDone={() => {
                  setEditing(null);
                  load();
                }}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <div key={i.id} className="list-row">
                <div className="list-row-main">
                  <strong>{i.name}</strong>
                  <span>{i.category}</span>
                </div>
                <span style={{ color: 'var(--text-secondary)' }}>{i.label || '—'}</span>
                <button
                  className="icon-button"
                  onClick={() => setEditing(i.id)}
                  title="Modifica nome e quantità"
                >
                  <Pencil size={15} />
                </button>
                <button
                  className="icon-button danger"
                  onClick={async () => {
                    await api.removePantryItem(i.id);
                    load();
                  }}
                  title="Togli dalla dispensa"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            )
          )}
          {items.length === 0 && (
            <p className="field-hint">
              Dispensa vuota: la lista della spesa comprende tutto quello che serve alle
              ricette.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Una riga della dispensa aperta in modifica.
 *
 * Il nome si può cambiare come la quantità perché la dispensa si riempie da sola a
 * spesa fatta, e quello che ci finisce ha il nome che gli ha dato l'AI nella ricetta:
 * "petto di pollo a fette" quando in frigo c'è del pollo. Cambiarlo non è cosmesi —
 * la riga punta a un altro ingrediente dell'anagrafica, ed è da lì che dipende cosa
 * verrà scomputato dalla prossima lista della spesa.
 */
function PantryRowEditor({ item, onDone, onCancel }) {
  const { addToast } = useApp();
  const [name, setName] = useState(item.name);
  const [quantity, setQuantity] = useState(item.quantity ?? '');
  const [unit, setUnit] = useState(item.unit || 'g');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!name.trim()) {
      addToast('Il nome non può restare vuoto', 'error');
      return;
    }
    setBusy(true);
    try {
      // Quantità vuota è una risposta legittima ("ce l'ho, non so quanto"): in quel
      // caso non si sottrae niente dalla spesa, ma la riga resta a dire che c'è.
      await api.updatePantryItem(item.id, {
        ingredient_name: name.trim(),
        quantity: quantity === '' ? null : Number(quantity),
        unit: quantity === '' ? null : unit,
      });
      onDone();
    } catch (e) {
      addToast(e.message, 'error');
      setBusy(false);
    }
  };

  return (
    <div className="list-row">
      <div className="inline-form" style={{ flex: 1 }}>
        <IngredientInput value={name} onChange={setName} />
        <input
          type="number"
          placeholder="Quantità"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          style={{ maxWidth: 110 }}
        />
        <select value={unit} onChange={(e) => setUnit(e.target.value)} style={{ maxWidth: 100 }}>
          <option value="g">g</option>
          <option value="ml">ml</option>
          <option value="unità">unità</option>
        </select>
      </div>
      <button className="icon-button" onClick={save} disabled={busy} title="Salva">
        <Check size={16} />
      </button>
      <button className="icon-button" onClick={onCancel} disabled={busy} title="Annulla">
        <X size={16} />
      </button>
    </div>
  );
}
