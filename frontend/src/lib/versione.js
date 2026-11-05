// L'app aperta sul telefono non si ricarica da sola. Su iPhone la PWA in
// background viene solo «risvegliata»: niente richiesta di index.html, niente
// bundle nuovo, e dopo un deploy si continua a vedere la versione di prima anche
// per ore (è successo con le calorie mangiate: il server era già giusto, lo schermo
// mostrava ancora il conto vecchio). Quando l'app torna in primo piano si chiede
// al server quale bundle serve adesso; se non è quello caricato, si ricarica.

// Il bundle principale scritto in un index.html (quello di Vite, con l'hash).
export function bundleDi(html) {
  const m = /<script[^>]*\ssrc="(\/assets\/[^"]+\.js)"/.exec(html || '');
  return m ? m[1] : null;
}

function bundleCaricato() {
  const s = document.querySelector('script[type="module"][src*="/assets/"]');
  return s ? new URL(s.src, location.origin).pathname : null;
}

let inCorso = false;

async function controlla() {
  if (inCorso || document.visibilityState !== 'visible') return;
  inCorso = true;
  try {
    // La query evita sia la cache HTTP sia quella del service worker, che ha
    // «/» e «/index.html» fra le sue chiavi.
    const risposta = await fetch(`/index.html?v=${Date.now()}`, { cache: 'no-store' });
    if (!risposta.ok) return;
    const nuovo = bundleDi(await risposta.text());
    const attuale = bundleCaricato();
    if (!nuovo || !attuale || nuovo === attuale) return;
    // Una volta sola per bundle: se la ricarica non bastasse, niente giro infinito.
    try {
      if (sessionStorage.getItem('dietai-ricarica') === nuovo) return;
      sessionStorage.setItem('dietai-ricarica', nuovo);
    } catch {
      /* storage non disponibile: si ricarica lo stesso */
    }
    location.reload();
  } catch {
    // Senza rete si resta sulla versione che c'è.
  } finally {
    inCorso = false;
  }
}

export function seguiVersione() {
  document.addEventListener('visibilitychange', controlla);
  window.addEventListener('pageshow', (e) => e.persisted && controlla());
}
