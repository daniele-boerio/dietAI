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
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">{title}</h2>
        {text && <p className="modal-text">{text}</p>}
        <div className="modal-actions">
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
      </div>
    </div>
  );
}
