const CACHE_VERSION = "mpb-site-v2";
const CORE_CACHE = `${CACHE_VERSION}-core`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const OFFLINE_URL = "/offline.html";

const CORE_ASSETS = [
    "/",
    "/index.html",
    "/schedule",
    "/schedule.html",
    "/studio",
    "/studio.html",
    "/login",
    "/login.html",
    "/register",
    "/register.html",
    OFFLINE_URL,
    "/site.webmanifest",
    "/css/tailwind.css?v=1",
    "/js/runtime_config.js?v=1",
    "/js/ui_utils.js?v=1",
    "/js/navbar.js?v=24",
    "/js/navbar.js?v=23",
    "/js/theme_bootstrap.js?v=1",
    "/js/telegram_webapp.js?v=2",
    "/js/schedule.js?v=22",
    "/js/calendar_sync.js?v=5",
    "/js/schedule_ux.js?v=7",
    "/js/studio.js?v=10",
    "/js/auth.js?v=6",
    "/favicon.ico",
    "/favicon-16x16.png",
    "/favicon-32x32.png",
    "/apple-touch-icon.png",
    "/android-chrome-192x192.png",
    "/android-chrome-512x512.png",
    "/logo.png",
    "/thelogo.png",
    "/inverted_logo.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CORE_CACHE).then((cache) => cache.addAll(CORE_ASSETS)).then(() => {
            self.skipWaiting();
        })
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key.startsWith("mpb-site-") && !key.startsWith(CACHE_VERSION))
                    .map((key) => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

async function networkFirstNavigation(request) {
    try {
        const response = await fetch(request);
        const cache = await caches.open(RUNTIME_CACHE);
        cache.put(request, response.clone());
        return response;
    } catch (_error) {
        const url = new URL(request.url);
        return (
            (await caches.match(request)) ||
            (await caches.match(url.pathname)) ||
            (await caches.match(`${url.pathname}.html`)) ||
            (await caches.match(OFFLINE_URL))
        );
    }
}

async function staleWhileRevalidate(request) {
    const cached = await caches.match(request);
    const fetchPromise = fetch(request).then(async (response) => {
        if (response && (response.ok || response.type === "opaque")) {
            const cache = await caches.open(RUNTIME_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    });
    return cached || fetchPromise;
}

self.addEventListener("fetch", (event) => {
    const { request } = event;
    if (request.method !== "GET") return;

    const url = new URL(request.url);
    if (url.origin === self.location.origin && url.pathname.startsWith("/api/")) {
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(networkFirstNavigation(request));
        return;
    }

    event.respondWith(staleWhileRevalidate(request));
});
