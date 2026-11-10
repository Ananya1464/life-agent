/* Offline shell: the app's own files load instantly and without signal. Vault data (/api) is never cached. */
const VERSION = 'lifebot-web-v1';
const SHELL = [
  '/', '/index.html', '/styles.css', '/app.js', '/md.js', '/avocado-art.js', '/lib/pomodoro.js',
  '/fonts/PressStart2P-Regular.ttf', '/icons/icon-192.png', '/manifest.webmanifest',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  // network first, so a new version shows up right away; the cache covers no-signal moments
  e.respondWith(
    fetch(e.request).then((res) => {
      if (res.ok && res.type === 'basic') { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); }
      return res;
    }).catch(() => caches.match(e.request).then((hit) => hit || caches.match('/index.html'))),
  );
});
