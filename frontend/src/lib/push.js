// Le notifiche push dal lato del browser: chiedere il permesso, iscrivere il
// dispositivo, disiscriverlo. Il server firma le notifiche con la sua chiave VAPID e
// questa iscrizione è l'indirizzo a cui le manda.

// Cosa sa fare questo browser, detto in modo che la pagina possa spiegarlo.
// Su iPhone le notifiche esistono solo per l'app installata sulla schermata Home
// (iOS 16.4 in su): da Safari `PushManager` non c'è proprio.
export function supportoPush() {
  if (typeof window === 'undefined') return 'no';
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const installata =
    window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone;
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    return ios && !installata ? 'ios-da-installare' : 'no';
  }
  if (Notification.permission === 'denied') return 'negato';
  return 'si';
}

function chiaveInByte(base64url) {
  const pad = '='.repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob((base64url + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

// Il service worker si registra solo in produzione (main.jsx): in sviluppo `ready`
// non arriverebbe mai, e la pagina resterebbe appesa.
async function registrazione() {
  const reg = await Promise.race([
    navigator.serviceWorker.ready,
    new Promise((_, no) =>
      setTimeout(() => no(new Error('Il service worker non è attivo (in sviluppo non lo è).')), 4000)
    ),
  ]);
  return reg;
}

export async function iscrivi(publicKey) {
  const permesso = await Notification.requestPermission();
  if (permesso !== 'granted') {
    throw new Error('Senza il permesso alle notifiche il promemoria non può arrivare.');
  }
  const reg = await registrazione();
  const esistente = await reg.pushManager.getSubscription();
  const sub =
    esistente ||
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: chiaveInByte(publicKey),
    }));
  return sub.toJSON();
}

export async function iscrizioneCorrente() {
  if (supportoPush() !== 'si') return null;
  try {
    const reg = await registrazione();
    return await reg.pushManager.getSubscription();
  } catch {
    return null;
  }
}
