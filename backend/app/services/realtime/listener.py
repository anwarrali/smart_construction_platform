"""One PostgreSQL `LISTEN` per worker, fanned out to that worker's SSE clients.

**This module is why realtime works at all under `--workers 2`.** Each uvicorn
worker is a separate process with separate memory. A client's SSE connection
lives in exactly one of them, while the request that changes data may be
handled by the other. An in-process registry would therefore drop roughly half
of all events — and, worse, would appear to work in single-worker testing.

PostgreSQL is the shared bus. Every worker holds one dedicated connection
issuing `LISTEN realtime`; every worker's publishes reach every worker's
clients. No Redis, no extra container, and the broker is the database that is
already the source of truth.

**Why a thread rather than asyncio.** The project uses psycopg2, which is
synchronous; waiting for a notification means blocking in `select()`. Adding
asyncpg for this one purpose would mean a second driver, a second connection
configuration and a second failure mode. Instead one daemon thread owns the
blocking wait and hands events to the event loop through
`call_soon_threadsafe`, which is the documented bridge between the two worlds.

The connection is deliberately **not** taken from SQLAlchemy's pool: a pooled
connection returned mid-`LISTEN` would silently stop listening, and holding one
out of the pool forever would starve request handling. This owns its own.
"""

from __future__ import annotations

import asyncio
import json
import logging
import select
import threading
import time
from typing import Callable

import psycopg2
import psycopg2.extensions

from app.core.config import settings
from app.services.realtime.publisher import CHANNEL, RealtimeEvent

logger = logging.getLogger("uvicorn.error").getChild("realtime.listener")

#: How long `select()` waits before looping, so a stop request is noticed
#: promptly rather than after the next notification (which may never come).
_POLL_TIMEOUT_SECONDS = 5.0

#: Reconnect backoff bounds for a listener whose connection died — a database
#: restart must not leave realtime permanently deaf, and must not spin.
_RECONNECT_MIN_SECONDS = 1.0
_RECONNECT_MAX_SECONDS = 30.0


class RealtimeListener:
    """Owns this worker's LISTEN connection and its in-process subscribers.

    Lifecycle is tied to the application's lifespan: `start()` on boot,
    `stop()` on shutdown. Shutdown must be prompt — a listener that blocks
    exit would make every container stop take its full timeout.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connection = None
        #: Callables that receive each event, on the event loop thread.
        self._handlers: set[Callable[[RealtimeEvent], None]] = set()
        self._handlers_lock = threading.Lock()
        self._connected = threading.Event()
        self._last_error: str | None = None

    # --- lifecycle ---------------------------------------------------------

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if not settings.REALTIME_ENABLED:
            logger.info("realtime disabled by configuration; not listening")
            return
        if self._thread and self._thread.is_alive():
            return
        self._loop = loop
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="realtime-listener", daemon=True
        )
        self._thread.start()
        logger.info("realtime listener started (channel=%s)", CHANNEL)

    def stop(self) -> None:
        """Signal the thread and close the connection so `select()` returns.

        Closing the socket is what actually wakes a thread parked in
        `select()`; the event alone would only be noticed after the poll
        timeout, delaying shutdown by up to `_POLL_TIMEOUT_SECONDS`.
        """
        self._stop.set()
        connection = self._connection
        if connection is not None:
            try:
                connection.close()
            except Exception:  # pragma: no cover - already closing
                pass
        thread = self._thread
        if thread and thread.is_alive():
            # Bounded: a daemon thread must never hold up interpreter exit.
            thread.join(timeout=5.0)
        self._thread = None
        self._connected.clear()
        logger.info("realtime listener stopped")

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # --- subscription ------------------------------------------------------

    def add_handler(self, handler: Callable[[RealtimeEvent], None]) -> None:
        with self._handlers_lock:
            self._handlers.add(handler)

    def remove_handler(self, handler: Callable[[RealtimeEvent], None]) -> None:
        with self._handlers_lock:
            self._handlers.discard(handler)

    @property
    def handler_count(self) -> int:
        with self._handlers_lock:
            return len(self._handlers)

    # --- the thread --------------------------------------------------------

    def _run(self) -> None:
        delay = _RECONNECT_MIN_SECONDS
        while not self._stop.is_set():
            try:
                self._listen_forever()
                delay = _RECONNECT_MIN_SECONDS  # a clean return resets backoff
            except Exception as error:
                if self._stop.is_set():
                    break
                self._connected.clear()
                self._last_error = str(error)
                logger.warning(
                    "realtime listener lost its connection (%s); retrying in %.0fs",
                    error, delay,
                )
                # Interruptible sleep: a stop during backoff should not wait it out.
                self._stop.wait(delay)
                delay = min(delay * 2, _RECONNECT_MAX_SECONDS)
        self._connected.clear()

    def _listen_forever(self) -> None:
        connection = psycopg2.connect(settings.DATABASE_URL)
        # LISTEN must not sit inside a transaction, or notifications are only
        # seen when it commits — which for an idle listener is never.
        connection.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self._connection = connection
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"LISTEN {CHANNEL};")
            self._connected.set()
            self._last_error = None
            logger.info("realtime listener connected")

            while not self._stop.is_set():
                if select.select([connection], [], [], _POLL_TIMEOUT_SECONDS) == ([], [], []):
                    continue
                connection.poll()
                while connection.notifies:
                    notify = connection.notifies.pop(0)
                    self._dispatch(notify.payload)
        finally:
            self._connected.clear()
            self._connection = None
            try:
                connection.close()
            except Exception:  # pragma: no cover
                pass

    def _dispatch(self, payload: str) -> None:
        """Parse one notification and hand it to the event loop."""
        try:
            event = RealtimeEvent.from_payload(json.loads(payload))
        except (ValueError, KeyError, TypeError):
            # A malformed payload must not kill the listener — that would take
            # realtime down for every client on this worker.
            logger.warning("discarding malformed realtime payload")
            return

        loop = self._loop
        if loop is None or loop.is_closed():
            return
        with self._handlers_lock:
            handlers = list(self._handlers)
        for handler in handlers:
            try:
                loop.call_soon_threadsafe(handler, event)
            except RuntimeError:  # pragma: no cover - loop shutting down
                pass


#: One listener per worker process.
_listener = RealtimeListener()


def get_listener() -> RealtimeListener:
    return _listener
