// Service worker della PWA.
// - /api/*        -> sempre dalla rete (mai cache).
// - HTML/navigazioni -> RETE-first (l'aggiornamento si vede subito; cache solo
//   come fallback offline). Evita di restare "incastrati" su una pagina vecchia.
// - altri asset   -> cache-first (avvio rapido/offline).
const CACHE = "nexussec-v7";
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

function isHTML(req, url) {
  return req.mode === "navigate" || url.pathname === "/" ||
         url.pathname.endsWith("/") || url.pathname.endsWith(".html");
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // sempre live

  if (isHTML(e.request, url)) {
    // rete-first: prende la versione aggiornata; offline -> cache.
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copy = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
          return r;
        })
        .catch(() => caches.match(e.request).then((r) => r || caches.match("index.html")))
    );
    return;
  }

  // altri asset: cache-first
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
