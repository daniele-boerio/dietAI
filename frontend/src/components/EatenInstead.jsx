import { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { api, formatNumber } from '../api';
import { useApp } from '../App';

// «Ho mangiato altro: cosa?». Senza, un pasto saltato è un buco nei dati: si sa che il
// piano non è stato seguito, non cosa si è mangiato al suo posto. Si scrive a parole
// ("una pizza", "panino al bar") e il modello ne stima calorie e macro — è un ordine di
// grandezza, e lo si dice; l'andamento lo usa per il totale del giorno.
//
// Il pulsante è un `.btn-ai` con le scintille: chiama il modello, e sta accanto a
// comandi che non costano niente.
export default function EatenInstead({ meal, onSaved }) {
  const { addToast } = useApp();
  const [testo, setTesto] = useState(meal.deviation_notes || '');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setTesto(meal.deviation_notes || '');
  }, [meal.id, meal.deviation_notes]);

  const stima = meal.eaten_nutrition;
  const cambiato = testo.trim() !== (meal.deviation_notes || '');

  const salva = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      onSaved(await api.setEatenInstead(meal.id, testo.trim()));
    } catch (err) {
      addToast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="eaten-instead" onSubmit={salva}>
      <label className="field-label" htmlFor={`mangiato-${meal.id}`}>
        Cosa hai mangiato invece?
      </label>
      <div className="eaten-row">
        <input
          id={`mangiato-${meal.id}`}
          type="text"
          maxLength={500}
          placeholder="una pizza margherita, un panino al bar…"
          value={testo}
          onChange={(e) => setTesto(e.target.value)}
        />
        <button className="btn btn-ai btn-sm" disabled={busy || !cambiato}>
          {busy ? <span className="spinner-inline" /> : <Sparkles size={14} />}
          {testo.trim() ? 'Stima' : 'Cancella'}
        </button>
      </div>
      {stima && !cambiato && (
        <p className="eaten-estimate">
          ≈ {stima.calories} kcal · P {formatNumber(stima.protein_g, 0)} · C{' '}
          {formatNumber(stima.carbs_g, 0)} · G {formatNumber(stima.fat_g, 0)}
          {stima.note ? <span> — stima: {stima.note}</span> : null}
        </p>
      )}
    </form>
  );
}
