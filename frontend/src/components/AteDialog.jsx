import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import Modal from './Modal';

const ESEMPI = `Pasta al pomodoro, circa 100 g, con un filo d'olio.
Una pizza margherita in pizzeria e una birra media.
Toast prosciutto e formaggio e un caffè al bar.`;

// «Ho mangiato questo» / «Pasto libero»: su una casella vuota si scrive a parole un
// piatto (di oggi o del passato: quello che si è mangiato; di un giorno che verrà: un
// pasto libero in programma). Il modello lo trasforma in una ricetta (i macro si contano dagli
// ingredienti) e il pasto nasce già seguito: senza, quel giorno restava un buco per
// l'andamento e per healthAI. La dispensa non si tocca — non si sa se era roba di casa.
export default function AteDialog({ meal, futuro = false, onSaved, onClose }) {
  const { addToast } = useApp();
  const [testo, setTesto] = useState('');
  const [busy, setBusy] = useState(false);

  const salva = async (e) => {
    e.preventDefault();
    if (testo.trim().length < 3) return;
    setBusy(true);
    try {
      const updated = await api.ateMeal(meal.id, testo.trim());
      addToast(
        `${futuro ? 'In programma' : 'Segnato'}: ${updated.recipe.title} · ${updated.recipe.calories} kcal`,
      );
      onSaved(updated);
      onClose();
    } catch (err) {
      // La modale resta aperta col testo scritto: riprovare non deve voler dire
      // riscriverlo.
      addToast(err.message, 'error');
      setBusy(false);
    }
  };

  return (
    <Modal
      as="form"
      title={futuro ? 'Pasto libero' : 'Cosa hai mangiato?'}
      onClose={onClose}
      busy={busy}
      onSubmit={salva}
    >
      <p className="modal-text">
        {meal.slot_name}: scrivilo come lo diresti, con le quantità se le sai. Diventa una
        ricetta con calorie e macro stimati così com'è, senza adattarla ai tuoi target
        {futuro ? '.' : ', e il pasto risulta seguito.'}
      </p>
      <textarea
        rows={4}
        value={testo}
        placeholder={ESEMPI}
        aria-label={futuro ? 'Cosa mangerai' : 'Cosa hai mangiato'}
        onChange={(e) => setTesto(e.target.value)}
        maxLength={1000}
        disabled={busy}
        autoFocus
      />
      <div className="modal-actions" style={{ marginTop: 16 }}>
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={busy}>
          Annulla
        </button>
        <button type="submit" className="btn btn-ai" disabled={busy || testo.trim().length < 3}>
          {busy ? <span className="spinner-inline" /> : <Sparkles size={16} />}
          {futuro ? 'Mettilo in programma' : 'Segna come mangiato'}
        </button>
      </div>
    </Modal>
  );
}
