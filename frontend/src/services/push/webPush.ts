/**
 * Browser push, through the same FCM project the mobile app uses.
 *
 * The design rule from the backend holds here too: this module obtains a
 * delivery address and hands it to the server. It contains no notification
 * business logic — no decision about who is notified, what a notification
 * means, or where it should lead. Routing is resolved by `useNotifications`,
 * which already maps a notification's entity onto a role-aware path.
 *
 * Everything degrades. A browser without service workers, a user who denies
 * permission, a deployment with no Firebase configuration — each returns a
 * reason instead of throwing, because in every one of those cases the
 * notification centre still works and the user should notice nothing broken.
 */

import { deleteToken, getMessaging, getToken, isSupported, onMessage } from "firebase/messaging";
import { initializeApp, type FirebaseApp } from "firebase/app";
import type { Messaging, MessagePayload } from "firebase/messaging";

/** Why push is unavailable, when it is. Surfaced in settings, never as an error. */
export type PushUnavailableReason =
  | "not-configured"
  | "unsupported"
  | "permission-denied"
  | "permission-dismissed"
  | "registration-failed";

export type PushSetupResult =
  | { ok: true; token: string }
  | { ok: false; reason: PushUnavailableReason; detail?: string };

/**
 * The Firebase web configuration.
 *
 * These are public client identifiers, not secrets — they identify the
 * project to Google and grant nothing on their own. They still come from the
 * environment rather than being written here, so that a staging build points
 * at a staging Firebase project without a code change.
 */
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/** The public half of the VAPID key pair, from Firebase Console → Web Push certificates. */
const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY;

export const isPushConfigured = () =>
  Boolean(firebaseConfig.projectId && firebaseConfig.messagingSenderId && vapidKey);

/**
 * Which build-time values are absent, by name.
 *
 * Names only — never values. Enough to diagnose a misconfigured build without
 * printing configuration into a console that ends up in screenshots.
 *
 * Vite inlines `import.meta.env.*` at build time, so an empty result here means
 * the values were missing when the bundle was compiled, not when it ran. In
 * Docker that means the build args in `frontend/Dockerfile`.
 */
export const missingPushConfigKeys = (): string[] =>
  [
    ["VITE_FIREBASE_PROJECT_ID", firebaseConfig.projectId],
    ["VITE_FIREBASE_MESSAGING_SENDER_ID", firebaseConfig.messagingSenderId],
    ["VITE_FIREBASE_API_KEY", firebaseConfig.apiKey],
    ["VITE_FIREBASE_APP_ID", firebaseConfig.appId],
    ["VITE_FIREBASE_VAPID_KEY", vapidKey],
  ]
    .filter(([, value]) => !value)
    .map(([name]) => name as string);

let app: FirebaseApp | null = null;
let messaging: Messaging | null = null;

const getMessagingInstance = async (): Promise<Messaging | null> => {
  if (!isPushConfigured()) return null;
  if (!(await isSupported())) return null;
  if (!app) app = initializeApp(firebaseConfig);
  if (!messaging) messaging = getMessaging(app);
  return messaging;
};

/**
 * A stable identifier for this browser installation.
 *
 * The server uses it to retire this browser's *previous* token when Firebase
 * rotates one, so a long-lived profile does not accumulate dead registrations.
 * localStorage rather than sessionStorage: it must survive a tab close, and it
 * identifies the browser, not the person — it is generated locally, contains
 * nothing about the user, and is replaced if cleared.
 */
const DEVICE_ID_KEY = "scp_push_device_id";

export const getDeviceId = (): string => {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
};

/** A human-readable device label for the user's own device list. */
export const getDeviceName = (): string => {
  const agent = navigator.userAgent;
  const browser =
    /Edg\//.test(agent) ? "Edge"
    : /OPR\//.test(agent) ? "Opera"
    : /Chrome\//.test(agent) ? "Chrome"
    : /Safari\//.test(agent) ? "Safari"
    : /Firefox\//.test(agent) ? "Firefox"
    : "Browser";
  const platform =
    /Windows/.test(agent) ? "Windows"
    : /Android/.test(agent) ? "Android"
    : /iPhone|iPad/.test(agent) ? "iOS"
    : /Mac OS X/.test(agent) ? "macOS"
    : /Linux/.test(agent) ? "Linux"
    : "";
  return platform ? `${browser} on ${platform}` : browser;
};

