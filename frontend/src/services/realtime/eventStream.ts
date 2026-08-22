/**
 * The single SSE connection for the signed-in session.
 *
 * One connection for the whole application, not one per component. Browsers
 * cap concurrent connections per origin (six on HTTP/1.1), and a stream per
 * feature would exhaust that budget and starve ordinary REST calls.
 *
 * **Why this does not rely on EventSource's native reconnect.** `EventSource`
 * retries the *same URL*, and our URL carries a ticket that expires in about a
 * minute. After that, every native retry is a guaranteed 401 — a silent
 * infinite loop that looks exactly like a broken server. So an error closes
 * the stream deliberately and reconnects with a freshly minted ticket. We keep
 * the parts of `EventSource` that are genuinely useful (framing, parsing,
 * `Last-Event-ID`) and replace only the retry policy, which cannot work with
 * short-lived credentials.
 *
 * Events are hints. This module never interprets one; it forwards them to
 * subscribers, which refetch through the existing REST API.
 */

import api from "../api";

export type RealtimeState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline";

/** The envelope, exactly as the server sends it. Identifiers only. */
export interface RealtimeEvent {
  id: string;
  type: string;
  ts: string;
  projectId?: string;
  userId?: string;
  entityType?: string;
  entityId?: string;
}

/** Emitted locally on every (re)connect so subscribers can resynchronise. */
export const RECONNECTED = "REALTIME_RECONNECTED";

type EventHandler = (event: RealtimeEvent) => void;
type StateHandler = (state: RealtimeState) => void;

const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;
/** ±30% so a fleet of tabs does not stampede a restarting backend in lockstep. */
const JITTER = 0.3;

/** Server event names we translate into frames; anything else is forwarded raw. */
const HANDSHAKE_EVENT = "connected";

class EventStream {
  private source: EventSource | null = null;
  private state: RealtimeState = "idle";
  private attempts = 0;
  private reconnectTimer: number | null = null;
  private stopped = true;

  private readonly eventHandlers = new Set<EventHandler>();
  private readonly stateHandlers = new Set<StateHandler>();

  // --- public surface ----------------------------------------------------

  getState(): RealtimeState {
    return this.state;
  }

  onEvent(handler: EventHandler): () => void {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  onState(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    handler(this.state);
    return () => this.stateHandlers.delete(handler);
  }

  /** Open the stream. Safe to call repeatedly; only the first call connects. */
  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempts = 0;
    window.addEventListener("online", this.handleOnline);
    window.addEventListener("offline", this.handleOffline);
    void this.connect();
  }

  /** Close for good — on sign-out, or when the provider unmounts. */
  stop(): void {
    this.stopped = true;
    window.removeEventListener("online", this.handleOnline);
    window.removeEventListener("offline", this.handleOffline);
    this.clearTimer();
    this.closeSource();
    this.setState("idle");
  }

  // --- connection --------------------------------------------------------

  private async connect(): Promise<void> {
    if (this.stopped) return;
    this.closeSource();
    this.setState(this.attempts === 0 ? "connecting" : "reconnecting");

    let ticket: string;
    try {
      // A fresh ticket every time. They are single-purpose and short-lived by
      // design, so reusing one across reconnects is exactly what fails.
      ticket = (await api.realtime.ticket()).ticket;
    } catch {
      // Usually the session has ended or the backend is down. Either way the
      // right move is to back off and try again rather than spin.
      this.scheduleReconnect();
      return;
    }
    if (this.stopped) return;

    const url = `${realtimeBaseUrl()}/events/stream?ticket=${encodeURIComponent(ticket)}`;
    const source = new EventSource(url);
    this.source = source;

    source.addEventListener(HANDSHAKE_EVENT, () => {
      this.attempts = 0;
      this.setState("connected");
      // Tell subscribers to resynchronise. This is what recovers anything
      // that happened while the connection was down — no replay log, just a
      // refetch of whatever is on screen, which is idempotent by construction.
      this.emit({
        id: `reconnect-${Date.now()}`,
        type: RECONNECTED,
        ts: new Date().toISOString(),
      });
    });

    // A named-event listener only fires for that name, so every server event
    // type needs its own registration. `onmessage` would catch only unnamed
    // frames, which we never send.
    source.onmessage = (message) => this.forward(message.data);
    KNOWN_EVENT_TYPES.forEach((type) => {
      source.addEventListener(type, (message) =>
        this.forward((message as MessageEvent).data),
      );
    });

    source.onerror = () => {
      // EventSource does not tell us why. It may be a dead network, a restarted
      // backend, or an expired ticket — and the response to all three is the
      // same: close, back off, reconnect with new credentials.
      if (this.stopped) return;
      this.closeSource();
      this.scheduleReconnect();
    };
  }

  private forward(raw: string): void {
    try {
      const event = JSON.parse(raw) as RealtimeEvent;
      if (event?.type) this.emit(event);
    } catch {
      /* a frame we cannot parse is dropped; the next refetch corrects state */
    }
  }

  private emit(event: RealtimeEvent): void {
    this.eventHandlers.forEach((handler) => {
      try {
        handler(event);
      } catch {
        /* one bad subscriber must not stop the others from being told */
      }
    });
  }

  private scheduleReconnect(): void {
    if (this.stopped || this.reconnectTimer !== null) return;

    // The browser says the network is gone: report it honestly and wait for
    // the `online` event rather than burning retries that cannot succeed.
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      this.setState("offline");
      return;
    }

    this.setState("reconnecting");
    const exponential = Math.min(BASE_DELAY_MS * 2 ** this.attempts, MAX_DELAY_MS);
    const jitter = exponential * JITTER * (Math.random() * 2 - 1);
    const delay = Math.max(BASE_DELAY_MS, Math.round(exponential + jitter));
    this.attempts += 1;

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      void this.connect();
    }, delay);
  }

  private handleOnline = (): void => {
    if (this.stopped) return;
    // Back immediately rather than waiting out a backoff that was scheduled
    // while the network was down.
    this.clearTimer();
    this.attempts = 0;
    void this.connect();
  };

  private handleOffline = (): void => {
    if (this.stopped) return;
    this.clearTimer();
    this.closeSource();
    this.setState("offline");
  };

  private clearTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private closeSource(): void {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
  }

  private setState(state: RealtimeState): void {
    if (this.state === state) return;
    this.state = state;
    this.stateHandlers.forEach((handler) => {
      try {
        handler(state);
      } catch {
        /* ignored */
      }
    });
  }
}

/**
 * Event names the server can send.
 *
 * Registered explicitly because `EventSource` dispatches named events only to
 * listeners for that name. A name missing here is silently never delivered —
 * so adding a server event type means adding it here too.
 */
export const KNOWN_EVENT_TYPES = [
  "NOTIFICATION_CREATED",
  "NOTIFICATION_UPDATED",
  "MESSAGE_CREATED",
  "MESSAGE_UPDATED",
  "TASK_CREATED",
  "TASK_UPDATED",
  "ISSUE_CREATED",
  "ISSUE_UPDATED",
] as const;

/**
 * Where the stream lives.
 *
 * `EventSource` cannot go through the axios instance, so the base URL is
 * derived from the same setting axios uses rather than configured twice.
 */
const realtimeBaseUrl = (): string =>
  (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/+$/, "");

/** The one instance for the application. */
export const eventStream = new EventStream();
