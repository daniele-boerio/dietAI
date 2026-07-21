import { useEffect, useState } from 'react';
import { ArrowRight, Check, FileUp, KeyRound, Sprout, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import { useAuth } from '../AuthContext';
import IngredientInput from '../components/IngredientInput';

// Percorso guidato al primo accesso. L'ordine non è estetico: senza API key non si
// può leggere il PDF, senza dieta non si può generare niente, e senza esclusi la
// prima generazione rischia di finire nel cestino.
const STEPS = ['Benvenuto', 'API key', 'Dieta', 'Ingredienti', 'Preferenze'];

export default function OnboardingPage() {
  const { user, refreshUser } = useAuth();
  const { addToast } = useApp();
  const [step, setStep] = useState(user.has_api_key ? (user.has_active_diet ? 3 : 2) : 0);

  return (
    <div className="onboarding">
      <div className="auth-logo" style={{ marginBottom: 22 }}>
        <Sprout size={24} />
        DietAI
      </div>

      <div className="onboarding-steps">
        {STEPS.map((_, i) => (
          <i key={i} className={i <= step ? 'done' : ''} />
        ))}
      </div>

      {step === 0 && <Welcome onNext={() => setStep(1)} />}
      {step === 1 && (
        <ApiKeyStep
          onNext={() => setStep(2)}
          addToast={addToast}
          alreadySet={user.has_api_key}
        />
      )}
      {step === 2 && <DietStep onNext={() => setStep(3)} addToast={addToast} />}
      {step === 3 && <IngredientsStep onNext={() => setStep(4)} addToast={addToast} />}
      {step === 4 && (
        <PreferencesStep
          addToast={addToast}
          onDone={async () => {
            await refreshUser();
          }}
        />
      )}
    </div>
  );
}

function Welcome({ onNext }) {
  return (
    <>
      <h1 className="onboarding-title">Ciao! Mettiamo su la tua cucina.</h1>
      <p className="onboarding-text">
        DietAI parte dalla dieta del tuo nutrizionista e la trasforma in ricette vere,
        una settimana alla volta, con la lista della spesa già pronta. Servono tre
        cose: la tua API key di Claude, il PDF della dieta e due minuti per dirmi cosa
        non vuoi vedere nel piatto.
      </p>
      <button className="btn btn-primary" onClick={onNext}>
        Cominciamo <ArrowRight size={16} />
      </button>
    </>
  );
}

function ApiKeyStep({ onNext, addToast, alreadySet }) {
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState(null);

  useEffect(() => {
    api.getAiConfig().then(setAi).catch(() => {});
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      await api.setApiKey(key.trim());
      addToast('API key salvata ✓');
      onNext();
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h1 className="onboarding-title">La tua API key</h1>
      <p className="onboarding-text">
        Le ricette le scrive un modello linguistico, e le chiamate vengono pagate dalla
        tua chiave. Viene salvata cifrata sul server e non lascia mai il backend.
        {ai?.key_url && (
          <>
            {' '}
            La generi da{' '}
            <a
              href={ai.key_url}
              target="_blank"
              rel="noreferrer"
              style={{ color: 'var(--accent)', fontWeight: 600 }}
            >
              {new URL(ai.key_url).hostname}
            </a>
            .
          </>
        )}
        {ai?.can_list_models && (
          <>
            {' '}
            Con OpenRouter una chiave sola ti dà accesso a tutti i modelli: quale usare
            lo scegli poi da <strong>Impostazioni → Modelli AI</strong>.
          </>
        )}
      </p>

      <div className="field">
        <label className="field-label">
          <KeyRound size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
          API key
        </label>
        <input
          type="password"
          placeholder={`${ai?.key_prefix || 'sk-'}...`}
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </div>

      <div className="onboarding-actions">
        <button
          className="btn btn-primary"
          onClick={save}
          disabled={busy || key.trim().length < 20}
        >
          {busy && <span className="spinner-inline" />}
          Salva e continua
        </button>
        {alreadySet && (
          <button className="btn btn-ghost" onClick={onNext}>
            Ne ho già una salvata
          </button>
        )}
      </div>
    </>
  );
}

function DietStep({ onNext, addToast }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [over, setOver] = useState(false);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const diet = await api.uploadDiet(file);
      setResult(diet);
      addToast(`Letti ${diet.meals.length} pasti dal PDF ✓`);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <>
        <h1 className="onboarding-title">Ecco cosa ho letto</h1>
        <p className="onboarding-text">
          {result.total_daily_calories} kcal al giorno su {result.meals.length} pasti.
          Potrai correggere qualunque valore da <strong>La mia dieta</strong> — i macro
          sbagliati si notano subito, alla prima generazione.
        </p>

        <div className="card">
          <div className="list-rows">
            {result.meals.map((m) => (
              <div key={m.order} className="list-row">
                <div className="list-row-main">
                  <strong>{m.name}</strong>
                  <span>
                    P {m.protein_g}g · C {m.carbs_g}g · G {m.fat_g}g
                    {m.notes ? ` · ${m.notes}` : ''}
                  </span>
                </div>
                <span className="badge badge-accent">{m.calories} kcal</span>
              </div>
            ))}
          </div>
        </div>

        <div className="onboarding-actions">
          <button className="btn btn-primary" onClick={onNext}>
            Va bene, avanti <ArrowRight size={16} />
          </button>
          <button className="btn btn-ghost" onClick={() => setResult(null)}>
            Carica un altro PDF
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      <h1 className="onboarding-title">Carica la dieta</h1>
      <p className="onboarding-text">
        Il PDF del nutrizionista. Claude lo legge ed estrae i pasti con calorie e macro.
        Il file non viene conservato: resta solo la struttura estratta.
      </p>

      <label
        className={`dropzone ${over ? 'over' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) setFile(dropped);
        }}
      >
        <FileUp />
        {file ? (
          <div>
            <strong>{file.name}</strong>
            <div className="field-hint">{(file.size / 1024).toFixed(0)} KB</div>
          </div>
        ) : (
          <div>
            Trascina qui il PDF, oppure clicca per sceglierlo
            <div className="field-hint">Massimo 10 MB</div>
          </div>
        )}
        <input
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
      </label>

      <div className="onboarding-actions">
        <button className="btn btn-primary" onClick={upload} disabled={!file || busy}>
          {busy && <span className="spinner-inline" />}
          {busy ? 'Sto leggendo il PDF...' : 'Leggi la dieta'}
        </button>
      </div>
    </>
  );
}

function IngredientsStep({ onNext, addToast }) {
  const [base, setBase] = useState([]);
  const [excluded, setExcluded] = useState([]);
  const [baseDraft, setBaseDraft] = useState('');
  const [excludedDraft, setExcludedDraft] = useState('');
  const [loadedDefaults, setLoadedDefaults] = useState(false);

  const loadDefaults = async () => {
    try {
      await api.addDefaultBaseIngredients();
      setBase(await api.getBaseIngredients());
      setLoadedDefaults(true);
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const addBase = async () => {
    if (!baseDraft.trim()) return;
    try {
      const row = await api.addBaseIngredient(baseDraft.trim());
      setBase((prev) => [...prev, row]);
      setBaseDraft('');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const addExcluded = async () => {
    if (!excludedDraft.trim()) return;
    try {
      const row = await api.addExcluded(excludedDraft.trim(), null);
      setExcluded((prev) => [...prev, row]);
      setExcludedDraft('');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    <>
      <h1 className="onboarding-title">Cosa hai in casa, cosa non vuoi</h1>
      <p className="onboarding-text">
        Gli <strong>ingredienti di base</strong> sono quelli che non finiscono mai in
        lista della spesa (sale, olio, spezie). Gli <strong>esclusi</strong> non
        compariranno mai in una ricetta: allergie, intolleranze o semplicemente cose
        che non ti piacciono.
      </p>

      <div className="card">
        <div className="card-title">Ingredienti di base</div>
        {!loadedDefaults && base.length === 0 && (
          <button className="btn btn-secondary btn-sm" onClick={loadDefaults}>
            Aggiungi i soliti (sale, olio, pepe, aceto, zucchero, aglio, origano)
          </button>
        )}
        <div className="inline-form" style={{ marginTop: 10 }}>
          <IngredientInput value={baseDraft} onChange={setBaseDraft} />
          <button className="btn btn-secondary" onClick={addBase}>
            Aggiungi
          </button>
        </div>
        <div className="tag-list">
          {base.map((b) => (
            <span key={b.id} className="tag">
              {b.name}
              <button
                onClick={async () => {
                  await api.removeBaseIngredient(b.id);
                  setBase((prev) => prev.filter((x) => x.id !== b.id));
                }}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-title">Alimenti esclusi</div>
        <div className="inline-form">
          <IngredientInput
            value={excludedDraft}
            onChange={setExcludedDraft}
            placeholder="es. frutti di mare, lattosio, funghi..."
          />
          <button className="btn btn-secondary" onClick={addExcluded}>
            Escludi
          </button>
        </div>
        <div className="tag-list">
          {excluded.map((x) => (
            <span key={x.id} className="tag">
              {x.name}
              <button
                onClick={async () => {
                  await api.removeExcluded(x.id);
                  setExcluded((prev) => prev.filter((y) => y.id !== x.id));
                }}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
      </div>

      <div className="onboarding-actions">
        <button className="btn btn-primary" onClick={onNext}>
          Avanti <ArrowRight size={16} />
        </button>
      </div>
    </>
  );
}

function PreferencesStep({ onDone, addToast }) {
  const [prefs, setPrefs] = useState({
    prefer_seasonal: true,
    prefer_italian: true,
    max_prep_time_min: 45,
    budget_level: 'medio',
  });
  const [busy, setBusy] = useState(false);

  const finish = async () => {
    setBusy(true);
    try {
      await api.updatePreferences(prefs);
      await onDone();
    } catch (e) {
      addToast(e.message, 'error');
      setBusy(false);
    }
  };

  const toggle = (key) => setPrefs((p) => ({ ...p, [key]: !p[key] }));

  return (
    <>
      <h1 className="onboarding-title">Come ti piace mangiare</h1>
      <p className="onboarding-text">
        Sono i vincoli che passo a Claude a ogni generazione. Si cambiano quando vuoi
        dalle impostazioni.
      </p>

      <div className="card">
        <div className="toggle-row">
          <div className="toggle-text">
            <strong>Ingredienti di stagione</strong>
            <span>Costano meno e sanno di più</span>
          </div>
          <button
            className={`toggle ${prefs.prefer_seasonal ? 'on' : ''}`}
            onClick={() => toggle('prefer_seasonal')}
          >
            <i />
          </button>
        </div>

        <div className="toggle-row">
          <div className="toggle-text">
            <strong>Cucina italiana</strong>
            <span>Piatti di casa, ingredienti da supermercato</span>
          </div>
          <button
            className={`toggle ${prefs.prefer_italian ? 'on' : ''}`}
            onClick={() => toggle('prefer_italian')}
          >
            <i />
          </button>
        </div>

        <div className="field" style={{ marginTop: 16 }}>
          <label className="field-label">Tempo massimo di preparazione</label>
          <select
            value={prefs.max_prep_time_min ?? ''}
            onChange={(e) =>
              setPrefs((p) => ({
                ...p,
                max_prep_time_min: e.target.value ? Number(e.target.value) : null,
              }))
            }
          >
            <option value="">Nessun limite</option>
            <option value="15">15 minuti</option>
            <option value="30">30 minuti</option>
            <option value="45">45 minuti</option>
            <option value="60">1 ora</option>
          </select>
        </div>

        <div className="field">
          <label className="field-label">Budget</label>
          <select
            value={prefs.budget_level ?? ''}
            onChange={(e) => setPrefs((p) => ({ ...p, budget_level: e.target.value || null }))}
          >
            <option value="economico">Economico</option>
            <option value="medio">Medio</option>
            <option value="premium">Senza pensieri</option>
          </select>
        </div>
      </div>

      <div className="onboarding-actions">
        <button className="btn btn-primary" onClick={finish} disabled={busy}>
          {busy ? <span className="spinner-inline" /> : <Check size={16} />}
          Finito, portami dentro
        </button>
      </div>
    </>
  );
}
