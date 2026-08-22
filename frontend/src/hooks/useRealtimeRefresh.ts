/**
 * Subscribe a page's existing reload function to realtime events.
 *
 * The whole integration surface for a feature is one line:
 *
 *     useRealtimeRefresh(["MESSAGE_CREATED"], loadMessages);
 *
 * The page keeps owning its data. This hook only decides *when* to call the
 * function the page already had, which is why adopting realtime needs no state
 * refactor and no migration to a caching library.
 *
 * `REALTIME_RECONNECTED` is added to every subscription automatically. That is
 * how missed events are recovered: rather than replaying a log, the client
 * refetches on every (re)connect. A refetch is idempotent, so a reconnect can
 * never duplicate a message or leave a half-applied change — which a partial
 * replay very much could.
 */

import { useEffect, useRef } from "react";

import { useRealtime } from "../app/providers/RealtimeProvider";
import { RECONNECTED, type RealtimeEvent } from "../services/realtime/eventStream";

interface Options {
  /**
   * Only react to events for this project. Omit to accept any project.
   *
   * Purely a client-side narrowing for relevance — the server has already
   * decided what this user may receive. It stops a task board for project A
   * refetching because something moved in project B.
   */
  projectId?: string;
  /** Ignore reconnect-triggered refreshes. Rarely wanted; see the note above. */
  skipOnReconnect?: boolean;
  /**
   * Collapse bursts. A status change can produce several events in quick
   * succession, and refetching once per event would hammer the API for a
   * single visible outcome.
   */
  debounceMs?: number;
}

export const useRealtimeRefresh = (
  eventTypes: readonly string[],
  onChange: (event: RealtimeEvent) => void | Promise<void>,
  options: Options = {},
): void => {
  const realtime = useRealtime();
  const { projectId, skipOnReconnect = false, debounceMs = 250 } = options;

  // Kept in refs so a caller passing an inline arrow does not re-subscribe on
  // every render — the common case, and one that would otherwise churn the
  // subscription set continuously.
  const handlerRef = useRef(onChange);
  handlerRef.current = onChange;

  const typesRef = useRef<readonly string[]>(eventTypes);
  typesRef.current = eventTypes;

  useEffect(() => {
    if (!realtime) return;

    let timer: number | null = null;
    let pending: RealtimeEvent | null = null;

    const flush = () => {
      timer = null;
      const event = pending;
      pending = null;
      if (event) void handlerRef.current(event);
    };

    const unsubscribe = realtime.subscribe((event) => {
      const isReconnect = event.type === RECONNECTED;
      if (isReconnect && skipOnReconnect) return;
      if (!isReconnect && !typesRef.current.includes(event.type)) return;
      // A reconnect is not project-specific: it means "you may have missed
      // things", so it must reach every subscriber regardless of scope.
      if (!isReconnect && projectId && event.projectId && event.projectId !== projectId) return;

      pending = event;
      if (timer === null) timer = window.setTimeout(flush, debounceMs);
    });

    return () => {
      unsubscribe();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [realtime, projectId, skipOnReconnect, debounceMs]);
};
