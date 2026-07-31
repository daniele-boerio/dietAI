import { useState } from 'react';
import { Plus, RotateCcw, X } from 'lucide-react';

// Un gruppo di normalizzazione: il nome normalizzato in testa e, dentro, tutti i
// termini che ci finiscono sopra.
//
// I termini di serie e quelli aggiunti a mano stanno nella **stessa** scatola, perché
// fanno la stessa identica cosa: tenerli in due elenchi avrebbe costretto a guardare in
// due punti per sapere se "tortiglioni" c'è già. Si tolgono tutti, ma in due modi
// diversi — quelli tuoi spariscono, quelli di serie restano barrati con accanto il
// modo di riaccenderli, perché sono scritti nel codice e la loro è una sospensione,
// non una cancellazione.
export default function RuleBox({
  target,
  note,
  fixed = [],
  custom = [],
  placeholder = 'Aggiungi un termine',
  busy = false,
  onAdd,
  onRemove,
  onDisable,
  onRestore,
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
        {fixed.map((t) => (
          <span
            key={`f-${t.term}`}
            className={`tag fixed ${t.disabled ? 'off' : ''}`}
            title={
              t.disabled
                ? 'Spento da te: non vale più. Premi per riaccenderlo.'
                : `Regola di serie (${t.term})`
            }
          >
            {t.label}
            {t.disabled ? (
              <button
                title="Riaccendi questo termine"
                disabled={busy}
                onClick={() => onRestore(t)}
              >
                <RotateCcw size={12} />
              </button>
            ) : (
              onDisable && (
                <button
                  title="Spegni questo termine di serie"
                  disabled={busy}
                  onClick={() => onDisable(t)}
                >
                  <X size={13} />
                </button>
              )
            )}
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

      {/* Senza `onAdd` la scatola è di sola consultazione (le famiglie di parole
          ignorate, i qualificatori): niente campo, o si aprirebbe la porta su una
          stanza che non c'è. */}
      {onAdd && (
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
      )}
    </div>
  );
}
