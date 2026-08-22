"""Realtime updates over Server-Sent Events.

    change in worker B                     SSE client on worker A
            │                                       ▲
      publish(db, event)                            │
            │                                  broker filters by
            ▼                                  user + accessible projects
    pg_notify('realtime', envelope)                 │
            │                                       │
            └────────── LISTEN realtime ────────────┘
                    (one connection per worker)

Three modules, one responsibility each:

  * `publisher` — builds the envelope and hands it to PostgreSQL, on the
    caller's transaction so a rollback announces nothing.
  * `listener`  — one `LISTEN` connection per worker, so an event raised in one
    uvicorn worker reaches clients connected to the other.
  * `broker`    — decides, per connection, whether this user may see this
    event. The security boundary.

Two invariants hold the design together:

  1. **Events are hints, never state.** They carry identifiers and a type; the
     client refetches through the existing REST API, which re-applies every
     authorization rule. The realtime layer can therefore never become a way
     to read data the REST API would refuse.
  2. **No business logic lives here.** Call sites decide what happened and who
     it concerns; this package only carries the announcement.
"""

from app.services.realtime.broker import (
    AuthorizationScope,
    RealtimeBroker,
    Subscriber,
    get_broker,
)
from app.services.realtime.listener import RealtimeListener, get_listener
from app.services.realtime.publisher import (
    ALL_EVENT_TYPES,
    CHANNEL,
    EventType,
    RealtimeEvent,
    publish,
    publish_event,
)

__all__ = [
    "ALL_EVENT_TYPES",
    "AuthorizationScope",
    "CHANNEL",
    "EventType",
    "RealtimeBroker",
    "RealtimeEvent",
    "RealtimeListener",
    "Subscriber",
    "get_broker",
    "get_listener",
    "publish",
    "publish_event",
]
