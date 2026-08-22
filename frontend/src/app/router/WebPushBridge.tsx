/**
 * Mounts browser push for the whole application.
 *
 * A component rather than a call inside `Router` because `useWebPush`
 * navigates, and hooks that navigate must live under `BrowserRouter`. It
 * renders nothing: everything it does is registration and event subscription.
 *
 * One instance, mounted once. Push registration and the foreground-message
 * subscription are process-wide concerns, and mounting this per page would
 * re-subscribe on every navigation.
 */

import { useWebPush } from "../../hooks/useWebPush";

export const WebPushBridge = () => {
  useWebPush();
  return null;
};
