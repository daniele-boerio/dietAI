// Service worker minimo: mette in cache la shell dell'app perché si apra anche
// senza rete (la lista della spesa al supermercato è il caso d'uso). Le chiamate
// /api NON vengono mai messe in cache: dati stantii su una dieta sono peggio di un
// errore di rete.
// v2: la v1 poteva contenere risposte d'errore messe in cache come asset; cambiare
// nome la fa svuotare all'attivazione.
const CACHE = 'dietai-shell-v2';
// Ogni deploy porta bundle con un nome nuovo: oltre questo numero si buttano i più
// vecchi, o la cache cresce per sempre.
const MAX_ASSET = 60;
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

// Il promemoria serale (e la notifica di prova): il server manda titolo, testo e
// l'indirizzo da aprire. Il `tag` fa sì che due promemoria non si impilino: il
// secondo sostituisce il primo.
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data && event.data.text() };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'DietAI', {
      body: data.body || '',
      icon: '/icon.svg',
      badge: '/icon.svg',
      tag: data.tag || 'dietai',
      data: { url: data.url || '/' },
    })
  );
});

// Toccando la notifica si torna all'app se è già aperta, invece di aprirne un'altra.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const richiesto = (event.notification.data && event.notification.data.url) || '/';
  // Solo indirizzi dell'app: il payload lo firma il server, ma una notifica non deve
  // poter portare altrove.
  const url = new URL(richiesto, self.location.origin).origin === self.location.origin
    ? richiesto
    : '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((finestre) => {
      const aperta = finestre.find((c) => new URL(c.url).origin === self.location.origin);
      if (aperta) {
        aperta.focus();
        // `navigate` rifiuta sulle finestre che il service worker non controlla:
        // prima il tocco non faceva niente.
        return aperta.navigate(url).catch(() => self.clients.openWindow(url));
      }
      return self.clients.openWindow(url);
    })
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api')) return;

  // Navigazioni: rete prima, cache come rete di sicurezza (SPA → index.html).
  //
  // La copia in cache si riscrive a ogni apertura riuscita, e non è un dettaglio:
  // l'index.html messo da parte all'installazione punta a un bundle col suo hash nel
  // nome, che il deploy successivo cancella dal server. Con la rete ballerina — cioè
  // sul telefono — la pagina di riserva caricherebbe uno script che non esiste più:
  // l'app si apre e resta nera, senza nemmeno un errore da leggere.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            event.waitUntil(caches.open(CACHE).then((c) => c.put('/index.html', copy)));
          }
          return response;
        })
        .catch(() => caches.match('/index.html'))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          // In cache solo quello che è davvero l'asset chiesto. Un 502 durante un
          // deploy, o un index.html servito al posto di uno script, finivano qui sotto
          // il nome dello script e venivano serviti per sempre: app nera.
          const tipo = response.headers.get('content-type') || '';
          if (response.ok && response.type === 'basic' && !tipo.includes('text/html')) {
            const copy = response.clone();
            event.waitUntil(
              caches.open(CACHE).then((c) => c.put(request, copy).then(() => sfoltisci(c)))
            );
          }
          return response;
        })
    )
  );
});

async function sfoltisci(cache) {
  const chiavi = await cache.keys();
  const asset = chiavi.filter((r) => new URL(r.url).pathname.startsWith('/assets/'));
  await Promise.all(asset.slice(0, Math.max(0, asset.length - MAX_ASSET)).map((r) => cache.delete(r)));
}
