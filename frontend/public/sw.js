// Service worker minimo: mette in cache la shell dell'app perché si apra anche
// senza rete (la lista della spesa al supermercato è il caso d'uso). Le chiamate
// /api NON vengono mai messe in cache: dati stantii su una dieta sono peggio di un
// errore di rete.
const CACHE = 'dietai-shell-v1';
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
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((finestre) => {
      const aperta = finestre.find((c) => new URL(c.url).origin === self.location.origin);
      if (aperta) {
        aperta.focus();
        return aperta.navigate(url);
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
            caches.open(CACHE).then((c) => c.put('/index.html', copy));
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
          const copy = response.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
          return response;
        })
    )
  );
});
