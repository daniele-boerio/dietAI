import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import ConfirmDialog from './ConfirmDialog';
import LoadError from './LoadError';
import RuleBox from './RuleBox';

// Perché i nomi si accorpano, e come cambiarlo senza toccare il codice.
//
// L'app riscrive i nomi degli ingredienti prima di salvarli, altrimenti la lista della
// spesa avrebbe tre righe di zucchine e la dispensa non ne coprirebbe nessuna. Le
// regole erano scritte solo nel codice: bastava che il modello inventasse un formato di
// pasta nuovo per ritrovarsi una riga in più, e per aggiungerlo serviva un deploy.
//
// Prima di salvare si passa sempre dall'anteprima: un accorpamento sbagliato **non si
// annulla** togliendo la regola, perché le righe fuse restano fuse. Vedere "riso →
// pasta" prima di premere è l'unica difesa che ha senso.
export default function NormalizationSettings() {
  const { addToast } = useApp();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(null);
  const [newTarget, setNewTarget] = useState('');

  const load = () => {
    setFailed(null);
    api
      .getNormalization()
      .then(setData)
      .catch((e) => setFailed(e.message));
  };

  useEffect(load, []);

  const salva = async (rule) => {
    setBusy(true);
    try {
      const res = await api.addNormalizationRule(rule);
      const fusi = res.merged.reduce((n, m) => n + m.from.length, 0);
      addToast(
        fusi
          ? `Regola salvata ✓ — ${fusi} ${fusi === 1 ? 'riga fusa' : 'righe fuse'}`
          : 'Regola salvata ✓'
      );
      load();
      return true;
    } catch (e) {
      addToast(e.message, 'error');
      return false;
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  // Ogni aggiunta passa di qui: si chiede al server cosa cambierebbe, e si conferma
  // solo se cambia davvero qualcosa. Se non tocca nessuna riga si salva e basta —
  // far confermare il nulla insegna a premere "sì" senza leggere.
  const chiedi = async (rule) => {
    setBusy(true);
    try {
      const preview = await api.previewNormalizationRule(rule);
      if (preview.changes.length === 0) return await salva(rule);
      setPending({ rule, preview });
      return true;
    } catch (e) {
      addToast(e.message, 'error');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const rimuovi = async (rule, messaggio) => {
    setBusy(true);
    try {
      await api.deleteNormalizationRule(rule.id ?? rule.rule_id);
      addToast(
        messaggio || `«${rule.term}» non verrà più accorpato da qui in avanti`
      );
      load();
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  // Spegnere un termine di serie non lo cancella: resta scritto nel codice e questa è
  // una riga che lo sospende. Per questo si riaccende, e per questo passa dalla stessa
  // anteprima delle aggiunte — spegnere "sedani" non rimette in due righe la pasta che
  // ci si era già fusa dentro, e conviene saperlo prima.
  const spegni = (t) => chiedi({ kind: 'off', term: t.term });

  const riaccendi = (t) =>
    rimuovi({ id: t.rule_id, term: t.label }, `«${t.label}» torna a valere`);

  if (failed) return <LoadError message={failed} onRetry={load} />;
  if (!data) return <div className="spinner" />;

  const creaGruppo = () => {
    const target = newTarget.trim().toLowerCase();
    if (!target) return;
    if (data.groups.some((g) => g.target === target)) {
      addToast(`Il gruppo «${target}» c'è già: aggiungi i termini lì.`, 'error');
      return;
    }
    setData((prev) => ({
      ...prev,
      groups: [...prev.groups, { target, terms: [], note: null, custom: [] }],
    }));
    setNewTarget('');
  };

  return (
    <>
      <div className="card settings-section">
        <div className="card-title">Come si accorpano i nomi</div>
        <p className="field-hint">
          Prima di finire in lista della spesa ogni nome viene riscritto: «Penne rigate
          bio» diventa <strong>pasta rigate</strong>. Serve perché la dispensa e la spesa
          si parlino — tre righe di zucchine scritte in tre modi non si sottraggono fra
          loro. Qui sotto ci sono tutte le regole: quelle di serie non si tolgono (ci si
          appoggiano il catalogo dei prezzi e i test), le tue sì.
        </p>
        <p className="field-hint">
          <strong>Un accorpamento non si annulla:</strong> togliendo la regola le righe
          già fuse restano fuse e le quantità sommate in dispensa non si dividono. Per
          questo prima di salvare ti mostro cosa cambierebbe.
        </p>
        <p className="field-hint">
          I termini di serie si spengono con la crocetta e restano barrati: sono scritti
          nel codice, quindi quella è una sospensione e si annulla con la freccia
          accanto. Serve per i casi ambigui — «sedani» è un formato di pasta, ma è anche
          il plurale del sedano.
        </p>
      </div>

      <h3 className="settings-heading">Accorpamenti</h3>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        A sinistra il nome normalizzato, dentro i termini che ci finiscono sopra. Il
        confronto è su parola intera: «calamarata» accorpata su «pasta» cambia anche
        «calamarata integrale», ma non tocca «calamarataccia».
      </p>

      {data.groups.map((group) => (
        <RuleBox
          key={group.target}
          target={group.target}
          note={group.note}
          fixed={group.terms}
          custom={group.custom}
          busy={busy}
          placeholder={`Termine da accorpare su «${group.target}»`}
          onAdd={(term) =>
            chiedi({ kind: 'alias', term, replacement: group.target })
          }
          onRemove={rimuovi}
          onDisable={spegni}
          onRestore={riaccendi}
        />
      ))}

      <div className="card settings-section">
        <div className="card-title">
          <Plus /> Nuovo accorpamento
        </div>
        <p className="field-hint" style={{ marginBottom: 12 }}>
          Il nome normalizzato, cioè quello che vuoi leggere in lista della spesa. I
          termini si aggiungono subito dopo, nella scatola che compare.
        </p>
        <div className="inline-form">
          <input
            type="text"
            placeholder="es. seitan"
            value={newTarget}
            onChange={(e) => setNewTarget(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && creaGruppo()}
          />
          <button
            className="btn btn-secondary"
            onClick={creaGruppo}
            disabled={newTarget.trim().length < 2}
          >
            Crea il gruppo
          </button>
        </div>
      </div>

      <h3 className="settings-heading">Parole ignorate</h3>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        Dicono <em>com'è messo</em> l'alimento, non <em>cos'è</em>: si tolgono dal nome e
        basta. «Pesce spada surgelato» e «pesce spada fresco» sono lo stesso pesce preso
        a due banchi diversi.
      </p>

      <RuleBox
        target="parole tolte dal nome"
        note="Le tue, più quelle di serie qui sotto."
        custom={data.noise.custom}
        busy={busy}
        placeholder="es. a filetti"
        onAdd={(term) => chiedi({ kind: 'noise', term })}
        onRemove={rimuovi}
      />

      {data.noise.builtin.map((gruppo) => (
        <RuleBox
          key={gruppo.label}
          target={gruppo.label}
          fixed={gruppo.terms}
          busy={busy}
          onDisable={spegni}
          onRestore={riaccendi}
        />
      ))}

      <p className="field-hint">
        Sono schemi, non parole: <code>fresc[ao]</code> copre fresco e fresca,{' '}
        <code>di …</code> una parola qualsiasi. Spegnerne uno non rimette in due le
        righe che si erano già unite grazie a lui: vale da qui in avanti.
      </p>

      <h3 className="settings-heading">Qualificatori legati a un alimento</h3>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        Si tolgono solo dopo quel nome: «nere» da solo non vuol dire niente, dopo
        «olive» sì.
      </p>

      {data.scoped.map((s) => (
        <RuleBox
          key={s.target}
          target={s.target}
          note={s.note}
          fixed={s.terms}
          busy={busy}
          onDisable={spegni}
          onRestore={riaccendi}
        />
      ))}

      <h3 className="settings-heading">Quello che succede da sé</h3>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        Due cose non hanno termini da elencare, perché non sono liste di parole.
        <br />
        <strong>Apostrofi e spazi</strong> hanno un modo solo di essere scritti: «tonno
        all'olio d'oliva», «tonno all’olio d’oliva» e «tonno all'olio di oliva» sono la
        stessa riga. Senza, in dispensa ne comparirebbero due identiche a vedersi.
        <br />
        <strong>Singolare e plurale</strong> finiscono sulla forma del catalogo, che è
        quella a cui sono attaccati reparto e prezzo: «peperone» diventa «peperoni»,
        «uovo» diventa «uova».
      </p>

      <div className="card settings-section">
        <div className="card-title">Parole che restano, di proposito</div>
        <p className="field-hint" style={{ marginBottom: 12 }}>
          Cambiano i numeri della dieta, quindi cambiano l'alimento: uno yogurt magro e
          uno intero non sono la stessa riga della spesa nemmeno volendo.
        </p>
        <div className="tag-list" style={{ marginTop: 0 }}>
          {data.kept.map((t) => (
            <span key={t} className="tag fixed">
              {t}
            </span>
          ))}
        </div>
      </div>

      {pending && (
        <ConfirmDialog
          danger={pending.preview.changes.some((c) => c.merges)}
          busy={busy}
          title="Questo cambia l'anagrafica"
          text={
            `Con questa regola ${pending.preview.changes.length} ` +
            `${pending.preview.changes.length === 1 ? 'riga cambia' : 'righe cambiano'} nome:\n\n` +
            pending.preview.changes
              .map((c) => `· ${c.from} → ${c.to}${c.merges ? ' (si fonde con la riga esistente)' : ''}`)
              .join('\n') +
            '\n\nLe fusioni non si annullano.'
          }
          confirmLabel="Salva la regola"
          onConfirm={() => salva(pending.rule)}
          onCancel={() => setPending(null)}
        />
      )}
    </>
  );
}
