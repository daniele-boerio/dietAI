import { useRef, useState } from 'react';
import { Receipt, Sparkles, X } from 'lucide-react';
import { api, formatMoney } from '../api';
import { useApp } from '../App';

// La foto dello scontrino. Segnare i prezzi a mano è una riga alla volta, col carrello
// in mano; lo scontrino li ha tutti, e a casa si fotografa in un secondo. Il modello
// legge le righe e le abbina agli articoli della lista, e da lì vale la stessa logica
// del prezzo scritto a mano. Quello che non ha trovato posto in lista si mostra,
// invece di sparire: un detersivo è normale, una riga di pollo che non si è abbinata no.
//
// La foto si rimpicciolisce qui prima di partire: un telefono ne fa da 4 MB, al modello
// ne bastano 1600 pixel di lato — e ogni pixel in più si paga in token.
const LATO_MAX = 1600;

async function rimpicciolisci(file) {
  try {
    const bitmap = await createImageBitmap(file);
    const scala = Math.min(1, LATO_MAX / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scala);
    canvas.height = Math.round(bitmap.height * scala);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((ok) => canvas.toBlob(ok, 'image/jpeg', 0.85));
    return blob ? new File([blob], 'scontrino.jpg', { type: 'image/jpeg' }) : file;
  } catch {
    // Un formato che il browser non sa decodificare (HEIC su un desktop): parte com'è.
    return file;
  }
}

export default function ReceiptReader({ onList }) {
  const { addToast } = useApp();
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [esito, setEsito] = useState(null);

  const leggi = async (file) => {
    if (!file) return;
    setBusy(true);
    setEsito(null);
    try {
      const res = await api.readReceipt(await rimpicciolisci(file));
      onList(res.list);
      setEsito(res);
      addToast(
        res.matched
          ? `Scontrino letto: ${res.matched} ${res.matched === 1 ? 'articolo' : 'articoli'} col prezzo pagato ✓`
          : 'Scontrino letto, ma nessuna riga corrisponde alla lista'
      );
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  return (
    <div className="receipt-reader">
      <button
        className="btn btn-ai btn-block"
        onClick={() => input.current?.click()}
        disabled={busy}
      >
        {busy ? <span className="spinner-inline" /> : <Sparkles size={16} />}
        {busy ? 'Leggo lo scontrino…' : 'Leggi lo scontrino'}
      </button>
      <input
        ref={input}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => leggi(e.target.files?.[0])}
      />

      {esito?.unmatched?.length > 0 && (
        <div className="receipt-unmatched">
          <div className="receipt-unmatched-head">
            <Receipt size={14} /> Rimaste fuori dalla lista
            <button
              className="btn btn-ghost btn-icon btn-sm"
              aria-label="Chiudi"
              onClick={() => setEsito(null)}
            >
              <X size={14} />
            </button>
          </div>
          <ul>
            {esito.unmatched.map((r, i) => (
              <li key={i}>
                <span>{r.text || '—'}</span>
                <span>{formatMoney(r.price)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
