"""What a caller may spend on `tools/call`, and how fast.

Before this, an MCP client could call tools as fast as the API would answer.
That was the one limitation that mattered: every other gap on this surface
costs a client some convenience, while this one lets a single misconfigured
loop — an agent that retries on every failure, say — put unbounded load on the
database on behalf of a perfectly legitimate user.

## What is counted, and what is not

`tools/call` only. `initialize`, `ping`, `tools/list` and notifications are
answered from a module constant or one filtered query and cost nothing worth
metering; charging for them would mean a client that reconnects often is
throttled for doing the right thing.

**A batch costs one unit per `tools/call` it contains.** Counting requests
instead of calls would leave batching as a way straight through the limit,
which is not a subtle hole — the transport already accepts batches, and one
POST could carry hundreds.

## Why the whole request is refused, rather than part of it

A request that cannot afford all of its calls is refused entirely, and spends
nothing. Running the first few calls of a batch and refusing the rest would
give a client a partial result it cannot distinguish from a complete one, in a
protocol where each call is a separate question. All-or-nothing is the answer
a client can act on.

Nothing is recorded for a refused request, either. Charging for refusals is
right for a login — an attacker guessing passwords *should* dig their own hole
deeper — and wrong here, where the caller is a legitimate client going too
fast and needs the window to actually drain so it can recover.

## Why the database

The same reason `rate_limit_service` gives: several uvicorn workers share one
port, so an in-process counter would hand out N times the intended budget to
anyone whose requests land on different workers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import rate_limit_service

#: The `rate_limit_hits.scope` these rows live under. Distinct from "login",
#: so neither limit can ever consume the other's budget.
SCOPE = "mcp_tool_call"

#: Rows older than this are dropped opportunistically — see `_prune_if_idle`.
PRUNE_OLDER_THAN_SECONDS = 86_400


@dataclass(frozen=True)
class Budget:
    """The verdict on one request, and what to tell the client.

    `retry_after` is only meaningful when `allowed` is false, and is always at
    least one second: a `Retry-After: 0` invites the immediate retry the limit
    exists to prevent.
    """

    allowed: bool
    limit: int
    remaining: int
    retry_after: int = 0
    #: True when limiting is switched off entirely. The caller uses it to omit
    #: the headers rather than publish a meaningless limit.
    enabled: bool = True

    @property
    def headers(self) -> dict[str, str]:
        if not self.enabled:
            return {}
        values = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
        }
        if not self.allowed:
            values["Retry-After"] = str(self.retry_after)
        return values


def unlimited() -> Budget:
    return Budget(allowed=True, limit=0, remaining=0, enabled=False)


def is_enabled() -> bool:
    """Both settings must be positive. Either at zero switches it off, which is
    how a deployment on a trusted network opts out without editing code."""
    return settings.MCP_RATE_LIMIT_CALLS > 0 and settings.MCP_RATE_LIMIT_WINDOW_SECONDS > 0


def cost(message) -> int:
    """How many units this decoded request would spend.

    Takes the already-decoded body — a dict or a list — so the count is made
    from what will actually be dispatched, not from a second parse that could
    disagree with it. A malformed member costs nothing; it is about to be
    refused as a protocol error anyway.

    A `tools/call` sent as a notification is counted like any other. It has no
    id and produces no response, but it still runs the tool.
    """
    if isinstance(message, list):
        return sum(cost(item) for item in message)
    if isinstance(message, dict) and message.get("method") == "tools/call":
        return 1
    return 0


def consume(db: Session, *, key: str, units: int, now: datetime | None = None) -> Budget:
    """Charge `units` against `key`, or refuse the request outright.

    The caller owns the transaction; the hits are flushed, not committed, so a
    request that goes on to fail for some unrelated reason does not leave a
    charge behind for work that never happened. `api/mcp.py` commits once the
    request is going ahead.
    """
    if not is_enabled() or units <= 0:
        return unlimited()

    now = now or datetime.now(timezone.utc)
    limit = settings.MCP_RATE_LIMIT_CALLS
    window = settings.MCP_RATE_LIMIT_WINDOW_SECONDS

    used = rate_limit_service.count_recent(
        db, scope=SCOPE, key=key, window_seconds=window, now=now,
    )
    if used == 0:
        _prune_if_idle(db, now)

    if used + units > limit:
        wait = rate_limit_service.seconds_until_slot_frees(
            db, scope=SCOPE, key=key, window_seconds=window, limit=limit, now=now,
        )
        return Budget(
            allowed=False, limit=limit, remaining=max(0, limit - used),
            retry_after=max(1, math.ceil(wait)),
        )

    for _ in range(units):
        rate_limit_service.record_hit(db, scope=SCOPE, key=key, now=now)

    return Budget(allowed=True, limit=limit, remaining=max(0, limit - used - units))


def _prune_if_idle(db: Session, now: datetime) -> None:
    """Drop hits too old to affect any window, on the first call after a lull.

    Pruning on every call would put a DELETE in the path of every tool call for
    rows that are almost never there; pruning never would leave the table to
    grow at the rate a busy client calls. Doing it when a key's window is empty
    costs one extra statement per idle period and nothing during a burst.

    `login` prunes the same table on the same terms, so a deployment where
    anybody signs in is covered twice over.
    """
    rate_limit_service.prune(db, older_than_seconds=PRUNE_OLDER_THAN_SECONDS, now=now)
