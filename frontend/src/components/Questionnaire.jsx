import { useEffect, useState } from 'react';
import { Calculator } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import LoadError from './LoadError';

// Il questionario per chi una dieta scritta non ce l'ha: sette domande da cui escono
// calorie, macro e la divisione fra i pasti. Il conto lo fa una formula sul server
// (Mifflin-St Jeor), non il modello — vedi backend/app/utils/nutrition.py.
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

  const submit = async () => {
    setBusy(true);
    try {
      const diet = await api.createDietFromQuestionnaire({
        sex: form.sex,
        age: Number(form.age),
        height_cm: Number(form.height_cm),
        weight_kg: Number(form.weight_kg),
        activity: form.activity,
        goal: form.goal,
        meals_count: Number(form.meals_count),
      });
      await onDone(diet);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

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

      <div className="field">
        <label className="field-label">Quanti pasti al giorno</label>
        <select
          value={form.meals_count}
          onChange={(e) => set('meals_count', Number(e.target.value))}
        >
          {options.meal_counts.map((n) => (
            <option key={n} value={n}>
              {n} pasti
            </option>
          ))}
        </select>
        <p className="field-hint">
          Colazione, pranzo e cena, più gli spuntini. Il totale della giornata non
          cambia: cambia in quante volte lo si divide.
        </p>
      </div>

      <button
        className="btn btn-primary"
        onClick={submit}
        disabled={busy || !numeriValidi}
      >
        {busy ? <span className="spinner-inline" /> : <Calculator size={16} />}
        {submitLabel}
      </button>

      <p className="field-hint" style={{ marginTop: 12 }}>
        Non è una prescrizione medica: è il calcolo standard (Mifflin-St Jeor) che trovi
        in qualunque manuale, un punto di partenza ragionevole. Se hai una dieta scritta
        da un professionista, quella vale di più — caricala e questi numeri si buttano.
      </p>
    </>
  );
}
