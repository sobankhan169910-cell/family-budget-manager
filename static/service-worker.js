"use strict";

const CACHE_NAME = "family-budget-shell-v2";
const APP_SHELL = [
    "/static/css/style.css",
    "/static/js/app.js",
    "/static/images/app-icon-192.png",
    "/static/images/app-icon-512.png",
    "/static/manifest.webmanifest",
    "/static/offline.html",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key.startsWith("family-budget-shell-") && key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const requestUrl = new URL(event.request.url);
    if (requestUrl.origin !== self.location.origin || event.request.method !== "GET") {
        return;
    }

    if (event.request.mode === "navigate") {
        event.respondWith(
            fetch(event.request, {cache: "no-store"}).catch(() =>
                caches.match("/static/offline.html")
            )
        );
        return;
    }

    if (APP_SHELL.includes(requestUrl.pathname)) {
        event.respondWith(
            caches.match(event.request).then((cachedResponse) =>
                cachedResponse || fetch(event.request)
            )
        );
    }
});
