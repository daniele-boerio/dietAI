import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';

const FOCUSABILI =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// La finestra modale di tutta l'app. Prima ogni modale era un `div` sopra la pagina:
// niente ruolo né nome per il lettore di schermo, il focus restava sul pulsante dietro
// l'overlay, Tab usciva nella pagina coperta e solo una delle sette si chiudeva con Esc.
// Qui una volta sola: `role="dialog"` col titolo come nome, focus dentro all'apertura
// e di nuovo sul pulsante di partenza alla chiusura, Tab che gira dentro, Esc e clic
// sullo sfondo che chiudono — tranne mentre `busy`, perché chiudere a metà di una
// chiamata al modello lascerebbe la risposta senza nessuno ad aspettarla. Il resto
// dell'app diventa `inert` finché la modale è aperta.
export default function Modal({
  title,
  onClose,
  busy = false,
  as: Tag = 'div',
  className = '',
  children,
  ...rest
}) {
  const id = useId();
  const box = useRef(null);
  const chiudi = useRef(onClose);
  chiudi.current = busy ? null : onClose;

  useEffect(() => {
    const prima = document.activeElement;
    const app = document.getElementById('root');
    app?.setAttribute('inert', '');

    // Chi ha già messo l'autoFocus su un campo vince; altrimenti il primo controllo.
    if (!box.current?.contains(document.activeElement)) {
      (box.current?.querySelector(FOCUSABILI) || box.current)?.focus();
    }

    const tasti = (e) => {
      if (e.key === 'Escape') {
        chiudi.current?.();
        return;
      }
      if (e.key !== 'Tab' || !box.current) return;
      const controlli = [...box.current.querySelectorAll(FOCUSABILI)];
      if (!controlli.length) return;
      const primo = controlli[0];
      const ultimo = controlli[controlli.length - 1];
      if (e.shiftKey && document.activeElement === primo) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && document.activeElement === ultimo) {
        e.preventDefault();
        primo.focus();
      }
    };
    document.addEventListener('keydown', tasti);

    return () => {
      document.removeEventListener('keydown', tasti);
      app?.removeAttribute('inert');
      prima?.focus?.();
    };
  }, []);

  return createPortal(
    <div className="modal-overlay" onClick={() => chiudi.current?.()}>
      <Tag
        ref={box}
        className={`modal ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-titolo`}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        {...rest}
      >
        <h2 className="modal-title" id={`${id}-titolo`}>
          {title}
        </h2>
        {children}
      </Tag>
    </div>,
    document.body
  );
}
