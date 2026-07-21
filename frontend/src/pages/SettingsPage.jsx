import { useEffect, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { FileUp, KeyRound, Save, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import { useAuth } from '../AuthContext';
import IngredientInput from '../components/IngredientInput';
import ModelPicker from '../components/ModelPicker';

const TABS = [
  { key: 'diet', label: 'La mia dieta' },
  { key: 'base', label: 'Ingredienti di base' },
  { key: 'excluded', label: 'Alimenti esclusi' },
  { key: 'pantry', label: 'Dispensa' },
  { key: 'preferences', label: 'Preferenze' },
  { key: 'models', label: 'Modelli AI' },
  { key: 'account', label: 'Account e API key' },
];

export default function SettingsPage() {
  const { tab = 'diet' } = useParams();

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Impostazioni</h1>
          <p className="page-subtitle">
            Sono i vincoli che passo a Claude a ogni generazione: cambiarli cambia le
            ricette della prossima settimana.
          </p>
        </div>
      </div>

      <div className="settings-layout">
        <nav className="settings-nav">
          {TABS.map((t) => (
            <NavLink
              key={t.key}
              to={`/settings/${t.key}`}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              {t.label}
            </NavLink>
          ))}
        </nav>

        <div>
          {tab === 'diet' && <DietTab />}
          {tab === 'base' && <BaseTab />}
          {tab === 'excluded' && <ExcludedTab />}
          {tab === 'pantry' && <PantryTab />}
          {tab === 'preferences' && <PreferencesTab />}
          {tab === 'models' && <ModelsTab />}
          {tab === 'account' && <AccountTab />}
        </div>
      </div>
    </>
  );
}

// ── La mia dieta ───────────────────────────────────────────────────────────────

function DietTab() {
  const { addToast } = useApp();
  const [diet, setDiet] = useState(null);
  const [meals, setMeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);

  const load = () =>
    api
      .getDiet()
      .then((d) => {
        setDiet(d);
        setMeals(d.meals);
      })
      .catch(() => setDiet(null))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const updateMeal = (index, field, value) =>
    setMeals((prev) =>
      prev.map((m, i) =>
        i === index ? { ...m, [field]: field === 'name' ? value : Number(value) } : m
      )
    );

  const save = async () => {
    setBusy(true);
    try {
      const payload = meals.map((m, i) => ({
        name: m.name,
        order: i,
        calories: Number(m.calories) || 0,
        protein_g: Number(m.protein_g) || 0,
        carbs_g: Number(m.carbs_g) || 0,
        fat_g: Number(m.fat_g) || 0,
        notes: m.notes || null,
      }));
      const updated = await api.updateDietMeals(diet.id, payload);
      setDiet(updated);
      setMeals(updated.meals);
      addToast('Dieta aggiornata ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const updated = await api.uploadDiet(file);
      setDiet(updated);
      setMeals(updated.meals);
      setFile(null);
      addToast(`Nuova dieta caricata: ${updated.meals.length} pasti ✓`);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="spinner" />;

  const total = meals.reduce((sum, m) => sum + (Number(m.calories) || 0), 0);

  return (
    <>
      <div className="card settings-section">
        <div className="card-title">Pasti e macro</div>
        <p className="field-hint" style={{ marginBottom: 14 }}>
          Questi numeri sono il vincolo più duro di tutta l'app: ogni ricetta deve starci
          dentro con una tolleranza del 10%. Se il PDF è stato letto male, correggilo qui.
        </p>

        <div className="meal-editor-row meal-editor-head">
          <span>Pasto</span>
          <span>kcal</span>
          <span>Prot.</span>
          <span>Carb.</span>
          <span>Grassi</span>
          <span />
        </div>

        {meals.map((meal, i) => (
          <div key={i} className="meal-editor-row">
            <input value={meal.name} onChange={(e) => updateMeal(i, 'name', e.target.value)} />
            <input
              type="number"
              value={meal.calories}
              onChange={(e) => updateMeal(i, 'calories', e.target.value)}
            />
            <input
              type="number"
              value={meal.protein_g}
              onChange={(e) => updateMeal(i, 'protein_g', e.target.value)}
            />
            <input
              type="number"
              value={meal.carbs_g}
              onChange={(e) => updateMeal(i, 'carbs_g', e.target.value)}
            />
            <input
              type="number"
              value={meal.fat_g}
              onChange={(e) => updateMeal(i, 'fat_g', e.target.value)}
            />
            <button
              className="icon-button danger"
              onClick={() => setMeals((prev) => prev.filter((_, idx) => idx !== i))}
              title="Rimuovi il pasto"
            >
              <X size={15} />
            </button>
          </div>
        ))}

        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() =>
              setMeals((prev) => [
                ...prev,
                {
                  name: 'Nuovo pasto',
                  order: prev.length,
                  calories: 300,
                  protein_g: 20,
                  carbs_g: 35,
                  fat_g: 10,
                },
              ])
            }
          >
            Aggiungi pasto
          </button>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={busy}>
            {busy ? <span className="spinner-inline" /> : <Save size={14} />}
            Salva
          </button>
          <span style={{ marginLeft: 'auto', alignSelf: 'center', color: 'var(--text-secondary)' }}>
            Totale: <strong>{total} kcal</strong>
          </span>
        </div>
      </div>

      <div className="card settings-section">
        <div className="card-title">Carica un nuovo PDF</div>
        <p className="field-hint" style={{ marginBottom: 12 }}>
          Il nutrizionista ti ha dato una dieta nuova? Caricala: quella attuale finisce in
          archivio e i pasti vengono riletti da capo.
        </p>
        <label className="dropzone">
          <FileUp />
          {file ? <strong>{file.name}</strong> : 'Scegli il PDF della dieta'}
          <input
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>
        <button
          className="btn btn-primary btn-sm"
          style={{ marginTop: 12 }}
          onClick={upload}
          disabled={!file || busy}
        >
          {busy && <span className="spinner-inline" />}
          Leggi e sostituisci
        </button>
      </div>
    </>
  );
}

// ── Liste di ingredienti ───────────────────────────────────────────────────────

function BaseTab() {
  const { addToast } = useApp();
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    api.getBaseIngredients().then(setItems).catch(() => {});
  }, []);

  const add = async () => {
    if (!draft.trim()) return;
    try {
      const row = await api.addBaseIngredient(draft.trim());
      setItems((prev) => [...prev, row]);
      setDraft('');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    <div className="card">
      <div className="card-title">Ingredienti di base</div>
      <p className="field-hint" style={{ marginBottom: 14 }}>
        Quello che hai sempre in casa. Non finisce mai nella lista della spesa, ma le
        ricette possono usarlo liberamente.
      </p>

      <div className="inline-form">
        <IngredientInput value={draft} onChange={setDraft} />
        <button className="btn btn-secondary" onClick={add}>
          Aggiungi
        </button>
      </div>

      <div className="tag-list">
        {items.map((i) => (
          <span key={i.id} className="tag">
            {i.name}
            <button
              onClick={async () => {
                await api.removeBaseIngredient(i.id);
                setItems((prev) => prev.filter((x) => x.id !== i.id));
              }}
            >
              <X size={13} />
            </button>
          </span>
        ))}
        {items.length === 0 && <p className="field-hint">Nessun ingrediente di base.</p>}
      </div>
    </div>
  );
}

function ExcludedTab() {
  const { addToast } = useApp();
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState('');
  const [reason, setReason] = useState('');

  useEffect(() => {
    api.getExcluded().then(setItems).catch(() => {});
  }, []);

  const add = async () => {
    if (!draft.trim()) return;
    try {
      const row = await api.addExcluded(draft.trim(), reason || null);
      setItems((prev) => [...prev, row]);
      setDraft('');
      setReason('');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    <div className="card">
      <div className="card-title">Alimenti esclusi</div>
      <p className="field-hint" style={{ marginBottom: 14 }}>
        Non compariranno in nessuna ricetta, in nessuna forma. Puoi scrivere anche
        categorie intere ("frutti di mare") oltre ai singoli ingredienti.
      </p>

      <div className="inline-form">
        <IngredientInput value={draft} onChange={setDraft} placeholder="Alimento da escludere" />
        <select
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          style={{ maxWidth: 170 }}
        >
          <option value="">Motivo (opzionale)</option>
          <option value="allergia">Allergia</option>
          <option value="intolleranza">Intolleranza</option>
          <option value="non piace">Non mi piace</option>
        </select>
        <button className="btn btn-secondary" onClick={add}>
          Escludi
        </button>
      </div>

      <div className="tag-list">
        {items.map((i) => (
          <span key={i.id} className="tag">
            {i.name}
            {i.reason && <small>({i.reason})</small>}
            <button
              onClick={async () => {
                await api.removeExcluded(i.id);
                setItems((prev) => prev.filter((x) => x.id !== i.id));
              }}
            >
              <X size={13} />
            </button>
          </span>
        ))}
        {items.length === 0 && <p className="field-hint">Nessun alimento escluso.</p>}
      </div>
    </div>
  );
}

function PantryTab() {
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
    <div className="card">
      <div className="card-title">Dispensa</div>
      <p className="field-hint" style={{ marginBottom: 14 }}>
        Quello che hai già in casa viene sottratto dalla lista della spesa e proposto per
        primo alle ricette. Si aggiorna da solo quando segni una spesa come fatta.
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
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
        {items.length === 0 && <p className="field-hint">Dispensa vuota.</p>}
      </div>
    </div>
  );
}

// ── Preferenze ─────────────────────────────────────────────────────────────────

function PreferencesTab() {
  const { addToast } = useApp();
  const [prefs, setPrefs] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getPreferences().then(setPrefs).catch(() => {});
  }, []);

  if (!prefs) return <div className="spinner" />;

  const save = async (next) => {
    setPrefs(next);
    setBusy(true);
    try {
      await api.updatePreferences(next);
      addToast('Preferenze salvate ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="card-title">Preferenze di cucina</div>

      <div className="toggle-row">
        <div className="toggle-text">
          <strong>Ingredienti di stagione</strong>
          <span>Costano meno, sanno di più e la spesa cambia con i mesi</span>
        </div>
        <button
          className={`toggle ${prefs.prefer_seasonal ? 'on' : ''}`}
          disabled={busy}
          onClick={() => save({ ...prefs, prefer_seasonal: !prefs.prefer_seasonal })}
        >
          <i />
        </button>
      </div>

      <div className="toggle-row">
        <div className="toggle-text">
          <strong>Cucina italiana</strong>
          <span>Piatti di casa con ingredienti da supermercato italiano</span>
        </div>
        <button
          className={`toggle ${prefs.prefer_italian ? 'on' : ''}`}
          disabled={busy}
          onClick={() => save({ ...prefs, prefer_italian: !prefs.prefer_italian })}
        >
          <i />
        </button>
      </div>

      <div className="field" style={{ marginTop: 18 }}>
        <label className="field-label">Tempo massimo di preparazione</label>
        <select
          value={prefs.max_prep_time_min ?? ''}
          onChange={(e) =>
            save({
              ...prefs,
              max_prep_time_min: e.target.value ? Number(e.target.value) : null,
            })
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
          onChange={(e) => save({ ...prefs, budget_level: e.target.value || null })}
        >
          <option value="">Non specificato</option>
          <option value="economico">Economico</option>
          <option value="medio">Medio</option>
          <option value="premium">Senza pensieri</option>
        </select>
      </div>
    </div>
  );
}

// ── Modelli AI ─────────────────────────────────────────────────────────────────

function ModelsTab() {
  const { addToast } = useApp();
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getAiConfig().then(setConfig).catch(() => {});
    api
      .getAiModels()
      .then((d) => setModels(d.models))
      .catch(() => setModels([]));
  }, []);

  if (!config) return <div className="spinner" />;

  const change = async (role, model) => {
    const payload = Object.fromEntries(
      config.roles.map((r) => [r.key, r.key === role ? model : r.model])
    );
    setBusy(true);
    try {
      setConfig(await api.updateAiModels(payload));
      addToast('Modello aggiornato ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card settings-section">
        <div className="card-title">Provider: {config.provider}</div>
        <p className="field-hint">
          {config.can_list_models ? (
            <>
              Con OpenRouter una sola chiave ti dà accesso ai modelli di tutti i
              fornitori. Puoi usare un modello diverso per ogni ruolo: quello che conta
              davvero è la pianificazione settimanale, il resto può costare molto meno.
              {models.length > 0 && ` ${models.length} modelli disponibili.`}
            </>
          ) : (
            <>
              Provider fisso via configurazione. Per poter scegliere tra più modelli
              imposta <code>AI_PROVIDER=openrouter</code> nelle variabili d'ambiente.
            </>
          )}
        </p>
      </div>

      {config.roles.map((role) => (
        <div key={role.key} className="card settings-section">
          <div className="card-title">{role.label}</div>
          <p className="field-hint" style={{ marginBottom: 12 }}>
            {role.hint}
          </p>

          {models.length > 0 ? (
            <ModelPicker
              role={role.key}
              models={models}
              value={role.model}
              defaultModel={role.default}
              onChange={change}
            />
          ) : (
            <div className="inline-form">
              <input
                type="text"
                defaultValue={role.model || ''}
                placeholder={role.default}
                onBlur={(e) => change(role.key, e.target.value.trim() || null)}
                disabled={busy}
              />
            </div>
          )}
        </div>
      ))}

      <p className="field-hint">
        Un modello più economico si nota soprattutto in due punti: quanto spesso sbaglia
        il formato JSON (e va ritentato) e quanti pasti finiscono fuori dal ±10% dei
        macro. Il secondo lo misuri da solo: genera una settimana e guarda la
        percentuale di aderenza in <strong>Andamento</strong>.
      </p>
    </>
  );
}

// ── Account ────────────────────────────────────────────────────────────────────

function AccountTab() {
  const { user, refreshUser, logout } = useAuth();
  const { addToast } = useApp();
  const [apiKey, setApiKey] = useState('');
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [busy, setBusy] = useState(false);
  const [ai, setAi] = useState(null);

  useEffect(() => {
    api.getAiConfig().then(setAi).catch(() => {});
  }, []);

  const saveKey = async () => {
    setBusy(true);
    try {
      await api.setApiKey(apiKey.trim());
      setApiKey('');
      await refreshUser();
      addToast('API key aggiornata ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async () => {
    setBusy(true);
    try {
      await api.changePassword(current, next);
      addToast('Password aggiornata: rifai il login');
      await logout();
    } catch (e) {
      addToast(e.message, 'error');
      setBusy(false);
    }
  };

  return (
    <>
      <div className="card settings-section">
        <div className="card-title">
          <KeyRound /> API key {ai ? `(${ai.provider})` : ''}
        </div>
        <p className="field-hint" style={{ marginBottom: 12 }}>
          {user.has_api_key
            ? 'Una chiave è già salvata (cifrata). Inserirne una nuova sostituisce la vecchia.'
            : 'Nessuna chiave salvata: le funzioni AI sono spente.'}{' '}
          {ai?.key_url && (
            <a href={ai.key_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
              Dove trovarla
            </a>
          )}
        </p>
        <div className="inline-form">
          <input
            type="password"
            placeholder={`${ai?.key_prefix || 'sk-'}...`}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <button
            className="btn btn-primary"
            onClick={saveKey}
            disabled={busy || apiKey.trim().length < 20}
          >
            Salva
          </button>
        </div>
      </div>

      <div className="card settings-section">
        <div className="card-title">Password</div>
        <div className="field">
          <label className="field-label">Password attuale</label>
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label">Nuova password</label>
          <input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <p className="field-hint">
            Almeno 8 caratteri. Cambiandola tutte le sessioni aperte vengono chiuse.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={changePassword}
          disabled={busy || !current || next.length < 8}
        >
          {busy && <span className="spinner-inline" />}
          Cambia password
        </button>
      </div>
    </>
  );
}
