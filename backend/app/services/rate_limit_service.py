"""Database-backed rate limiting for authentication-sensitive endpoints.

The audit found no rate limiting anywhere in the platform: login accepted
unlimited password guesses, and any OTP feature built on top of that would
inherit the same weakness. This module is the shared counter.

Why the database rather than an in-process dict: the API runs several uvicorn
workers behind one port, so a per-process counter would let an attacker get
N times the intended attempts simply by having requests land on different
workers. The same reasoning already drove the scheduler's advisory lock.

Why not Redis: the deployment has PostgreSQL and nothing else, and this task
is explicitly not meant to introduce new infrastructure. The table is small,
indexed on exactly the lookup used, and pruned as it is read.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.rate_limit import RateLimitHit


def _cutoff(window_seconds: int, now: datetime) -> datetime:
    return now - timedelta(seconds=window_seconds)


def count_recent(db: Session, *, scope: str, key: str, window_seconds: int,
                 now: datetime | None = None) -> int:
    """How many hits this scope/key has recorded inside the window."""
    now = now or datetime.now(timezone.utc)
    return db.query(RateLimitHit).filter(
        RateLimitHit.scope == scope,
        RateLimitHit.key == key,
        RateLimitHit.created_at >= _cutoff(window_seconds, now),
    ).count()


def seconds_since_last(db: Session, *, scope: str, key: str,
                       now: datetime | None = None) -> float | None:
    """Age of the most recent hit, or None when there is none."""
    now = now or datetime.now(timezone.utc)
    last = db.query(RateLimitHit).filter(
        RateLimitHit.scope == scope, RateLimitHit.key == key,
    ).order_by(RateLimitHit.created_at.desc()).first()
    if not last:
        return None
    stamp = last.created_at
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (now - stamp).total_seconds()


def record_hit(db: Session, *, scope: str, key: str, now: datetime | None = None) -> None:
    """Record one attempt. The caller owns the transaction."""
    now = now or datetime.now(timezone.utc)
    db.add(RateLimitHit(scope=scope, key=key, created_at=now))
    # Autoflush is disabled on this session, so without a flush a second check
    # in the same request would not see the hit just recorded.
    db.flush()


def clear(db: Session, *, scope: str, key: str) -> None:
    """Forget this key's history — used after a success, so a legitimate user
    who mistyped a few times is not still throttled afterwards."""
    db.query(RateLimitHit).filter(
        RateLimitHit.scope == scope, RateLimitHit.key == key,
    ).delete(synchronize_session=False)


def prune(db: Session, *, older_than_seconds: int = 86_400,
          now: datetime | None = None) -> int:
    """Drop hits too old to affect any window. Called opportunistically from
    login, mirroring how `login` already prunes expired revoked tokens."""
    now = now or datetime.now(timezone.utc)
    return db.query(RateLimitHit).filter(
        RateLimitHit.created_at < _cutoff(older_than_seconds, now),
    ).delete(synchronize_session=False)
