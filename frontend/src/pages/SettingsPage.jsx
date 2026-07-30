import { useEffect, useState } from 'react';
import { Link, NavLink, Navigate, useParams } from 'react-router-dom';
import { KeyRound, ShieldOff, Sparkles, Trash2, UserPlus, X } from 'lucide-react';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import { useAuth } from '../AuthContext';
import ConfirmDialog from '../components/ConfirmDialog';
import IngredientInput from '../components/IngredientInput';
import ModelPicker from '../components/ModelPicker';

// Qui stanno solo le cose che si impostano una volta e poi restano. Quelle che
// cambiano di continuo hanno una pagina loro: la dieta (`/diet`) e la dispensa
// (`/pantry`), che si riempie da sola a ogni spesa.
//
// Due schede sono dell'amministratore soltanto: i modelli AI (li paga lui, e valgono
// per tutti) e gli utenti. Non è una questione di ordine — chi non amministra, quelle
// rotte le riceve con un 403.
const TABS = [
  { key: 'preferences', label: 'Preferenze' },
  { key: 'base', label: 'Ingredienti di base' },
  { key: 'excluded', label: 'Alimenti esclusi' },
  { key: 'models', label: 'Modelli AI', adminOnly: true },
  { key: 'users', label: 'Utenti', adminOnly: true },
  { key: 'account', label: 'Account' },
];

