/**
 * Wires browser push into the notification centre that already exists.
 *
 * Three jobs, and deliberately no fourth:
 *
 *   1. register this browser as a delivery address once the user is signed in;
 *   2. refresh the bell when a push arrives while the tab is open;
 *   3. navigate when a notification is clicked.
 *
 * It does not decide who gets notified, what a notification says, or when one
 * is created — all of that is the backend's, and duplicating any of it here
 * would give the web app its own divergent notion of a notification.
 *
 * Deliberately quiet about failure. Push is an enhancement: a browser that
 * cannot receive it still shows every notification in the bell, and telling
 * the user their browser is deficient on every sign-in would be noise. The
 * reason is returned instead, for a settings screen to show if it wants it.
 *
 * `.tsx` rather than `.ts` because the foreground toast renders a clickable
 * element — a notification you cannot click is only half of one.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";

import api from "../services/api";
import {
  getDeviceId,
  getDeviceName,
  isPushConfigured,
  missingPushConfigKeys,
  onForegroundMessage,
  onNotificationClick,
  setupWebPush,
  teardownWebPush,
  type PushUnavailableReason,
} from "../services/push/webPush";
import { useAuthStore } from "../app/store/auth.store";
import { useNotificationStore } from "../app/store/notification.store";
import { useRole } from "./useRole";
import { projectEntityPath, projectModulePath } from "../utils/projectRoutes";
import { ROUTES } from "../utils/constants";

export type WebPushStatus =
  | { state: "idle" }
  | { state: "registering" }
  | { state: "registered" }
  | { state: "unavailable"; reason: PushUnavailableReason };

export const useWebPush = () => {
  const navigate = useNavigate();
  const { hasCapability } = useRole();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const setUnreadCount = useNotificationStore((state) => state.setUnreadCount);
  const [status, setStatus] = useState<WebPushStatus>({ state: "idle" });

  // Registration must happen once per sign-in — not once per render, and not
  // again on every navigation. Firebase returns the same token each time, so
  // the repeat is harmless but wasteful, and the ref also absorbs React's
  // strict-mode double invocation in development.
  const registeredRef = useRef(false);

  /**
   * Where a notification payload should take the user.
   *
   * Reuses `projectEntityPath` — the same mapping the notification list uses —
   * so a push and a click in the bell land in exactly the same place, for the
   * same role. A project-scoped notification always resolves inside the
   * project workspace; only one with no project at all falls back to the
   * notification centre.
   */
  const resolvePath = useCallback(
    (data: Record<string, string>) => {
      const projectId = data.projectId;
      const entityType = data.entityType || (data.taskId ? "TASK" : undefined);
      const entityId = data.entityId || data.taskId;
      if (!projectId) return ROUTES.NOTIFICATIONS;
      return entityType
        ? projectEntityPath(projectId, entityType, entityId || "", hasCapability)
        : projectModulePath(projectId, "activity", hasCapability);
    },
    [hasCapability],
  );

  const refreshUnreadCount = useCallback(async () => {
    try {
      const { count } = await api.notifications.getUnreadCount();
      setUnreadCount(count);
    } catch {
      /* the bell keeps its previous value; a failed refresh is not worth a toast */
    }
  }, [setUnreadCount]);

  /** Register this browser once the user is signed in. */
  useEffect(() => {
    if (!isAuthenticated || registeredRef.current) return;
    if (!isPushConfigured()) {
      // Say so once, rather than failing silently. "Not configured" and
      // "working fine" previously looked identical from the outside: no
      // prompt, no request, no error — which is indistinguishable from a bug
      // and cost a full debugging session to tell apart. The backend logs its
      // equivalent line at boot; this is the frontend's.
      //
      // Names which values are missing, never their contents. They are public
      // client identifiers, but printing config into a console that ends up in
      // screenshots and bug reports is a habit worth not forming.
      console.info(
        "[push] Web push is not configured, so no permission will be requested. " +
          `Missing build-time values: ${missingPushConfigKeys().join(", ")}. ` +
          "These are Vite build args — see frontend/Dockerfile and docs/NOTIFICATIONS.md.",
      );
      setStatus({ state: "unavailable", reason: "not-configured" });
      return;
    }

    let cancelled = false;
    registeredRef.current = true;
    setStatus({ state: "registering" });

    void (async () => {
      const result = await setupWebPush();
      if (cancelled) return;
      if (!result.ok) {
        // Allow a retry on the next sign-in: someone who dismissed the prompt
        // today may well accept it tomorrow.
        registeredRef.current = false;
        setStatus({ state: "unavailable", reason: result.reason });
        return;
      }
      try {
        await api.notifications.registerDevice({
          token: result.token,
          platform: "web",
          deviceId: getDeviceId(),
          deviceName: getDeviceName(),
        });
        if (!cancelled) setStatus({ state: "registered" });
      } catch {
        registeredRef.current = false;
        if (!cancelled) setStatus({ state: "unavailable", reason: "registration-failed" });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  /** Sign-out clears the guard so the next user registers their own token. */
  useEffect(() => {
    if (isAuthenticated) return;
    registeredRef.current = false;
    setStatus({ state: "idle" });
  }, [isAuthenticated]);

  /** A push arriving while the tab is open: update the bell, offer the link. */
  useEffect(() => {
    if (!isAuthenticated) return;
    return onForegroundMessage((payload) => {
      void refreshUnreadCount();
      const data = (payload.data || {}) as Record<string, string>;
      const title = payload.notification?.title || data.title;
      const body = payload.notification?.body || data.body;
      if (!title) return;
      toast(
        (instance) => (
          <button
            type="button"
            className="text-start"
            onClick={() => {
              toast.dismiss(instance.id);
              navigate(resolvePath(data));
            }}
          >
            <span className="block text-sm font-semibold">{title}</span>
            {body ? <span className="block text-xs text-muted-foreground">{body}</span> : null}
          </button>
        ),
        { duration: 6000, ariaProps: { role: "status", "aria-live": "polite" } },
      );
    });
  }, [isAuthenticated, navigate, refreshUnreadCount, resolvePath]);

  /** A click on a background notification, forwarded by the service worker. */
  useEffect(() => {
    if (!isAuthenticated) return;
    return onNotificationClick((data) => {
      void refreshUnreadCount();
      navigate(resolvePath(data));
    });
  }, [isAuthenticated, navigate, refreshUnreadCount, resolvePath]);

  /**
   * Called on sign-out, so a shared machine stops delivering the previous
   * user's notifications to whoever signs in next.
   */
  const unregister = useCallback(async () => {
    try {
      await api.notifications.unregisterDevice({ deviceId: getDeviceId() });
    } catch {
      /* the server may already have retired it; sign-out must not be blocked */
    }
    await teardownWebPush();
    registeredRef.current = false;
  }, []);

  return { status, unregister };
};
