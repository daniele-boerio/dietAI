import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, Calculator, Check, Lock, Unlock } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import { splitByWeights } from '../lib/macros';
import LoadError from './LoadError';

// Il questionario per chi una dieta scritta non ce l'ha, in due tempi.
//
// Prima i dati della persona, da cui escono calorie e macro del giorno (Mifflin-St
// Jeor, sul server: backend/app/utils/nutrition.py). Poi *quali* pasti si fanno —
// chi la colazione non la fa non deve ritrovarsela in griglia tutti i giorni — e come
// quei numeri si dividono fra loro.
//
// I due tempi sono separati perché la seconda domanda si risponde solo avendo davanti
// la prima risposta: "faccio lo spuntino di metà mattina?" dipende da quanto grande
// verrebbe, e finché non si sa che la giornata è di 2200 kcal non lo sa nessuno.
//
// Sta in un componente e non dentro una pagina perché serve in due punti che non si
// somigliano: al primo accesso, dove è l'alternativa al PDF, e in "La mia dieta", dove
// si riapre già compilato ogni volta che il peso cambia.

const DEFAULTS = {
  sex: 'donna',
  age: 30,
  height_cm: 170,
  weight_kg: 65,
  activity: 'moderato',
  goal: 'mantenere',
  meals_count: 4,
};

// Gli stessi estremi che valida il backend: qui servono a spegnere il pulsante invece
// di far tornare un errore di validazione, che arriverebbe in una lingua sola (inglese).
const LIMITS = { age: [14, 100], height_cm: [120, 230], weight_kg: [35, 250] };

const NUMBERS = [
  { key: 'age', label: 'Età', unit: 'anni' },
  { key: 'height_cm', label: 'Altezza', unit: 'cm' },
  { key: 'weight_kg', label: 'Peso', unit: 'kg' },
];

// `proposed` è quello che direbbe la formula: i totali si confrontano con lì per
// sapere se sono stati corretti a mano, e quindi se vanno mandati al server.
const TOTALI = [
  { key: 'calories', proposto: 'daily_calories', label: 'kcal al giorno', unit: '' },
  { key: 'protein_g', proposto: 'protein_g', label: 'Proteine', unit: 'g' },
  { key: 'carbs_g', proposto: 'carbs_g', label: 'Carboidrati', unit: 'g' },
  { key: 'fat_g', proposto: 'fat_g', label: 'Grassi', unit: 'g' },
];

