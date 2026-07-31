import { useState } from 'react';
import { Plus, X } from 'lucide-react';

// Un gruppo di normalizzazione: il nome normalizzato in testa e, dentro, tutti i
// termini che ci finiscono sopra.
//
// I termini di serie e quelli aggiunti a mano stanno nella **stessa** scatola, perché
// fanno la stessa identica cosa — cambia solo che i primi non si tolgono da qui. La
// differenza si vede senza doverla leggere: quelli aggiunti hanno la crocetta, gli
// altri no. Tenerli in due elenchi separati avrebbe costretto a guardare in due punti
// per sapere se "tortiglioni" c'è già.
export default function RuleBox({
  target,
  note,
  fixed = [],
  custom = [],
  placeholder = 'Aggiungi un termine',
  busy = false,
  onAdd,
  onRemove,
  onRemoveGroup,
}) {
  const [draft, setDraft] = useState('');

  const add = async () => {
    const term = draft.trim();
    if (!term) return;
    const ok = await onAdd(term);
    // Il campo si svuota solo se il termine è stato accettato: se la regola è stata
    // rifiutata (o annullata all'anteprima) riscriverla da capo sarebbe una punizione.
    if (ok) setDraft('');
  };

  return (
    <div className="rule-box">
      <div className="rule-box-head">
        <div className="rule-target" title="Il nome con cui finisce in lista della spesa">
          {target}
        </div>
        {onRemoveGroup && custom.length > 0 && fixed.length === 0 && (
          <button className="btn btn-ghost btn-sm" onClick={onRemoveGroup} disabled={busy}>
            Svuota
          </button>
        )}
      </div>

      {note && <p className="field-hint">{note}</p>}

      <div className="tag-list">
        {fixed.map((term) => (
          <span key={`f-${term}`} className="tag fixed" title="Regola di serie">
            {term}
          </span>
        ))}
        {custom.map((rule) => (
          <span key={rule.id} className="tag custom">
            {rule.term}
            <button
              title="Togli la regola (quello che ha già fuso resta fuso)"
              disabled={busy}
              onClick={() => onRemove(rule)}
            >
              <X size={13} />
            </button>
          </span>
        ))}
        {fixed.length === 0 && custom.length === 0 && (
          <span className="field-hint">Nessun termine.</span>
        )}
      </div>

      <div className="inline-form" style={{ marginTop: 12 }}>
        <input
          type="text"
          value={draft}
          placeholder={placeholder}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
        />
        <button
          className="btn btn-secondary"
          onClick={add}
          disabled={busy || draft.trim().length < 2}
        >
          <Plus size={15} /> Aggiungi
        </button>
      </div>
    </div>
  );
}
