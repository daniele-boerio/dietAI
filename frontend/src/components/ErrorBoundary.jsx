import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * L'ultima rete sotto le pagine.
 *
 * Senza, un errore in un componente stacca l'intero albero React e lascia la
 * finestra vuota — nera, col tema scuro — senza un pulsante per uscirne. Sul
 * telefono è il peggio che possa capitare: non c'è una console da aprire e non si
 * capisce nemmeno se sia colpa dell'app o della rete. Meglio dirlo e offrire la via
 * d'uscita.
 */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('DietAI — errore in pagina:', error, info);
  }

  // Cambiando pagina si riprova: l'errore era di quella schermata, non dell'app, e
  // restare bloccati sul messaggio sarebbe solo un altro modo di non funzionare.
  componentDidUpdate(prev) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="empty-state">
        <AlertTriangle />
        <h3>Qualcosa si è rotto in questa schermata</h3>
        <p>
          {error.message || 'Errore imprevisto'}
          <br />
          Ricarica: i tuoi dati sono al sicuro sul server, qui non si è perso niente.
        </p>
        <button className="btn btn-primary" onClick={() => window.location.reload()}>
          Ricarica l'app
        </button>
      </div>
    );
  }
}
