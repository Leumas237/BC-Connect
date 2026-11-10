const CACHE = "bc-connect-v2";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([
    "/",
    "/static/style.css",
    "/static/manifest.json",
    "/static/logo.svg",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
  ])));
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
