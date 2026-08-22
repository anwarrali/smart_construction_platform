/**
 * Owns the application's single SSE connection.
 *
 * Mounted once, above the router. It starts the stream when a session exists
 * and stops it when the session ends — so a signed-out browser holds no open
 * connection, and the next user's stream is opened with their own ticket
 * rather than inheriting the previous one.
 *
 * The provider deliberately knows nothing about tasks, messages or
 * notifications. It exposes "an event arrived" and "the transport is in this
 * state"; deciding what to refetch belongs to the features, via
 * `useRealtimeRefresh`.
 */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  eventStream,
  type RealtimeEvent,
  type RealtimeState,
} from "../../services/realtime/eventStream";
import { useAuthStore } from "../store/auth.store";

interface RealtimeContextValue {
  /** The real transport state — never a guess. */
  state: RealtimeState;
  /** True only while a stream is actually open. */
  isConnected: boolean;
  /** Subscribe to every event. Returns an unsubscribe function. */
  subscribe: (handler: (event: RealtimeEvent) => void) => () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export const RealtimeProvider = ({ children }: { children: ReactNode }) => {
  const isAuthenticated = useAuthStore((store) => store.isAuthenticated);
  const [state, setState] = useState<RealtimeState>(() => eventStream.getState());

  // Subscribers registered before the first connection must survive reconnects,
  // so they attach to the module-level stream rather than to a connection.
  const subscribersRef = useRef(
    new Set<(event: RealtimeEvent) => void>(),
  );

  useEffect(() => eventStream.onState(setState), []);

  useEffect(() => {
    if (!isAuthenticated) {
      // Signing out must close the stream: the ticket was minted for the
      // previous user, and a shared machine must not leave it open.
      eventStream.stop();
      return;
    }
    eventStream.start();
    // Not stopped on unmount while still authenticated — React's strict-mode
    // double-mount would otherwise tear down a healthy connection and force a
    // needless reconnect on every development reload.
  }, [isAuthenticated]);

  useEffect(() => {
    const subscribers = subscribersRef.current;
    return eventStream.onEvent((event) => {
      subscribers.forEach((handler) => {
        try {
          handler(event);
        } catch {
          /* one failing subscriber must not silence the rest */
        }
      });
    });
  }, []);

  const value = useMemo<RealtimeContextValue>(
    () => ({
      state,
      isConnected: state === "connected",
      subscribe: (handler) => {
        subscribersRef.current.add(handler);
        return () => {
          subscribersRef.current.delete(handler);
        };
      },
    }),
    [state],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};

/**
 * Access the realtime context.
 *
 * Returns null rather than throwing when no provider is mounted, so a
 * component can be rendered in a test or a narrow tree without one. Realtime
 * is an enhancement: its absence must never break a screen.
 */
export const useRealtime = (): RealtimeContextValue | null => useContext(RealtimeContext);
