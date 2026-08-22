"""Who is allowed to see which event.

This is the security boundary of the realtime layer, and it holds one line:
**the client may narrow its subscription, never widen it.** A subscription
request is intersected with what the server independently resolved for that
user; it is never trusted as the source of scope.

Authorization is re-resolved on a short TTL rather than pinned at connect.
Project membership changes — someone is removed from a project — and a
connection that cached its scope at open would keep receiving that project's
events until the tab closed, which could be days. The TTL bounds that window to
seconds.

The rules reuse `accessible_project_ids`, the same helper the REST endpoints
use. That is deliberate and was the lesson of the document-scope work earlier
in this codebase: a second implementation of "what can this user see" drifts
from the first, and the copy that drifts is the one nobody audits.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.core.deps import accessible_project_ids
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.enums import UserStatus
from app.models.user import User
from app.services.realtime.publisher import RealtimeEvent

logger = logging.getLogger("uvicorn.error").getChild("realtime.broker")


class AuthorizationScope:
    """What one connected user may currently receive.

    `project_ids is None` means unrestricted — the platform-wide viewer case
    that `accessible_project_ids` signals the same way. Preserving that
    distinction matters: an empty list means "no projects", and conflating the
    two would either blind an admin or expose everything to a member of none.
    """

    def __init__(self, user_id: uuid.UUID):
        self.user_id = user_id
        self.project_ids: list[uuid.UUID] | None = []
        self.is_active: bool = False
        self.refreshed_at: float = 0.0

    @property
    def unrestricted(self) -> bool:
        return self.project_ids is None

    def allows(self, event: RealtimeEvent) -> bool:
        """Whether this user may see this event.

        A user-targeted event is theirs only if it names them. A project event
        requires access to that project. An event naming both must satisfy
        whichever it names — user identity is the stronger claim, so it wins.
        """
        if not self.is_active:
            return False
        if event.user_id is not None:
            return event.user_id == self.user_id
        if event.project_id is not None:
            return self.unrestricted or event.project_id in (self.project_ids or [])
        # Unaddressed events are refused rather than broadcast. `publish`
        # already rejects them; this is the second door on the same room.
        return False

    def refresh(self) -> None:
        """Re-resolve access from the database. Cheap, indexed, and bounded."""
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.id == self.user_id).first()
            if user is None or user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
                # A deactivated account stops receiving events at the next
                # refresh, without needing the connection to be torn down.
                self.is_active = False
                self.project_ids = []
            else:
                self.is_active = True
                self.project_ids = accessible_project_ids(session, user)
        except Exception:
            # Fail closed. An error resolving permissions must never widen
            # them; the connection goes quiet until the next refresh succeeds.
            logger.exception("could not refresh realtime authorization; failing closed")
            self.is_active = False
            self.project_ids = []
        finally:
            session.close()
            self.refreshed_at = time.monotonic()

    def refresh_if_stale(self) -> None:
        if time.monotonic() - self.refreshed_at >= settings.REALTIME_AUTH_TTL_SECONDS:
            self.refresh()


class Subscriber:
    """One SSE connection: a bounded queue plus the scope that guards it."""

    def __init__(self, user_id: uuid.UUID, event_types: set[str] | None = None):
        self.scope = AuthorizationScope(user_id)
        #: Client-requested narrowing. None means "everything I am allowed".
        #: This can only ever remove events — see `accepts`.
        self.event_types = event_types or None
        self.queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(
            maxsize=settings.REALTIME_MAX_QUEUE
        )
        self.dropped = 0

    def accepts(self, event: RealtimeEvent) -> bool:
        """Authorization first, then the client's own narrowing.

        The order is not cosmetic. Authorization is the server's decision and
        must not be reachable by anything the client sends; the client filter
        is applied only to events that already passed it.
        """
        self.scope.refresh_if_stale()
        if not self.scope.allows(event):
            return False
        if self.event_types is not None and event.type not in self.event_types:
            return False
        return True

    def offer(self, event: RealtimeEvent) -> None:
        """Enqueue if authorized. Never blocks the listener thread.

        A slow or wedged client must not stall delivery for everyone else on
        this worker, so the queue is bounded and overflow is dropped. Dropping
        is safe *because* events are hints: the client refetches on reconnect
        and on its next event, so a dropped hint costs latency, not
        correctness. That property is what makes a bounded queue acceptable
        here and would not hold if events carried state.
        """
        if not self.accepts(event):
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 50 == 0:
                logger.warning(
                    "realtime subscriber %s is not keeping up (%s dropped)",
                    self.scope.user_id, self.dropped,
                )


class RealtimeBroker:
    """Tracks this worker's subscribers and offers each event to all of them."""

    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()

    def add(self, subscriber: Subscriber) -> None:
        self._subscribers.add(subscriber)
        logger.info(
            "realtime connection opened (user=%s, connections=%s)",
            subscriber.scope.user_id, len(self._subscribers),
        )

    def remove(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        logger.info(
            "realtime connection closed (user=%s, connections=%s, dropped=%s)",
            subscriber.scope.user_id, len(self._subscribers), subscriber.dropped,
        )

    @property
    def connection_count(self) -> int:
        return len(self._subscribers)

    def dispatch(self, event: RealtimeEvent) -> None:
        """Called on the event loop thread for every event this worker sees."""
        delivered = 0
        # A copy: `offer` cannot mutate the set, but a disconnect racing this
        # loop could, and iterating a mutating set raises.
        for subscriber in list(self._subscribers):
            before = subscriber.queue.qsize()
            subscriber.offer(event)
            if subscriber.queue.qsize() > before:
                delivered += 1
        logger.debug(
            "event %s (%s) offered to %s connection(s), delivered to %s",
            event.type, event.id, len(self._subscribers), delivered,
        )


_broker = RealtimeBroker()


def get_broker() -> RealtimeBroker:
    return _broker
