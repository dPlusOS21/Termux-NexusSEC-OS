// Service worker minimale: cache dello "shell" della PWA per installabilita'
// e avvio offline dell'interfaccia. Le chiamate /api/* passano sempre dalla rete.
const CACHE = "nexussec-v2";
const SHELL = ["./", "index.html", "manifest.json"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // sempre live, mai da cache
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
