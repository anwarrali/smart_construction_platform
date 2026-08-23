/* Firebase Cloud Messaging service worker.
 *
 * This file is what makes browser notifications work when the tab is closed.
 * It runs in its own worker context with no access to the React app, no
 * bundler, and no import.meta.env — which is why it uses the compat scripts
 * from the CDN and reads its configuration from the query string that
 * `registerServiceWorker()` appends (see src/services/push/webPush.ts).
 *
 * **The SDK version here must match the one the page uses** (`firebase` in
 * package.json). Both sides open the same IndexedDB database,
 * `firebase-messaging-database`, and they open it at a version that changes
 * between majors — v10 asks for 1, v12 asks for 2. A mismatched pair produces
 * `VersionError: The requested version (1) is less than the existing version
 * (2)` and leaves the worker unable to read its own token store.
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

importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.18.0/firebase-messaging-compat.js");

/** Configuration passed by the page at registration time. */
const params = new URL(self.location).searchParams;
const firebaseConfig = {
  apiKey: params.get("apiKey"),
  authDomain: params.get("authDomain"),
  projectId: params.get("projectId"),
  messagingSenderId: params.get("messagingSenderId"),
  appId: params.get("appId"),
};

/** Where to send the user when the payload names no specific destination. */
const FALLBACK_PATH = "/notifications";

/** PNG, not SVG: Chrome does not render SVG notification icons on Windows. */
const NOTIFICATION_ICON = "/notification-icon.png";

if (firebaseConfig.projectId && firebaseConfig.messagingSenderId) {
  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();

  /* Background messages: the tab is closed, or in another window.
   *
   * Only *data-only* messages need handling here — when the server includes a
   * `notification` block the SDK displays it itself, and calling
   * showNotification again would produce two identical toasts. The backend
   * does send a notification block, so this is the safety net for a data-only
   * send rather than the normal path. */
  messaging.onBackgroundMessage((payload) => {
    if (payload.notification) return;
    const data = payload.data || {};
    self.registration.showNotification(data.title || "Struct IQ", {
      body: data.body || "",
      icon: NOTIFICATION_ICON,
      // Collapses repeats of the same subject into one entry, matching the
      // collapse_key the server sends for mobile.
      tag: data.collapseKey || data.notificationId || undefined,
      data,
    });
  });
}

/**
 * Read our routing payload out of a notification, whichever way it was shown.
 *
 * The two display paths nest the data differently, and assuming one shape is
 * how notification clicks silently stopped opening the right page:
 *
 *   • The Firebase SDK wraps the whole message and stores it under a single
 *     `FCM_MSG` key, so our fields live at `data.FCM_MSG.data`.
 *   • A notification shown by `onBackgroundMessage` above passes our flat
 *     object straight through, so the fields are at the top level.
 *
 * Reading only the flat shape meant every SDK-displayed notification fell back
 * to the notification centre instead of opening the task, issue or message it
 * was about.
 */
const routingData = (notification) => {
  const raw = (notification && notification.data) || {};
  const wrapped = raw.FCM_MSG && raw.FCM_MSG.data;
  return wrapped || raw;
};

/* Clicking a notification.
 *
 * Focus an existing tab rather than opening a new one where possible: a site
 * engineer who already has the project open does not want a second window,
 * and an already-open tab keeps its session and unsaved state. */
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const data = routingData(event.notification);
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
