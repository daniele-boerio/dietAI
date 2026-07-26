import { useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
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
    <>
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
          {items.map((i) => (
            <div key={i.id} className="list-row">
              <div className="list-row-main">
                <strong>{i.name}</strong>
                <span>{i.category}</span>
              </div>
              <span style={{ color: 'var(--text-secondary)' }}>{i.label || '—'}</span>
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
          ))}
          {items.length === 0 && (
            <p className="field-hint">
              Dispensa vuota: la lista della spesa comprende tutto quello che serve alle
              ricette.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
