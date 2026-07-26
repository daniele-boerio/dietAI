import { useEffect, useRef, useState } from 'react';
import { Brain, FileText } from 'lucide-react';
import { api } from '../api';

// Quanto spesso si chiede al server a che punto è. Il diario lato server si riscrive
// ogni due secondi: chiedere più spesso mostrerebbe due volte la stessa riga.
const POLL_MS = 2000;

function durata(secondi) {
  const m = Math.floor(secondi / 60);
  const s = secondi % 60;
  return m ? `${m} min ${s}s` : `${s}s`;
}

/**
 * Cosa sta facendo il modello mentre costruisce la settimana.
 *
 * Non è un dettaglio da nerd: la generazione dura minuti, si paga, e una schermata
 * ferma non permette di distinguere un modello che sta ragionando da uno piantato.
 * Il ragionamento (quando il modello lo lascia vedere) e il JSON che sta scrivendo
 * arrivano già in streaming al backend: qui si guardano scorrere.
 */
export default function GenerationLog({ weekId }) {
  const [data, setData] = useState(null);
  const [vista, setVista] = useState('reasoning');
  const [secondi, setSecondi] = useState(0);
  const paneRef = useRef(null);

  useEffect(() => {
    let vivo = true;
    const chiedi = async () => {
      try {
        const res = await api.getGenerationProgress(weekId);
        if (vivo) setData(res);
      } catch {
        // Un buco di rete non deve far sparire quello che si stava leggendo.
      }
    };
    chiedi();
    const timer = setInterval(chiedi, POLL_MS);
    return () => {
      vivo = false;
      clearInterval(timer);
    };
  }, [weekId]);

  // Il cronometro va per conto suo: dice che l'attesa è viva anche nei secondi in cui
  // il modello ragiona in silenzio e il diario non cambia di una riga.
  useEffect(() => {
    if (!data?.started_at) return;
    const inizio = new Date(data.started_at).getTime();
    const tick = () => setSecondi(Math.max(0, Math.round((Date.now() - inizio) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [data?.started_at]);

  const ragiona = (data?.reasoning_chars || 0) > 0;
  const scrive = (data?.content_chars || 0) > 0;
  // Si guarda il ragionamento finché c'è; appena cominciano le ricette si passa a
  // quelle, che sono la cosa concreta.
  const attiva = vista === 'content' || !ragiona ? 'content' : 'reasoning';
  const testo = (attiva === 'content' ? data?.content : data?.reasoning) || '';

  useEffect(() => {
    if (paneRef.current) paneRef.current.scrollTop = paneRef.current.scrollHeight;
  }, [testo]);

  const fatte = data?.recipes_written || 0;
  const attese = data?.expected_recipes || 0;

  return (
    <div className="generation-log">
      <div className="generation-log-head">
        <div className="generation-log-tabs">
          <button
            className={`generation-log-tab ${attiva === 'reasoning' ? 'active' : ''}`}
            onClick={() => setVista('reasoning')}
            disabled={!ragiona}
          >
            <Brain size={14} /> Ragionamento
          </button>
          <button
            className={`generation-log-tab ${attiva === 'content' ? 'active' : ''}`}
            onClick={() => setVista('content')}
            disabled={!scrive}
          >
            <FileText size={14} /> Ricette
          </button>
        </div>
        <span className="generation-log-meta">
          {attese > 0 && scrive ? `${Math.min(fatte, attese)} di ${attese} · ` : ''}
          {durata(secondi)}
        </span>
      </div>

      {attese > 0 && (
        <div className="generation-bar">
          <div
            className="generation-bar-fill"
            style={{ width: `${Math.min(100, Math.round((fatte / attese) * 100))}%` }}
          />
        </div>
      )}

      <pre className="generation-log-pane" ref={paneRef}>
        {testo ||
          (ragiona || scrive
            ? '…'
            : 'Il modello ha ricevuto la richiesta. Alcuni modelli non mostrano il ragionamento: in quel caso qui comparirà direttamente la prima ricetta.')}
      </pre>
    </div>
  );
}