export default function Questionnaire({
  profile,
  submitLabel = 'Calcola la mia dieta',
  onDone,
}) {
  const { addToast } = useApp();
  const [options, setOptions] = useState(null);
  const [failed, setFailed] = useState(null);
  const [form, setForm] = useState({ ...DEFAULTS, ...(profile || {}) });
  const [busy, setBusy] = useState(false);

  // Il secondo passo: i numeri calcolati, i pasti spuntati e il lucchetto.
  const [computed, setComputed] = useState(null);
  const [totals, setTotals] = useState(null);
  const [selection, setSelection] = useState([]);
  const [unlocked, setUnlocked] = useState(false);

  const loadOptions = () => {
    setFailed(null);
    api
      .getQuestionnaireOptions()
      .then(setOptions)
      .catch((e) => setFailed(e.message));
  };

  useEffect(loadOptions, []);

  // Il profilo arriva dalla dieta attiva, cioè dopo il primo render: senza questo il
  // form resterebbe sui valori di default con i dati veri già in mano.
  useEffect(() => {
    if (profile) setForm((prev) => ({ ...prev, ...profile }));
  }, [profile]);

  if (failed) return <LoadError message={failed} onRetry={loadOptions} />;
  if (!options) return <div className="spinner" />;

  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const numeriValidi = NUMBERS.every(({ key }) => {
    const value = Number(form[key]);
    const [min, max] = LIMITS[key];
    return Number.isFinite(value) && value >= min && value <= max;
  });

  const dati = () => ({
    sex: form.sex,
    age: Number(form.age),
    height_cm: Number(form.height_cm),
    weight_kg: Number(form.weight_kg),
    activity: form.activity,
    goal: form.goal,
  });

  // I pasti da cui partire: quelli dell'ultimo calcolo, se il questionario si sta
  // riaprendo, altrimenti la proposta standard per quattro pasti.
  const selezioneIniziale = () => {
    const salvati = (profile?.meals || []).filter((key) =>
      options.meals.some((m) => m.key === key)
    );
    if (salvati.length) return salvati;
    return options.default_meals[String(form.meals_count || 4)] || options.default_meals['4'];
  };

  const calcola = async () => {
    setBusy(true);
    try {
      const scelti = selezioneIniziale();
      const preview = await api.previewQuestionnaire({ ...dati(), meals: scelti });
      setComputed(preview);
      setTotals({
        calories: preview.daily_calories,
        protein_g: preview.protein_g,
        carbs_g: preview.carbs_g,
        fat_g: preview.fat_g,
      });
      setSelection(scelti);
      setUnlocked(false);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const salva = async (meals, targets) => {
    setBusy(true);
    try {
      const diet = await api.createDietFromQuestionnaire({ ...dati(), meals, targets });
      await onDone(diet);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (computed) {
    return (
      <MealSplit
        options={options}
        computed={computed}
        totals={totals}
        setTotals={setTotals}
        selection={selection}
        setSelection={setSelection}
        unlocked={unlocked}
        setUnlocked={setUnlocked}
        busy={busy}
        onBack={() => setComputed(null)}
        onConfirm={salva}
      />
    );
  }

  return (
    <>
      <div className="field">
        <label className="field-label">Sesso</label>
        <div className="segmented">
          {options.sexes.map((s) => (
            <button
              key={s}
              className={form.sex === s ? 'on' : ''}
              onClick={() => set('sex', s)}
            >
              {s === 'uomo' ? 'Uomo' : 'Donna'}
            </button>
          ))}
        </div>
        <p className="field-hint">
          Serve alla formula del metabolismo basale, che parte da valori diversi nei due
          casi. Se non ti ci ritrovi, scegli quello più vicino e correggi i numeri dopo:
          restano tutti modificabili.
        </p>
      </div>

      <div className="field-grid">
        {NUMBERS.map(({ key, label, unit }) => (
          <div className="field" key={key}>
            <label className="field-label">
              {label} <span style={{ color: 'var(--text-muted)' }}>({unit})</span>
            </label>
            <input
              type="number"
              inputMode="numeric"
              min={LIMITS[key][0]}
              max={LIMITS[key][1]}
              value={form[key] ?? ''}
              onChange={(e) => set(key, e.target.value)}
            />
          </div>
        ))}
      </div>

      <div className="field">
        <label className="field-label">Quanto ti muovi</label>
        <select value={form.activity} onChange={(e) => set('activity', e.target.value)}>
          {options.activity_levels.map((a) => (
            <option key={a.key} value={a.key}>
              {a.label} — {a.hint}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label className="field-label">Obiettivo</label>
        <select value={form.goal} onChange={(e) => set('goal', e.target.value)}>
          {options.goals.map((g) => (
            <option key={g.key} value={g.key}>
              {g.label} — {g.hint}
            </option>
          ))}
        </select>
      </div>

      <button
        className="btn btn-primary"
        onClick={calcola}
        disabled={busy || !numeriValidi}
      >
        {busy ? <span className="spinner-inline" /> : <Calculator size={16} />}
        {submitLabel}
      </button>

      <p className="field-hint" style={{ marginTop: 12 }}>
        Quali pasti fai e come si dividono le calorie si sceglie al passo dopo, con i
        numeri già davanti. Non è una prescrizione medica: è il calcolo standard
        (Mifflin-St Jeor) che trovi in qualunque manuale, un punto di partenza
        ragionevole. Se hai una dieta scritta da un professionista, quella vale di più —
        caricala e questi numeri si buttano.
      </p>
    </>
  );
}

// ── Secondo passo: quali pasti, e come si dividono ─────────────────────────────

// I totali stanno chiusi a chiave e i pasti no: è il verso giusto del vincolo. Quanto
// si mangia in un giorno l'ha deciso la formula (o il nutrizionista, o l'utente stesso
// aprendo il lucchetto); come lo si spezza durante la giornata è organizzazione, e
// cambia quando cambiano gli orari. Senza il lucchetto le due cose si confondono: si
// toglie la colazione per non farla e ci si ritrova con 400 kcal in meno al giorno,
// cioè con una dieta diversa da quella che si era calcolata dieci secondi prima.
function MealSplit({
  options,
  computed,
  totals,
  setTotals,
  selection,
  setSelection,
  unlocked,
  setUnlocked,
  busy,
  onBack,
  onConfirm,
}) {
  const { addToast } = useApp();

  const righe = useMemo(
    () => splitByWeights(options.meals.filter((m) => selection.includes(m.key)), totals),
    [options.meals, selection, totals]
  );

  const calorie = Number(totals.calories) || 0;
  const scarto = calorie - computed.proposed.daily_calories;
  const corretti = TOTALI.some(
    ({ key, proposto }) => Number(totals[key]) !== computed.proposed[proposto]
  );

  const toggle = (key) => {
    if (selection.includes(key)) {
      if (selection.length === 1) {
        addToast('Almeno un pasto al giorno deve restare', 'error');
        return;
      }
      setSelection(selection.filter((k) => k !== key));
    } else {
      setSelection([...selection, key]);
    }
  };

  // L'ordine dei pasti lo rimette il backend (quello della giornata): qui conta
  // *quali*. I totali si mandano solo se sono stati corretti a mano — altrimenti li
  // ricalcola la formula, che con gli stessi dati dà sempre gli stessi numeri.
  const conferma = () =>
    onConfirm(
      selection,
      corretti
        ? TOTALI.reduce(
            (acc, { key }) => ({ ...acc, [key]: Number(totals[key]) || 0 }),
            {}
          )
        : null
    );

  return (
    <>
      <div className={`totals-lock ${unlocked ? 'open' : ''}`}>
        <div className="totals-lock-head">
          <div>
            <strong>La tua giornata</strong>
            <span>
              Metabolismo basale {computed.bmr} kcal · fabbisogno {computed.tdee} kcal
              {scarto ? ` · calcolate ${computed.proposed.daily_calories} kcal` : ''}
            </span>
          </div>
          <button
            className={`lock-toggle ${unlocked ? 'open' : ''}`}
            onClick={() => setUnlocked(!unlocked)}
            title={
              unlocked
                ? 'Richiudi: i totali tornano intoccabili e i pasti li ridividono'
                : 'Apri per correggere calorie e macro del giorno'
            }
          >
            {unlocked ? <Unlock size={13} /> : <Lock size={13} />}
            {unlocked ? 'Modificabili' : 'Bloccati'}
          </button>
        </div>

        <div className="totals-lock-grid">
          {TOTALI.map(({ key, label, unit }) => (
            <div className="totals-lock-cell" key={key}>
              <span>{label}</span>
              {unlocked ? (
                <input
                  type="number"
                  inputMode="numeric"
                  value={totals[key] ?? ''}
                  onChange={(e) => setTotals({ ...totals, [key]: e.target.value })}
                />
              ) : (
                <strong>
                  {totals[key]}
                  {unit}
                </strong>
              )}
            </div>
          ))}
        </div>

        <p className="field-hint" style={{ marginTop: 10 }}>
          {unlocked ? (
            <>
              Adesso i totali si scrivono a mano: usalo se hai già i numeri di qualcun
              altro, o se la formula ti sembra larga. Quello che scrivi qui si ridivide
              da sé fra i pasti spuntati.
            </>
          ) : (
            <>
              Spuntando o togliendo un pasto questi numeri <strong>non cambiano</strong>:
              cambia solo in quante volte si dividono. Per correggerli apri il lucchetto.
            </>
          )}
        </p>
      </div>

      <div className="meal-pick-list">
        {options.meals.map((meal) => {
          const on = selection.includes(meal.key);
          const riga = righe.find((r) => r.key === meal.key);
          return (
            <button
              key={meal.key}
              className={`meal-pick ${on ? 'on' : ''}`}
              onClick={() => toggle(meal.key)}
            >
              <i>{on && <Check size={13} />}</i>
              <span className="meal-pick-name">{meal.name}</span>
              {on ? (
                <span className="meal-pick-macros">
                  <strong>{riga.calories} kcal</strong>
                  <em>
                    P {riga.protein_g} · C {riga.carbs_g} · G {riga.fat_g}
                  </em>
                </span>
              ) : (
                <span className="meal-pick-macros off">non lo faccio</span>
              )}
            </button>
          );
        })}
      </div>

      <p className="field-hint" style={{ marginTop: 10 }}>
        Togliendo la colazione le sue calorie vanno sugli altri pasti, in proporzione a
        quanto pesano: un pranzo e una cena più sostanziosi, non una giornata più corta.
        Nomi e valori restano correggibili uno per uno da «La mia dieta».
      </p>

      <div className="onboarding-actions" style={{ marginTop: 14 }}>
        <button
          className="btn btn-primary"
          onClick={conferma}
          disabled={busy || calorie < 500 || selection.length === 0}
        >
          {busy ? <span className="spinner-inline" /> : <ArrowRight size={16} />}
          Va bene, salva la dieta
        </button>
        <button className="btn btn-ghost" onClick={onBack} disabled={busy}>
          <ArrowLeft size={15} /> Rivedi i dati
        </button>
      </div>
    </>
  );
}
