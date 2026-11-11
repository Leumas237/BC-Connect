const CACHE = "bc-connect-v5";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll([
    "/",
    "/static/style.css",
    "/static/manifest.json",
    "/static/logo.svg",
    "/static/assets/campus-connect.svg",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
  ])));
});

self.addEventListener("fetch", (event) => {
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});

self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(self.registration.showNotification(data.title || "BC Connect", {
    body: data.body || "Tu as une nouvelle connexion.",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow("/#auth"));
});