/**
 * Register the service worker, passing the Firebase config in the query string.
 *
 * The worker cannot read the bundler's environment, and hardcoding the config
 * into a file in `public/` would mean editing a checked-in file per
 * environment. The query string is the documented way to configure it.
 */
const registerServiceWorker = async (): Promise<ServiceWorkerRegistration> => {
  const params = new URLSearchParams({
    apiKey: firebaseConfig.apiKey ?? "",
    authDomain: firebaseConfig.authDomain ?? "",
    projectId: firebaseConfig.projectId ?? "",
    messagingSenderId: firebaseConfig.messagingSenderId ?? "",
    appId: firebaseConfig.appId ?? "",
  });
  return navigator.serviceWorker.register(`/firebase-messaging-sw.js?${params.toString()}`, {
    scope: "/",
  });
};

/**
 * Ask for permission and obtain a push token.
 *
 * Permission is requested only when this is called, and callers only call it
 * after the user is signed in — a permission prompt on a login screen is the
 * fastest way to get permanently denied, and a denial cannot be undone from
 * script.
 */
export const setupWebPush = async (): Promise<PushSetupResult> => {
  if (!isPushConfigured()) return { ok: false, reason: "not-configured" };
  if (!("Notification" in window) || !("serviceWorker" in navigator)) {
    return { ok: false, reason: "unsupported" };
  }

  const instance = await getMessagingInstance();
  if (!instance) return { ok: false, reason: "unsupported" };

  const permission =
    Notification.permission === "default"
      ? await Notification.requestPermission()
      : Notification.permission;

  if (permission === "denied") return { ok: false, reason: "permission-denied" };
  if (permission !== "granted") return { ok: false, reason: "permission-dismissed" };

  try {
    const serviceWorkerRegistration = await registerServiceWorker();
    const token = await getToken(instance, { vapidKey, serviceWorkerRegistration });
    if (!token) return { ok: false, reason: "registration-failed" };
    return { ok: true, token };
  } catch (error) {
    return {
      ok: false,
      reason: "registration-failed",
      detail: error instanceof Error ? error.message : String(error),
    };
  }
};

/**
 * Foreground messages — the tab is open and focused.
 *
 * FCM does not show these itself; that is by design, because an app that is
 * already on screen should update its own UI rather than raise an OS toast
 * over itself. The caller refreshes the bell and shows an in-app toast.
 */
export const onForegroundMessage = (handler: (payload: MessagePayload) => void) => {
  let unsubscribe: (() => void) | undefined;
  let cancelled = false;

  void getMessagingInstance().then((instance) => {
    if (!instance || cancelled) return;
    unsubscribe = onMessage(instance, handler);
  });

  return () => {
    cancelled = true;
    unsubscribe?.();
  };
};

/**
 * Messages posted by the service worker when a notification is clicked.
 *
 * The worker focuses the existing tab and hands the payload over rather than
 * navigating itself, so the React router — which knows the user's role — is
 * the one that decides where to go.
 */
export const onNotificationClick = (handler: (data: Record<string, string>) => void) => {
  if (!("serviceWorker" in navigator)) return () => {};
  const listener = (event: MessageEvent) => {
    if (event.data?.type === "NOTIFICATION_CLICK") handler(event.data.data || {});
  };
  navigator.serviceWorker.addEventListener("message", listener);
  return () => navigator.serviceWorker.removeEventListener("message", listener);
};

/**
 * Drop this browser's token on sign-out.
 *
 * Without it, a shared machine keeps delivering the previous user's
 * notifications to whoever signs in next. Failure is ignored on purpose: the
 * server-side unregistration is the authoritative half, and a sign-out must
 * never be blocked by Firebase being unreachable.
 */
export const teardownWebPush = async (): Promise<void> => {
  try {
    const instance = await getMessagingInstance();
    if (instance) await deleteToken(instance);
  } catch {
    /* ignored: see above */
  }
};
