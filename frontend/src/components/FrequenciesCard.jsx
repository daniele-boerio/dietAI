import { useEffect, useState } from 'react';
import { CalendarRange, Plus, Save, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';

// Le frequenze settimanali della dieta: «pesce 2-3 volte, carne rossa al massimo una».
// Sono un dato della dieta e non una regola scritta a parole perché le conta Python:
// prima di chiamare il modello si decide in quali pranzi e cene va il pesce, e dopo la
// settimana dice quante volte c'è davvero. Le regole libere restano per il resto.
//
// Il massimo vuoto vuol dire «nessun massimo», il minimo a zero «nessun minimo»: una
// riga coi due vuoti non dice niente e il server la scarta.
export default function FrequenciesCard({ diet, onSaved }) {
  const { addToast } = useApp();
  const [options, setOptions] = useState(null);
  const [rows, setRows] = useState(diet.frequencies || []);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRows(diet.frequencies || []);
  }, [diet.id, diet.frequencies]);

  useEffect(() => {
    api.getFrequencyOptions().then(setOptions).catch(() => setOptions(null));
  }, []);

  const label = (food) => options?.foods.find((f) => f.key === food)?.label || food;
  const liberi = (options?.foods || []).filter((f) => !rows.some((r) => r.food === f.key));

  const cambia = (food, campo, valore) =>
    setRows((prev) =>
      prev.map((r) =>
        r.food === food
          ? { ...r, [campo]: valore === '' ? (campo === 'max' ? null : 0) : Number(valore) }
          : r
      )
    );

  const salva = async () => {
    setBusy(true);
    try {
      const updated = await api.updateDietFrequencies(diet.id, rows);
      onSaved(updated);
      addToast('Frequenze salvate ✓ — valgono dalla prossima generazione');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const dirty = JSON.stringify(rows) !== JSON.stringify(diet.frequencies || []);

  return (
    <div className="card settings-section">
      <div className="card-title">
        <CalendarRange /> Quante volte a settimana
      </div>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        Le frequenze per gruppo di alimenti, come le scrive il nutrizionista. Le
        distribuisco io sui pranzi e sulle cene prima di generare, e nella settimana
        vedi quante volte c'è davvero ogni gruppo.
      </p>

      {rows.length > 0 && (
        <div className="freq-list">
          <div className="freq-row freq-head">
            <span />
            <span>min</span>
            <span>max</span>
            <span />
          </div>
          {rows.map((r) => (
            <div key={r.food} className="freq-row">
              <span className="freq-name">{label(r.food)}</span>
              <input
                type="number"
                min="0"
                max="21"
                value={r.min ?? 0}
                aria-label={`${label(r.food)}: minimo a settimana`}
                onChange={(e) => cambia(r.food, 'min', e.target.value)}
              />
              <input
                type="number"
                min="0"
                max="21"
                placeholder="—"
                value={r.max ?? ''}
                aria-label={`${label(r.food)}: massimo a settimana`}
                onChange={(e) => cambia(r.food, 'max', e.target.value)}
              />
              <button
                className="btn btn-ghost btn-icon btn-sm"
                aria-label={`Togli ${label(r.food)}`}
                onClick={() => setRows((prev) => prev.filter((x) => x.food !== r.food))}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="freq-actions">
        {liberi.length > 0 && (
          <select
            value=""
            aria-label="Aggiungi un gruppo"
            onChange={(e) =>
              e.target.value &&
              setRows((prev) => [...prev, { food: e.target.value, min: 1, max: null }])
            }
          >
            <option value="">+ Aggiungi un gruppo…</option>
            {liberi.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
        )}
        {options && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setRows(options.recommended)}
            title="Linee guida per una sana alimentazione (CREA, 2018): indicative, per un adulto sano"
          >
            <Plus size={14} /> Usa le consigliate
          </button>
        )}
        <button className="btn btn-primary btn-sm" onClick={salva} disabled={busy || !dirty}>
          {busy ? <span className="spinner-inline" /> : <Save size={14} />}
          Salva
        </button>
      </div>
    </div>
  );
}
