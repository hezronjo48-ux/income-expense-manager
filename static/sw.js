// Service Worker for Income & Expense Manager PWA
const CACHE_VERSION = 'v2';
const STATIC_CACHE  = `myledger-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `myledger-dynamic-${CACHE_VERSION}`;
const SHELL_CACHE   = `myledger-shell-${CACHE_VERSION}`;
const SHELL_HTML    = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MyLedger</title><style>body{margin:0;font-family:system-ui,sans-serif;background:#0EA5E9;display:flex;justify-content:center;align-items:center;height:100vh;color:#fff}.c{text-align:center}.c h2{margin:0 0 .4rem;font-size:1.2rem}.c p{margin:0;font-size:.85rem;opacity:.8}</style></head><body><div class="c"><h2>MyLedger</h2><p>Check your connection and try again.</p></div></body></html>`;

// Static assets to cache at install (only truly static, no auth-gated pages)
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/manifest.json',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
  'https://cdn.jsdelivr.net/npm/chart.js'
];

// Simple fetch timeout helper
function fetchTimeout(request, ms) {
  return new Promise((resolve, reject) => {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), ms);
    fetch(request, { signal: controller.signal })
      .then(r => { clearTimeout(id); resolve(r); })
      .catch(e => { clearTimeout(id); reject(e); });
  });
}

// Cache strategies
const CACHE_STRATEGIES = {
  // Static assets - Cache First
  static: async (request) => {
    const cached = await caches.match(request);
    if (cached) return cached;
    try {
      const response = await fetchTimeout(request, 8000);
      if (response.ok) {
        const cache = await caches.open(STATIC_CACHE);
        cache.put(request, response.clone());
      }
      return response;
    } catch {
      return new Response('Offline', { status: 503 });
    }
  },

  // API/Data - Network First, fallback to cache
  api: async (request) => {
    try {
      const response = await fetchTimeout(request, 10000);
      if (response.ok) {
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, response.clone());
      }
      return response;
    } catch {
      const cached = await caches.match(request);
      return cached || new Response(JSON.stringify({ offline: true }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
  },

  // Pages - Network First with timeout, fallback to cache / offline shell
  page: async (request) => {
    const cached = await caches.match(request);
    try {
      const response = await fetchTimeout(request, 8000);
      if (response.ok) {
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, response.clone());
      }
      return response;
    } catch {
      // Network failed or timed out — serve last-known cache or the offline shell
      return cached || new Response(SHELL_HTML, {
        headers: { 'Content-Type': 'text/html', 'Cache-Control': 'no-cache' }
      });
    }
  }
};

// Install - Cache static assets + offline shell
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      return cache.addAll(STATIC_ASSETS.map(url => new Request(url, { credentials: 'same-origin' })));
    }).then(() => caches.open(SHELL_CACHE).then(c => c.put('/__offline-shell', new Response(SHELL_HTML, { headers: { 'Content-Type': 'text/html' } }))))
      .then(() => self.skipWaiting())
  );
});

// Activate - Clean all old versioned caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => !key.endsWith(`-${CACHE_VERSION}`))
            .map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch - Route to appropriate strategy
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip non-http(s)
  if (!url.protocol.startsWith('http')) return;

  // Determine strategy based on path
  let strategy;
  if (url.pathname.startsWith('/static/') ||
      url.pathname === '/manifest.json' ||
      url.hostname === 'fonts.googleapis.com' ||
      url.hostname === 'fonts.gstatic.com' ||
      url.hostname === 'cdnjs.cloudflare.com' ||
      url.hostname === 'cdn.jsdelivr.net') {
    strategy = CACHE_STRATEGIES.static;
  } else if (url.pathname.startsWith('/api/') ||
             url.pathname.startsWith('/export/') ||
             url.pathname.includes('/monitoring/notifications/count')) {
    strategy = CACHE_STRATEGIES.api;
  } else {
    strategy = CACHE_STRATEGIES.page;
  }

  event.respondWith(strategy(request));
});

// Background Sync for offline actions
self.addEventListener('sync', event => {
  if (event.tag === 'sync-transactions') {
    event.waitUntil(syncTransactions());
  }
});

async function syncTransactions() {
  console.log('Syncing offline transactions...');
}

// Push notifications
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  const options = {
    body: data.message,
    icon: '/static/img/icon-192.png',
    badge: '/static/img/icon-72.png',
    vibrate: [200, 100, 200],
    data: data.url || '/dashboard',
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'dismiss', title: 'Dismiss' }
    ]
  };
  event.waitUntil(
    self.registration.showNotification(data.title || 'MyLedger', options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.openWindow(event.notification.data || '/dashboard')
    );
  }
});

// Message from client
self.addEventListener('message', event => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }
});
