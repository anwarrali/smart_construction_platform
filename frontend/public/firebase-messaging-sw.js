/* Firebase Cloud Messaging service worker.
 *
 * This file is what makes browser notifications work when the tab is closed.
 * It runs in its own worker context with no access to the React app, no
 * bundler, and no import.meta.env — which is why it uses the compat scripts
 * from the CDN and reads its configuration from the query string that
 * `registerServiceWorker()` appends (see src/services/push/webPush.ts).
 *
 * Nothing secret lives here. A Firebase web config (apiKey, senderId, appId)
 * is a public client identifier, not a credential: it identifies the project
 * to Google and grants nothing on its own. The service account that can
 * actually *send* notifications stays on the server and never reaches a
 * browser.
 *
 * Kept in `public/` deliberately. A service worker may only control pages at
 * or below its own path, so it must be served from the site root — a hashed
 * bundle under /assets/ could not.
 */

importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js");

/** Configuration passed by the page at registration time. */
const params = new URL(self.location).searchParams;
const firebaseConfig = {
  apiKey: params.get("apiKey"),
  authDomain: params.get("authDomain"),
  projectId: params.get("projectId"),
  messagingSenderId: params.get("messagingSenderId"),
  appId: params.get("appId"),
};

/** Where to send the user when there is no better destination. */
const FALLBACK_PATH = "/notifications";

if (firebaseConfig.projectId && firebaseConfig.messagingSenderId) {
  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();

  /* Background messages: the tab is closed, or in another window.
   *
   * Only *data-only* messages reach this handler — when the server includes a
   * `notification` block, the browser displays it itself and calling
   * showNotification here as well would produce two identical toasts. The
   * backend does send a notification block, so this handler is the safety net
   * for a data-only send rather than the normal path. */
  messaging.onBackgroundMessage((payload) => {
    if (payload.notification) return;
    const data = payload.data || {};
    self.registration.showNotification(data.title || "Struct IQ", {
      body: data.body || "",
      icon: "/favicon.svg",
      // Collapses repeats of the same subject into one entry, matching the
      // collapse_key the server sends for mobile.
      tag: data.collapseKey || data.notificationId || undefined,
      data,
    });
  });
}

/* Clicking a notification.
 *
 * Focus an existing tab rather than opening a new one where possible: a site
 * engineer who already has the project open does not want a second window,
 * and an already-open tab keeps its session and unsaved state. */
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const data = event.notification.data || {};
  const path = data.clickPath || data.click_path || FALLBACK_PATH;
  const target = new URL(path, self.location.origin).href;

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url.startsWith(self.location.origin) && "focus" in client) {
            // Tell the app where to go instead of navigating the worker: the
            // React router owns role-aware routing, and a hard navigation
            // would reload the whole application.
            client.postMessage({ type: "NOTIFICATION_CLICK", data });
            return client.focus();
          }
        }
        return self.clients.openWindow(target);
      }),
  );
});
