/* Service worker for the JayMax Concepts employee task portal (Prep + Counts).
 * Scope: enables "Add to Home Screen" installs on staff phones/tablets, keeps
 * the app shell available when a device loses signal mid-shift, and receives
 * web push notifications when a manager assigns/schedules a new task. */
const CACHE_NAME = "jaymax-employee-shell-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Network-first with cache fallback for the app shell only — API requests are
// always PIN/session scoped and must never be served from cache.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET" || request.url.includes("/api/")) return;
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return response;
      })
      .catch(() => caches.match(request))
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "JayMax Concepts", body: "You have a new task." };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch { /* fall back to defaults if the payload isn't JSON */ }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: `${self.registration.scope}favicon.ico`,
      badge: `${self.registration.scope}favicon.ico`,
      data: { taskId: data.taskId },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clients) => {
      const existing = clients.find((c) => "focus" in c);
      if (existing) return existing.focus();
      return self.clients.openWindow("./");
    })
  );
});
