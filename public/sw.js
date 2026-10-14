// Ele-in Background Service Worker for Native OS Desktop Notifications & WebPush
/* eslint-disable no-restricted-globals */

self.addEventListener('install', () => {
  // Activate immediately without waiting for existing instances to terminate
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Immediately take control of all active clients and tabs in the workspace
  event.waitUntil(self.clients.claim());
});

// Handle background Web Push events (when browser tabs are inactive or closed)
self.addEventListener('push', (event) => {
  let payload = {
    title: 'New Lead Reply',
    body: 'A prospect has responded to your outreach.',
    url: '/elein/inbox',
    tag: 'elein-lead-notification',
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      payload = { ...payload, ...parsed };
    } catch {
      payload.body = event.data.text() || payload.body;
    }
  }

  const notificationOptions = {
    body: payload.body,
    icon: '/logo-icon.png',
    badge: '/logo-icon.png',
    tag: payload.tag || 'elein-notification',
    data: {
      url: payload.url || '/elein/inbox',
      timestamp: Date.now(),
    },
    renotify: true,
  };

  event.waitUntil(
    self.registration.showNotification(payload.title, notificationOptions)
  );
});

// Handle notification click: Focus existing active client or open new window to target URL
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = event.notification.data?.url || '/elein/inbox';

  event.waitUntil(
    self.clients
      .matchAll({
        type: 'window',
        includeUncontrolled: true,
      })
      .then((clientList) => {
        // If an Ele-in tab is already open, focus it and navigate
        for (const client of clientList) {
          if ('focus' in client) {
            client.focus();
            if ('navigate' in client && targetUrl) {
              return client.navigate(targetUrl);
            }
            return client;
          }
        }
        // If no tab is open, open a new window
        if (self.clients.openWindow) {
          return self.clients.openWindow(targetUrl);
        }
      })
  );
});
