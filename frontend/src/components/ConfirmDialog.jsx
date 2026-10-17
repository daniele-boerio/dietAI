import Modal from './Modal';

export default function ConfirmDialog({
  title,
  text,
  confirmLabel = 'Conferma',
  cancelLabel = 'Annulla',
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal title={title} onClose={onCancel} busy={busy}>
      {text && <p className="modal-text">{text}</p>}
      <div className="modal-actions">
        {/* Primo nell'ordine del focus: un Invio di troppo annulla, non conferma. */}
        <button className="btn btn-secondary" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy && <span className="spinner-inline" />}
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
