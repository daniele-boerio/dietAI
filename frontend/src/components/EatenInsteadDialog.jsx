import { useEffect, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import { otherNutrientsLine } from '../lib/nutrients';

// «Ho mangiato altro»: subito dopo il pulsante, la domanda. Prima la si trovava solo
// aprendo il pasto, sotto i pulsanti, e quasi nessuno la vedeva: il pasto restava
// saltato senza dire cosa, cioè un buco nei dati — per l'andamento e per healthAI,
// che un pasto senza stima non lo ricevono.
//
// Si può non rispondere («Non lo so»): il pasto resta «ho mangiato altro», come
// prima. Il pulsante che stima chiama il modello, quindi è `.btn-ai` con le scintille.
export default function EatenInsteadDialog({ meal, onSaved, onClose }) {
  const { addToast } = useApp();
  const [testo, setTesto] = useState(meal.deviation_notes || '');
  const [busy, setBusy] = useState(false);
  const campo = useRef(null);

  useEffect(() => {
    campo.current?.focus();
  }, []);

  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && !busy && onClose();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [busy, onClose]);

  const invia = async (niente) => {
    setBusy(niente ? 'niente' : 'stima');
    try {
      const updated = await api.setEatenInstead(meal.id, niente ? null : testo.trim(), niente);
      const stima = updated.eaten_nutrition;
      if (niente) {
        addToast('Segnato: non hai mangiato niente');
      } else if (stima) {
        const altri = otherNutrientsLine(stima);
        addToast(`Stimato: circa ${stima.calories} kcal${altri ? ` · ${altri}` : ''}`);
      }
      onSaved(updated);
      onClose();
    } catch (err) {
      // La modale resta aperta col testo scritto: riprovare non deve voler dire
      // riscriverlo.
      addToast(err.message, 'error');
      setBusy(false);
    }
  };

  const salva = (e) => {
    e.preventDefault();
    if (testo.trim()) invia(false);
  };

  return (
    <div className="modal-overlay" onClick={busy ? undefined : onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={salva}>
        <h2 className="modal-title">Cosa hai mangiato invece?</h2>
        <p className="modal-text">
          {meal.slot_name ? `${meal.slot_name}: ` : ''}scrivilo come lo diresti — «una pizza
          margherita», «panino al bar e una birra». Il modello stima calorie e valori
          nutrizionali, e l'andamento li conta.
        </p>
        <input
          ref={campo}
          type="text"
          className="eaten-dialog-input"
          maxLength={500}
          placeholder="una pizza margherita, un panino al bar…"
          value={testo}
          onChange={(e) => setTesto(e.target.value)}
          disabled={busy}
          aria-label="Cosa hai mangiato invece"
        />
        {/* «Niente» è una risposta, non un rinuncia: si salva come zero saputo, e
            senza modello (niente scintille). «Non lo so» invece chiude e basta. */}
        <div className="modal-actions eaten-dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={!!busy}>
            Non lo so
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => invia(true)}
            disabled={!!busy}
          >
            {busy === 'niente' && <span className="spinner-inline" />}
            Non ho mangiato niente
          </button>
          <button type="submit" className="btn btn-ai" disabled={!!busy || !testo.trim()}>
            {busy === 'stima' ? <span className="spinner-inline" /> : <Sparkles size={16} />}
            Stima
          </button>
        </div>
      </form>
    </div>
  );
}