export default function SettingsPage() {
  const { tab = 'preferences' } = useParams();
  const { user } = useAuth();

  const tabs = TABS.filter((t) => !t.adminOnly || user.is_admin);

  // Un indirizzo scritto a mano (o un vecchio segnalibro) su una scheda che non c'è
  // non deve lasciare la pagina vuota: si torna alla prima.
  if (!tabs.some((t) => t.key === tab)) {
    return <Navigate to="/settings/preferences" replace />;
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Impostazioni</h1>
          <p className="page-subtitle">
            Sono i vincoli che passo al modello a ogni generazione: cambiarli cambia le
            ricette della prossima settimana. I pasti e i macro stanno in{' '}
            <Link to="/diet">La mia dieta</Link>.
          </p>
        </div>
      </div>

      <div className="settings-layout">
        <nav className="settings-nav">
          {tabs.map((t) => (
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
          {tab === 'preferences' && <PreferencesTab />}
          {tab === 'base' && <BaseTab />}
          {tab === 'excluded' && <ExcludedTab />}
          {tab === 'models' && <ModelsTab />}
          {tab === 'users' && <UsersTab />}
          {tab === 'account' && <AccountTab />}
        </div>
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

// ── Utenti ─────────────────────────────────────────────────────────────────────

// Gli account non si registrano da soli: li crea chi ha la chiave, e la password
// iniziale si dice a voce. L'app non manda posta — niente SMTP, niente inviti, niente
// link di recupero — quindi questa schermata è l'unico posto da cui si rimette in
// piedi un account, e deve saper fare tutto: crearlo, sospenderlo, ridargli la
// password, cancellarlo.
function UsersTab() {
  const { addToast } = useApp();
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState(null);
  const [resetting, setResetting] = useState(null);
  const [newPassword, setNewPassword] = useState('');

  const load = () => api.getUsers().then(setUsers).catch((e) => addToast(e.message, 'error'));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    setBusy(true);
    try {
      await api.createUser(email.trim(), password);
      setEmail('');
      setPassword('');
      await load();
      addToast('Account creato ✓ — la password gliela dici tu');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const setFlag = async (row, payload) => {
    try {
      const updated = await api.updateUserFlags(row.id, payload);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const resetPassword = async () => {
    setBusy(true);
    try {
      const res = await api.resetUserPassword(resetting.id, newPassword);
      addToast(res.detail);
      setResetting(null);
      setNewPassword('');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.deleteUser(toDelete.id);
      setToDelete(null);
      await load();
      addToast('Account cancellato con tutti i suoi dati');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (!users) return <div className="spinner" />;

  return (
    <>
      <div className="card settings-section">
        <div className="card-title">
          <UserPlus /> Nuovo account
        </div>
        <p className="field-hint" style={{ marginBottom: 12 }}>
          Chi entra da qui ha le sue ricette, la sua dieta, la sua spesa e la sua
          dispensa — non vedrà niente di tuo. Genera però con la <strong>tua</strong>{' '}
          API key e coi modelli che hai scelto tu: la spesa in chiamate è tua, ed è per
          questo che qui sotto c'è un interruttore per spegnergliele.
        </p>
        <div className="field">
          <label className="field-label">Email</label>
          <input
            type="email"
            autoComplete="off"
            placeholder="nome@esempio.it"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <p className="field-hint">
            Serve solo come nome utente: l'app non manda nessuna mail, quindi può anche
            non esistere davvero.
          </p>
        </div>
        <div className="field">
          <label className="field-label">Password iniziale</label>
          <input
            type="text"
            autoComplete="off"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className="field-hint">
            Almeno 8 caratteri. È in chiaro apposta: la devi leggere per dettarla, e la
            cambierà lui da Impostazioni → Account.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={create}
          disabled={busy || email.trim().length < 3 || password.length < 8}
        >
          {busy && <span className="spinner-inline" />}
          Crea l'account
        </button>
      </div>

      <div className="card settings-section">
        <div className="card-title">Account esistenti</div>
        <div className="list-rows">
          {users.map((u) => (
            <div key={u.id} className="list-row">
              <div className="list-row-main">
                <strong>
                  {u.email}
                  {u.id === me.id && ' (tu)'}
                </strong>
                <span>
                  {u.is_admin ? 'Amministratore' : 'Utente'}
                  {u.created_at && ` · dal ${formatDate(u.created_at)}`}
                  {u.has_active_diet ? ' · dieta attiva' : ' · nessuna dieta'}
                </span>
              </div>

              <div className="user-row-flags">
                {!u.is_active && <span className="badge badge-danger">Sospeso</span>}
                {!u.ai_enabled && <span className="badge badge-warning">AI spenta</span>}
              </div>

              {!u.is_admin && (
                <div className="user-row-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setFlag(u, { ai_enabled: !u.ai_enabled })}
                    title={
                      u.ai_enabled
                        ? 'Spegni le funzioni AI: smette di generare, i suoi dati restano'
                        : 'Riaccendi le funzioni AI'
                    }
                  >
                    <Sparkles size={14} /> {u.ai_enabled ? 'Spegni AI' : 'Riaccendi AI'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setFlag(u, { is_active: !u.is_active })}
                    title={
                      u.is_active
                        ? "Sospendi l'accesso: non entra più, ma non si perde niente"
                        : "Rimetti l'accesso"
                    }
                  >
                    <ShieldOff size={14} /> {u.is_active ? 'Sospendi' : 'Riattiva'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setResetting(u);
                      setNewPassword('');
                    }}
                  >
                    <KeyRound size={14} /> Password
                  </button>
                  <button
                    className="icon-button danger"
                    title="Cancella l'account e tutti i suoi dati"
                    onClick={() => setToDelete(u)}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {resetting && (
          <div className="card" style={{ marginTop: 14 }}>
            <div className="card-title">Nuova password per {resetting.email}</div>
            <div className="inline-form">
              <input
                type="text"
                autoComplete="off"
                placeholder="Almeno 8 caratteri"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <button
                className="btn btn-primary"
                onClick={resetPassword}
                disabled={busy || newPassword.length < 8}
              >
                Imposta
              </button>
              <button className="btn btn-ghost" onClick={() => setResetting(null)}>
                Annulla
              </button>
            </div>
            <p className="field-hint">
              Le sue sessioni aperte vengono chiuse: dovrà rientrare con questa.
            </p>
          </div>
        )}
      </div>

      {toDelete && (
        <ConfirmDialog
          danger
          busy={busy}
          title={`Cancellare ${toDelete.email}?`}
          text="Spariscono anche le sue ricette, i suoi piani, la sua spesa e la sua dispensa, e non si torna indietro. Se ti serve solo togliergli l'accesso, sospendilo."
          confirmLabel="Cancella tutto"
          onConfirm={remove}
          onCancel={() => setToDelete(null)}
        />
      )}
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
      {user.can_manage_api_key ? (
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
      ) : (
        // Niente campo, ma nemmeno silenzio: le ricette le scrive un modello che
        // qualcuno paga, e sapere che le chiamate non sono a proprio carico spiega
        // anche perché la scelta del modello qui non c'è.
        <div className="card settings-section">
          <div className="card-title">
            <KeyRound /> Funzioni AI
          </div>
          <p className="field-hint">
            {user.ai_enabled
              ? 'Le ricette le genera il modello scelto dall’amministratore, con la sua API key: non devi configurare niente.'
              : 'Le funzioni AI sono al momento sospese su questo account: il piano, la spesa e la dispensa restano come sono. Chiedi all’amministratore di riaccenderle.'}
          </p>
        </div>
      )}

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
