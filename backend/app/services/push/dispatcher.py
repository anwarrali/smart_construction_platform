"""Turns a persisted notification into push deliveries.

Two rules shape everything here:

1. **The database notification must never be lost because push failed.** Push
   is dispatched *after* the caller's transaction commits, on a background
   thread with its own session. An FCM outage, a DNS failure or a 30-second
   timeout therefore cannot roll back the business write that produced the
   notification, and cannot stall the HTTP response either.

2. **A dead token is retired, a sick network is not.** Only the failures FCM
   states are permanent deactivate a device row; everything else leaves the
   token alone so the next notification retries it.

The queue is attached to the SQLAlchemy session rather than to a global, so
concurrent requests cannot leak each other's pending pushes, and a rollback
discards them — a notification that was never committed must never be pushed.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.device_token import DeviceToken
from app.services.push.base import DeliveryStatus, PushMessage, PushResult
from app.services.push.fcm import get_provider

logger = logging.getLogger("uvicorn.error").getChild("push")

#: Key under which pending pushes ride along on `Session.info`.
_QUEUE_KEY = "_pending_push_messages"


# --- queueing ---------------------------------------------------------------


def queue_push(db: Session, user_id: uuid.UUID, message: PushMessage) -> None:
    """Remember to push this once the caller's transaction commits.

    Callers keep their own transaction boundary (see `notification_service`),
    so this cannot send immediately: the notification row it refers to may
    still be rolled back.
    """
    if not settings.PUSH_ENABLED:
        return
    db.info.setdefault(_QUEUE_KEY, []).append((user_id, message))


def _drain(session: Session) -> list[tuple[uuid.UUID, PushMessage]]:
    return session.info.pop(_QUEUE_KEY, []) or []


@event.listens_for(SessionLocal, "after_commit")
def _dispatch_after_commit(session: Session) -> None:
    pending = _drain(session)
    if not pending:
        return
    for user_id, message in pending:
        _spawn(user_id, message)


@event.listens_for(SessionLocal, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    # The notifications these referred to no longer exist. Pushing them would
    # tell a user about something that did not happen.
    _drain(session)


def _spawn(user_id: uuid.UUID, message: PushMessage) -> None:
    if not settings.PUSH_ENABLED:
        return
    if settings.PUSH_SYNCHRONOUS:
        # Tests and one-off scripts want the delivery to have happened by the
        # time the call returns. Never enabled in a served process.
        send_to_user(user_id, message)
        return
    thread = threading.Thread(
        target=_send_guarded, args=(user_id, message), name="push-dispatch", daemon=True
    )
    thread.start()


def _send_guarded(user_id: uuid.UUID, message: PushMessage) -> None:
    try:
        send_to_user(user_id, message)
    except Exception:  # pragma: no cover - defensive; a thread must not die loud
        logger.exception("push dispatch failed for user %s", user_id)


# --- delivery ---------------------------------------------------------------


def active_tokens_for_users(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Every live delivery address per user. One user, many devices."""
    if not user_ids:
        return {}
    rows = db.execute(
        select(DeviceToken.user_id, DeviceToken.token)
        .where(DeviceToken.user_id.in_(user_ids), DeviceToken.is_active.is_(True))
    ).all()
    grouped: dict[uuid.UUID, list[str]] = {}
    for row_user_id, token in rows:
        grouped.setdefault(row_user_id, []).append(token)
    return grouped


def send_to_user(user_id: uuid.UUID, message: PushMessage) -> list[PushResult]:
    """Deliver to every active device of one user, on a fresh session.

    A fresh session because this normally runs on a background thread after the
    request's session has already been returned to the pool.
    """
    db = SessionLocal()
    try:
        tokens = active_tokens_for_users(db, [user_id]).get(user_id, [])
        if not tokens:
            return []
        results = get_provider().send(tokens, message)
        apply_results(db, results)
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def apply_results(db: Session, results: list[PushResult]) -> None:
    """Retire tokens FCM called dead; keep the rest alive.

    Deactivation is recorded with a reason rather than deleting the row, so
    "this device was never registered" stays distinguishable from "this device
    was dropped by FCM" when a missing notification is investigated.
    """
    now = datetime.now(timezone.utc)
    dead = [result.token for result in results if result.should_deactivate]
    alive = [result.token for result in results if result.status is DeliveryStatus.SENT]

    if dead:
        reasons = {
            result.token: (result.detail or "rejected by provider")[:200]
            for result in results
            if result.should_deactivate
        }
        for token in dead:
            db.execute(
                update(DeviceToken)
                .where(DeviceToken.token == token)
                .values(is_active=False, deactivated_reason=reasons[token], updated_at=now)
            )
        logger.info("deactivated %s push token(s) rejected by the provider", len(dead))

    if alive:
        db.execute(
            update(DeviceToken).where(DeviceToken.token.in_(alive)).values(last_used_at=now)
        )

    failed = [r for r in results if r.status is DeliveryStatus.TRANSIENT_FAILURE]
    if failed:
        logger.warning(
            "%s push delivery(ies) failed transiently: %s",
            len(failed),
            failed[0].detail,
        )
