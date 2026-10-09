const CACHE_VERSION = "mpb-site-v39";
const CORE_CACHE = `${CACHE_VERSION}-core`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const OFFLINE_URL = "/offline.html";

const CORE_ASSETS = [
    "/",
    "/index.html",
    "/schedule",
    "/schedule.html",
    "/stats",
    "/stats.html",
    "/studio",
    "/studio.html",
    "/studio-editor.html",
    "/login",
    "/login.html",
    "/register",
    "/register.html",
    "/account",
    "/account.html",
    "/js/account.js?v=20261009-4",
    OFFLINE_URL,
    "/project",
    "/project.html",
    "/js/archive_download.js?v=20261009-4",
    "/js/home_recent.js?v=20261009-4",
    "/js/offline.js?v=20261009-4",
    "/js/product_ui.js?v=20261009-4",
    "/js/project_readme.js?v=20261009-5",
    "/js/schedule_workspace.js?v=20261009-4",
    "/js/stats_workspace.js?v=20261009-4",
    "/js/studio_workspace.js?v=20261009-4",
    "/css/product_ui.css?v=20261009-6",

    "/site.webmanifest",
    "/css/tailwind.css?v=20261009-4",
    "/css/studio.css?v=2",
    "/js/runtime_config.js?v=20260821-6",
    "/js/ui_utils.js?v=2",
    "/js/frontend_i18n.js?v=1",
    "/js/navbar.js?v=20261009-4",
    "/js/theme_bootstrap.js?v=20260821-6",
    "/js/telegram_webapp.js?v=20260821-6",
    "/js/schedule_state.js?v=20260821-6",
    "/js/schedule_api.js?v=20260924-1",
    "/js/schedule_filters.js?v=20260821-6",
    "/js/schedule_render.js?v=20260924-2",
    "/js/schedule.js?v=20261009-6",
    "/js/calendar_sync.js?v=20261009-4",
    "/js/schedule_ux.js?v=20260831-10",
    "/js/stats.js?v=20261009-4",
    "/js/stats_ux.js?v=2",
    "/js/studio.js?v=20261009-4",
    "/js/studio_session.js?v=20261009-4",
    "/js/studio_libraries.js?v=1",
    "/js/studio_monaco.js?v=1",
    "/js/schedule_planner.js?v=20261009-4",
    "/js/insights.js?v=20261009-4",
    "/css/feature_panels.css?v=20261009-1",
    "/js/auth.js?v=20261009-4",
    "/locales/en.json",
    "/locales/ru.json",
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
        const response = await fetch(new Request(request, { cache: "no-cache" }));
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

async function networkFirstCodeAsset(request) {
    try {
        const response = await fetch(new Request(request, { cache: "no-cache" }));
        if (response && response.ok) {
            const cache = await caches.open(RUNTIME_CACHE);
            cache.put(request, response.clone());
        }
        return response;
    } catch (_error) {
        return caches.match(request);
    }
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

    const isSameOriginCodeAsset =
        url.origin === self.location.origin &&
        (url.pathname.startsWith("/js/") ||
            url.pathname.startsWith("/css/") ||
            url.pathname.endsWith(".js") ||
            url.pathname.endsWith(".css"));
    if (isSameOriginCodeAsset) {
        event.respondWith(networkFirstCodeAsset(request));
        return;
    }

    event.respondWith(staleWhileRevalidate(request));
});
