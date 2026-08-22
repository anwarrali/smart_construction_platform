"""The Server-Sent Events endpoints.

Two routes, because `EventSource` cannot send an `Authorization` header:

    POST /events/ticket   normal bearer auth  -> a ~60s single-purpose ticket
    GET  /events/stream   ?ticket=...         -> the event stream

The split exists so the long-lived access token never appears in a URL, where
it would be written to access logs, proxy logs and `Referer` headers. The
ticket that does appear there expires in about a minute and can do exactly one
thing: open a read-only stream. It cannot call any other endpoint —
`get_current_user` rejects any token whose type is not "access", and this
stream rejects any token whose type is not the ticket type.

Nothing about a business object is sent down this stream. Events name what
changed; the client refetches through the REST API, which re-applies every
authorization rule it already enforces.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import SSE_TICKET_TYPE, create_sse_ticket, decode_token
from app.db.database import get_db
from app.models.enums import UserStatus
from app.models.user import User
from app.services.realtime import (
    ALL_EVENT_TYPES,
    RealtimeEvent,
    Subscriber,
    get_broker,
    get_listener,
)

from datetime import timedelta

logger = logging.getLogger("uvicorn.error").getChild("realtime.api")

router = APIRouter(prefix="/events", tags=["Realtime"])


def _require_enabled() -> None:
    if not settings.REALTIME_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime updates are not enabled on this server",
        )


@router.post("/ticket")
def create_ticket(current_user: User = Depends(get_current_user)):
    """Mint a short-lived ticket for opening the event stream.

    Authenticated exactly like every other endpoint. The response carries no
    scope information: what this user may see is resolved server-side when the
    stream opens, and re-resolved periodically thereafter.
    """
    _require_enabled()
    ticket = create_sse_ticket(
        str(current_user.id),
        timedelta(seconds=settings.REALTIME_TICKET_TTL_SECONDS),
    )
    return {
        "ticket": ticket,
        "expiresInSeconds": settings.REALTIME_TICKET_TTL_SECONDS,
        # So the client can schedule a refresh before the stream is dropped.
        "heartbeatSeconds": settings.REALTIME_HEARTBEAT_SECONDS,
    }


def _user_from_ticket(ticket: str, db: Session) -> User:
    """Resolve the ticket to an active user, or refuse.

    Every failure returns the same 401 with the same wording. Distinguishing
    "expired" from "wrong purpose" from "unknown user" would tell an
    unauthenticated caller which of their guesses was closest.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired realtime ticket",
    )

    payload = decode_token(ticket)  # signature + expiry, or None
    if payload is None or payload.get("type") != SSE_TICKET_TYPE:
        logger.info("realtime connection refused: invalid or wrong-purpose ticket")
        raise unauthorized

    subject = payload.get("sub")
    if not subject:
        raise unauthorized
    try:
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError):
        raise unauthorized

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
        logger.info("realtime connection refused: user missing, inactive or suspended")
        raise unauthorized
    return user


@router.get("/stream")
async def stream_events(
    request: Request,
    ticket: str = Query(..., description="Short-lived ticket from POST /events/ticket"),
    types: str | None = Query(
        None,
        description=(
            "Optional comma-separated event types to narrow the stream. "
            "Can only reduce what is delivered, never widen it."
        ),
    ),
    db: Session = Depends(get_db),
):
    """The event stream.

    Delivers only what this user is authorized to see, re-checked on a short
    TTL so revoked project access takes effect within seconds rather than
    lasting as long as the tab stays open.
    """
    _require_enabled()
    user = _user_from_ticket(ticket, db)

    # A client-supplied narrowing. Unknown names are discarded rather than
    # rejected so an older frontend naming a retired type still connects; and
    # because this only ever removes events, a hostile value cannot widen
    # anything — the worst it achieves is silencing its own stream.
    requested: set[str] | None = None
    if types:
        requested = {name.strip() for name in types.split(",") if name.strip()} & ALL_EVENT_TYPES
        if not requested:
            requested = None

    subscriber = Subscriber(user_id=user.id, event_types=requested)
    # Resolve authorization once up front so the first event is not delayed by
    # a database round trip, and so a connection from a user with no access is
    # quiet from the outset.
    subscriber.scope.refresh()

    broker = get_broker()
    listener = get_listener()

    def on_event(event: RealtimeEvent) -> None:
        subscriber.offer(event)

    async def event_stream():
        broker.add(subscriber)
        listener.add_handler(on_event)
        try:
            # Tell EventSource how soon to retry. The client applies its own
            # backoff and jitter on top; this is the floor, not the policy.
            yield f"retry: {settings.REALTIME_RETRY_MS}\n\n".encode()
            # An explicit "you are connected" frame. The client uses it to move
            # from `connecting` to `connected` and to trigger its reconnect
            # refetch, which is what recovers anything missed while away.
            yield _frame("connected", {"userId": str(user.id), "ts": _now()})

            while True:
                # Disconnects are not always signalled promptly by the ASGI
                # server, so the queue wait doubles as the disconnect check.
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        subscriber.queue.get(),
                        timeout=settings.REALTIME_HEARTBEAT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # A comment frame: ignored by EventSource, but it keeps
                    # proxies from dropping an idle connection, and a write
                    # failure here is how we learn the client is gone.
                    yield b": ping\n\n"
                    continue
                yield _frame(event.type, event.to_payload(), event_id=event.id)
        except asyncio.CancelledError:  # pragma: no cover - normal disconnect
            raise
        finally:
            # Both, always. A leaked handler would keep a dead connection's
            # queue filling for the lifetime of the worker.
            listener.remove_handler(on_event)
            broker.remove(subscriber)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default, which would hold
            # events until the buffer fills — indistinguishable from realtime
            # being broken. Harmless when nothing is proxying.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
def realtime_health(current_user: User = Depends(get_current_user)):
    """Whether this worker's listener is connected. For diagnosis only.

    Reports transport state and counts, never who is connected or what has
    been delivered.
    """
    listener = get_listener()
    return {
        "enabled": settings.REALTIME_ENABLED,
        "listenerConnected": listener.is_connected,
        "lastError": listener.last_error,
        "connections": get_broker().connection_count,
        "heartbeatSeconds": settings.REALTIME_HEARTBEAT_SECONDS,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _frame(event_type: str, payload: dict, event_id: str | None = None) -> bytes:
    """One SSE frame. `id:` lets EventSource report Last-Event-ID on reconnect."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(payload, separators=(',', ':'))}")
    return ("\n".join(lines) + "\n\n").encode()
