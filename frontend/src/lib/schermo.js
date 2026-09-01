import { useEffect, useState } from 'react';

// Una media query letta da JavaScript.
//
// Serve solo dove la larghezza non cambia *come* una cosa è fatta ma **cosa** è: la
// chat della spesa sul monitor è una colonna in pagina, sul telefono è un cassetto
// che si apre da un pulsante e si chiude con la X. Sono due componenti diversi, con
// due comandi diversi, e nasconderne uno col CSS vorrebbe dire montarli tutti e due
// — due conversazioni sullo stesso schermo, di cui una invisibile che continua a
// scaricare messaggi.
//
// Dove basta il CSS si usa il CSS: questo file non è la strada normale.
export function useMediaQuery(query) {
  const [combacia, setCombacia] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches
  );

  useEffect(() => {
    const mq = window.matchMedia(query);
    const aggiorna = (e) => setCombacia(e.matches);
    // Lo stato si rilegge anche adesso: fra il primo render e questo effetto la
    // finestra può essere già cambiata (succede aprendo l'app in orizzontale).
    setCombacia(mq.matches);
    mq.addEventListener('change', aggiorna);
    return () => mq.removeEventListener('change', aggiorna);
  }, [query]);

  return combacia;
}

// La soglia oltre la quale le pagine si aprono in due colonne. È la stessa dei
// blocchi `@media (max-width: 1100px)` del foglio di stile: se cambia lì, cambia qui.
export const useDueColonne = () => useMediaQuery('(min-width: 1101px)');
