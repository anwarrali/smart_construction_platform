// @vitest-environment jsdom
/**
 * The SSE transport: connection lifecycle, reconnection, and cleanup.
 *
 * `EventSource` does not exist in jsdom, so it is replaced with a fake that
 * records every instance. That is what lets us assert the property most likely
 * to regress in a hurry: **exactly one connection per session**. A stream
 * opened per component would exhaust the browser's per-origin connection
 * budget and starve ordinary REST calls, and nothing in the UI would look
 * wrong until it did.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ticketMock = vi.fn();
vi.mock("../api", () => ({
  default: { realtime: { ticket: ticketMock } },
}));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static get openCount() {
    return FakeEventSource.instances.filter((instance) => !instance.closed).length;
  }

  url: string;
  closed = false;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  private listeners = new Map<string, ((event: MessageEvent) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: MessageEvent) => void) {
    const existing = this.listeners.get(type) || [];
    existing.push(handler);
    this.listeners.set(type, existing);
  }

  close() {
    this.closed = true;
  }

  /** Drive the fake from a test. */
  emit(type: string, data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent;
    (this.listeners.get(type) || []).forEach((handler) => handler(event));
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);

// Imported after the stub so the module closes over the fake.
const { eventStream, RECONNECTED } = await import("./eventStream");

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

/** jsdom's navigator is read-only; redefine just the one property. */
const setOnLine = (value: boolean) =>
  Object.defineProperty(window.navigator, "onLine", {
    value,
    configurable: true,
  });

describe("event stream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    ticketMock.mockReset();
    ticketMock.mockResolvedValue({ ticket: "test-ticket", expiresInSeconds: 60 });
    setOnLine(true);
  });

  afterEach(() => {
    eventStream.stop();
    vi.useRealTimers();
  });

  it("opens exactly one connection for the session", async () => {
    eventStream.start();
    eventStream.start(); // repeated calls must be harmless
    eventStream.start();
    await flush();

    expect(FakeEventSource.openCount).toBe(1);
    expect(ticketMock).toHaveBeenCalledTimes(1);
  });

  it("authenticates with a ticket rather than the access token", async () => {
    eventStream.start();
    await flush();

    const url = FakeEventSource.instances[0].url;
    expect(url).toContain("/events/stream?ticket=test-ticket");
  });

  it("reports connected only once the server acknowledges", async () => {
    eventStream.start();
    await flush();
    // Socket constructed, but the handshake frame has not arrived.
    expect(eventStream.getState()).toBe("connecting");

    FakeEventSource.instances[0].emit("connected", { userId: "u1" });
    expect(eventStream.getState()).toBe("connected");
  });

  it("delivers events to subscribers", async () => {
    const received: unknown[] = [];
    const unsubscribe = eventStream.onEvent((event) => received.push(event));
    eventStream.start();
    await flush();

    FakeEventSource.instances[0].emit("TASK_UPDATED", {
      id: "e1", type: "TASK_UPDATED", ts: "now", projectId: "p1",
    });

    expect(received).toContainEqual(
      expect.objectContaining({ type: "TASK_UPDATED", projectId: "p1" }),
    );
    unsubscribe();
  });

  it("emits a reconnected event on every connect so subscribers resynchronise", async () => {
    const types: string[] = [];
    eventStream.onEvent((event) => types.push(event.type));
    eventStream.start();
    await flush();

    FakeEventSource.instances[0].emit("connected", { userId: "u1" });

    expect(types).toContain(RECONNECTED);
  });

  it("reconnects with a freshly minted ticket after an error", async () => {
    // The reason native EventSource retry is not used: the old ticket has
    // expired, so retrying the same URL can only ever produce a 401.
    vi.useFakeTimers();
    eventStream.start();
    await vi.advanceTimersByTimeAsync(0);
    FakeEventSource.instances[0].emit("connected", { userId: "u1" });

    FakeEventSource.instances[0].fail();
    expect(eventStream.getState()).toBe("reconnecting");

    await vi.advanceTimersByTimeAsync(35000);

    expect(ticketMock.mock.calls.length).toBeGreaterThan(1);
    expect(FakeEventSource.instances.length).toBeGreaterThan(1);
  });

  it("closes the failed socket rather than leaking it", async () => {
    vi.useFakeTimers();
    eventStream.start();
    await vi.advanceTimersByTimeAsync(0);

    const first = FakeEventSource.instances[0];
    first.fail();
    await vi.advanceTimersByTimeAsync(35000);

    expect(first.closed).toBe(true);
    expect(FakeEventSource.openCount).toBeLessThanOrEqual(1);
  });

  it("reports offline honestly instead of retrying a dead network", async () => {
    vi.useFakeTimers();
    eventStream.start();
    await vi.advanceTimersByTimeAsync(0);

    setOnLine(false);
    FakeEventSource.instances[0].fail();

    expect(eventStream.getState()).toBe("offline");
  });

  it("stops cleanly on sign-out", async () => {
    eventStream.start();
    await flush();
    expect(FakeEventSource.openCount).toBe(1);

    eventStream.stop();

    expect(FakeEventSource.openCount).toBe(0);
    expect(eventStream.getState()).toBe("idle");
  });

  it("survives a ticket request failure and retries", async () => {
    vi.useFakeTimers();
    ticketMock.mockRejectedValueOnce(new Error("session expired"));
    eventStream.start();
    await vi.advanceTimersByTimeAsync(0);

    // No socket yet — the ticket never arrived.
    expect(FakeEventSource.instances.length).toBe(0);
    expect(eventStream.getState()).toBe("reconnecting");

    await vi.advanceTimersByTimeAsync(35000);
    expect(FakeEventSource.instances.length).toBeGreaterThan(0);
  });

  it("ignores an unparseable frame without dropping the connection", async () => {
    const received: unknown[] = [];
    eventStream.onEvent((event) => received.push(event));
    eventStream.start();
    await flush();

    const source = FakeEventSource.instances[0];
    source.onmessage?.({ data: "not json" } as MessageEvent);
    source.emit("TASK_UPDATED", { id: "e2", type: "TASK_UPDATED", ts: "now" });

    expect(received.some((e) => (e as { type: string }).type === "TASK_UPDATED")).toBe(true);
    expect(source.closed).toBe(false);
  });
});
