import { AlertTriangle } from 'lucide-react';
import EmptyState from './EmptyState';

/**
 * Quando una pagina non riesce a caricare i suoi dati.
 *
 * Prima queste pagine restituivano `null`: si vedeva lo sfondo e basta — nero col
 * tema scuro — con l'unico avviso in un toast che dopo tre secondi non c'era più.
 * Il messaggio dell'errore serve: "sessione scaduta" e "niente rete" si risolvono in
 * due modi diversi.
 */
export default function LoadError({ message, onRetry }) {
  return (
    <EmptyState
      icon={AlertTriangle}
      title="Non sono riuscito a caricare questa pagina"
      text={message || 'Controlla la connessione e riprova.'}
      action={
        onRetry && (
          <button className="btn btn-primary" onClick={onRetry}>
            Riprova
          </button>
        )
      }
    />
  );
}
