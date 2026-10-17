import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

// Gli avvisi dell'app. Prima il contenitore nasceva insieme al primo avviso, e una
// regione live inserita già piena il lettore di schermo non la annuncia: gli errori,
// l'unico segno che un'azione non era andata, restavano muti. Ora le due regioni ci
// sono sempre — «status» per le conferme, «alert» per gli errori, che interrompono —
// e stanno fuori da #root: quando una modale è aperta il resto dell'app è inert, e
// un avviso arrivato in quel momento non si potrebbe né leggere né chiudere.
export default function Toast({ toasts, onClose }) {
  const voce = (t) => (
    <div key={t.id} className={`toast toast-${t.type}`}>
      <span>{t.message}</span>
      <button className="toast-close" onClick={() => onClose(t.id)} aria-label="Chiudi l'avviso">
        <X size={14} />
      </button>
    </div>
  );
  return createPortal(
    <div className="toast-container">
      <div role="status" aria-live="polite" className="toast-stack">
        {toasts.filter((t) => t.type !== 'error').map(voce)}
      </div>
      <div role="alert" aria-live="assertive" className="toast-stack">
        {toasts.filter((t) => t.type === 'error').map(voce)}
      </div>
    </div>,
    document.body
  );
}
