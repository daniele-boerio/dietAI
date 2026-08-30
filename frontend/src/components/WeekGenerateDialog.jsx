import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Sparkles } from 'lucide-react';
import { contaSelezione, daGenerare, giorniPredefiniti } from '../lib/generation';

// I pasti che non si vogliono generare sono quasi sempre gli stessi — chi la colazione
// se la prepara da sé lo fa tutte le settimane — quindi la scelta si ricorda. Si
// ricordano i pasti **esclusi** e non quelli spuntati: così un pasto aggiunto alla
// dieta dopo nasce acceso, che è quello che ci si aspetta. I giorni no: cambiano di
// settimana in settimana, e ricordarli non vorrebbe dire niente.
const MEMORIA = 'dietai.generazione.pasti-esclusi';

const leggiEsclusi = () => {
  try {
    const salvato = JSON.parse(localStorage.getItem(MEMORIA));
    return Array.isArray(salvato) ? salvato : [];
  } catch {
    return [];
  }
};

const scriviEsclusi = (nomi) => {
  try {
    localStorage.setItem(MEMORIA, JSON.stringify(nomi));
  } catch {
    // Navigazione privata, spazio finito: la memoria è una comodità, non un requisito.
  }
};

const plurale = (n, uno, molti) => `${n} ${n === 1 ? uno : molti}`;

/**
 * Cosa generare della settimana: quali giorni, quali pasti.
 *
 * Generare è la cosa più cara che fa l'app, e prima si pagava sempre la settimana
 * intera mentre quasi mai serve intera: le colazioni le fa chi le fa, i giorni già
 * passati sono andati, e il piatto di giovedì può star bene com'è. Qui si spunta
 * prima di pagare, e il pulsante dice quanti pasti verranno generati.
 *
 * Resta comunque **una chiamata sola**: l'anti-spreco (mezza zucchina lunedì, l'altra
 * metà giovedì) vive lì, e spezzare la selezione in più richieste lo perderebbe.
 */
