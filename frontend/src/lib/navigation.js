import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

/**
 * "Indietro" che non porta mai fuori dall'app.
 *
 * `navigate(-1)` sulla prima pagina della sessione esce da DietAI. Sul telefono,
 * dove l'app si apre a schermo intero dalla home (`apple-mobile-web-app-capable`),
 * fuori non c'è niente: niente barra degli indirizzi, niente pagina precedente —
 * resta uno schermo nero da cui si esce solo chiudendo l'app. E la prima pagina
 * della sessione è spessissimo il dettaglio di un pasto: iOS chiude le app tenute in
 * background e le riapre sull'ultimo indirizzo, che così diventa l'unica voce di
 * cronologia.
 *
 * React Router marca quella voce con `key === 'default'`. `idx` invece sopravvive a
 * un ricaricamento, dove la cronologia del browser c'è ancora ed è giusto usarla.
 */
export function hasInAppHistory(locationKey, historyState) {
  return locationKey !== 'default' || (historyState?.idx ?? 0) > 0;
}

export function useGoBack(fallback) {
  const navigate = useNavigate();
  const { key } = useLocation();
  const canGoBack = hasInAppHistory(key, window.history.state);

  return useCallback(() => {
    if (canGoBack) navigate(-1);
    // `replace`: la voce senza ritorno non deve restare in mezzo alla cronologia,
    // o il prossimo "indietro" ricasca esattamente qui.
    else navigate(fallback, { replace: true });
  }, [canGoBack, fallback, navigate]);
}