export default function WeekGenerateDialog({
  week,
  rigeneraDefault = false,
  busy = false,
  onGenerate,
  onCancel,
}) {
  const [rifaiTutto, setRifaiTutto] = useState(rigeneraDefault);
  const [giorni, setGiorni] = useState([]);
  // `null` = non ancora inizializzati dalla memoria: distinguerlo dall'array vuoto
  // serve a non riaccendere tutto appena l'utente li toglie uno per uno.
  const [pasti, setPasti] = useState(null);

  // Quante caselle ci sono da fare, per ogni giorno e per ogni pasto, nella modalità
  // scelta: solo le vuote, oppure tutte quelle generabili. La conta è la stessa che
  // fa il server (`lib/generation.js`), o il numero sul pulsante mentirebbe.
  const { celle, giorni: listaGiorni, pasti: listaPasti } = useMemo(
    () => daGenerare(week, { rifaiTutto }),
    [week, rifaiTutto]
  );

  // I giorni si ricalcolano ogni volta che cambia la modalità: con «rifai tutto» ne
  // diventano disponibili altri — quelli già pieni — e lasciarli spenti farebbe
  // sembrare che non ci sia niente da rigenerare.
  useEffect(() => {
    setGiorni(giorniPredefiniti(listaGiorni));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rifaiTutto, week]);

  // I pasti invece si spuntano una volta e restano: quello che si è escluso la
  // settimana scorsa è quasi sempre quello da escludere anche adesso.
  useEffect(() => {
    if (pasti !== null) return;
    const esclusi = leggiEsclusi();
    setPasti(listaPasti.filter((p) => !esclusi.includes(p.nome)).map((p) => p.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pasti, week]);

  const scelti = pasti || [];
  const totale = contaSelezione(celle, giorni, scelti);

  const toggleGiorno = (dow) =>
    setGiorni((prec) => (prec.includes(dow) ? prec.filter((d) => d !== dow) : [...prec, dow]));

  const togglePasto = (id) =>
    setPasti((prec) => (prec.includes(id) ? prec.filter((p) => p !== id) : [...prec, id]));

  const genera = () => {
    scriviEsclusi(listaPasti.filter((p) => !scelti.includes(p.id)).map((p) => p.nome));
    onGenerate({ regenerateAll: rifaiTutto, days: giorni, slotIds: scelti });
  };

  const nienteDaFare = celle.length === 0;

  return (
    <div className="modal-overlay" onClick={busy ? undefined : onCancel}>
      <div className="modal modal-lg" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">Cosa ti genero?</h2>
        <p className="modal-text" style={{ marginBottom: 16 }}>
          Spunta i giorni e i pasti: è una chiamata sola al modello, e quello che lasci
          fuori resta esattamente com'è.
        </p>

        <div className="gen-section">
          <div className="gen-section-head">
            <span className="field-label" style={{ marginBottom: 0 }}>
              Giorni
            </span>
            <div className="gen-quick">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setGiorni(listaGiorni.filter((g) => g.da_fare > 0).map((g) => g.dow))}
                disabled={busy || nienteDaFare}
              >
                Tutti
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setGiorni([])}
                disabled={busy || !giorni.length}
              >
                Nessuno
              </button>
            </div>
          </div>

          <div className="gen-days">
            {listaGiorni.map((g) => {
              const vuoto = g.da_fare === 0;
              const on = giorni.includes(g.dow) && !vuoto;
              return (
                <button
                  key={g.dow}
                  className={`gen-day ${on ? 'on' : ''} ${g.passato ? 'passato' : ''}`}
                  onClick={() => toggleGiorno(g.dow)}
                  disabled={busy || vuoto}
                  title={
                    g.saltato
                      ? 'Giornata saltata'
                      : vuoto
                        ? 'Niente da generare in questo giorno'
                        : `${plurale(g.da_fare, 'pasto', 'pasti')} da generare`
                  }
                >
                  <span className="gen-day-name">{g.nome.slice(0, 3)}</span>
                  <span className="gen-day-num">{Number(g.date.slice(8, 10))}</span>
                  <span className="gen-day-count">
                    {g.saltato ? 'salt.' : vuoto ? '—' : g.da_fare}
                  </span>
                </button>
              );
            })}
          </div>

          {listaGiorni.some((g) => g.passato && g.da_fare > 0) && (
            <p className="field-hint">
              I giorni già passati partono spenti: quel pasto è stato, o non è stato, e
              riempirlo adesso è una chiamata pagata per niente. Se ti serve, spuntali.
            </p>
          )}
        </div>

        <div className="gen-section">
          <span className="field-label">Pasti</span>
          <div className="meal-pick-list">
            {listaPasti.map((p) => {
              const bloccato = p.mio || p.da_fare === 0;
              const on = scelti.includes(p.id) && !bloccato;
              return (
                <button
                  key={p.id}
                  className={`meal-pick ${on ? 'on' : ''}`}
                  onClick={() => togglePasto(p.id)}
                  disabled={busy || bloccato}
                >
                  <i>{on && <Check size={13} />}</i>
                  <span className="meal-pick-name">{p.nome}</span>
                  <span className={`meal-pick-macros ${bloccato ? 'off' : ''}`}>
                    {p.mio
                      ? 'lo prepari tu'
                      : p.da_fare === 0
                        ? 'niente da fare'
                        : plurale(p.da_fare, 'casella', 'caselle')}
                  </span>
                </button>
              );
            })}
          </div>
          {listaPasti.some((p) => p.mio) && (
            <p className="field-hint">
              I pasti segnati «lo prepari tu» non si generano mai: quello si cambia da{' '}
              <strong>La mia dieta</strong>. Qui la scelta vale per questa volta — ma me
              la ricordo per la prossima.
            </p>
          )}
        </div>

        {/* Rifare una casella che una ricetta ce l'ha già è l'altra metà della stessa
            domanda: tenerla qui evita il secondo pulsante, che la faceva su tutta la
            settimana senza poter scegliere niente. */}
        <button
          className={`meal-pick ${rifaiTutto ? 'on' : ''}`}
          onClick={() => setRifaiTutto((v) => !v)}
          disabled={busy}
        >
          <i>{rifaiTutto && <Check size={13} />}</i>
          <span className="meal-pick-name">Rifai anche i pasti che hanno già una ricetta</span>
        </button>

        {rifaiTutto && (
          <div className="notice notice-error" style={{ marginTop: 12 }}>
            <AlertTriangle />
            <div>
              Le ricette di adesso vengono sostituite — restano nel ricettario, e i pasti
              fissi o che prepari tu non si toccano. Per cambiarne una sola conviene
              rigenerarla dalla sua card.
            </div>
          </div>
        )}

        <div className="modal-actions gen-actions">
          <span className="gen-total">
            {nienteDaFare
              ? 'Niente da generare'
              : totale === 0
                ? 'Non hai spuntato niente'
                : plurale(totale, 'pasto da generare', 'pasti da generare')}
          </span>
          <button className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Annulla
          </button>
          <button className="btn btn-primary" onClick={genera} disabled={busy || totale === 0}>
            {busy ? <span className="spinner-inline" /> : <Sparkles size={16} />}
            {totale > 0 ? `Genera ${plurale(totale, 'pasto', 'pasti')}` : 'Genera'}
          </button>
        </div>
      </div>
    </div>
  );
}
