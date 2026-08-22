"""Registration and retirement of push devices.

The interesting problem here is not storing a token; it is that the same
physical device produces a *different* token over time (FCM rotates them), and
the same token can move between accounts (a shared site tablet where one worker
signs out and the next signs in). Getting either wrong sends somebody else's
notifications to the wrong person, so both cases are handled explicitly:

  * a token already on file is **reassigned** to the caller, never duplicated;
  * a re-registration that carries a `device_id` **retires that installation's
    previous tokens**, so a rotating device does not accumulate dead rows.

Everything is scoped to the authenticated user by the caller. Nothing in this
module takes a user id that did not come from the access token.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.device_token import DeviceToken
from app.models.enums import DevicePlatform


def register_device(
    db: Session,
    *,
    user_id: uuid.UUID,
    token: str,
    platform: DevicePlatform,
    device_id: str | None = None,
    device_name: str | None = None,
    app_version: str | None = None,
) -> DeviceToken:
    """Register (or re-register) one device for one user. Idempotent."""
    now = datetime.now(timezone.utc)

    existing = db.execute(
        select(DeviceToken).where(DeviceToken.token == token)
    ).scalar_one_or_none()

    if existing is not None:
        # Reassign rather than reject. A shared tablet legitimately moves
        # between accounts, and the token belongs to the *installation*; the
        # person now signed in is the one who should receive its pushes.
        # Rejecting here would leave the previous user's rows live and
        # deliver their notifications to whoever holds the device.
        existing.user_id = user_id
        existing.platform = platform
        existing.device_id = device_id or existing.device_id
        existing.device_name = device_name or existing.device_name
        existing.app_version = app_version or existing.app_version
        existing.is_active = True
        existing.deactivated_reason = None
        existing.last_used_at = now
        record = existing
    else:
        record = DeviceToken(
            user_id=user_id,
            token=token,
            platform=platform,
            device_id=device_id,
            device_name=device_name,
            app_version=app_version,
            is_active=True,
            last_used_at=now,
        )
        db.add(record)

    db.flush()

    if device_id:
        # FCM rotated this installation's token: the old one is now dead but
        # would otherwise stay active forever, since a rotated token fails
        # silently rather than reporting itself unregistered.
        db.execute(
            update(DeviceToken)
            .where(
                DeviceToken.device_id == device_id,
                DeviceToken.id != record.id,
                DeviceToken.is_active.is_(True),
            )
            .values(
                is_active=False,
                deactivated_reason="superseded by a newer token for this device",
                updated_at=now,
            )
        )

    return record


def unregister_device(
    db: Session,
    *,
    user_id: uuid.UUID,
    token: str | None = None,
    device_id: str | None = None,
) -> int:
    """Retire a device on sign-out. Returns how many rows were deactivated.

    Scoped to `user_id` in the WHERE clause, so a caller cannot unsubscribe
    somebody else's device by guessing a token.

    Deactivated, not deleted: keeping the row preserves the answer to "was
    this device ever registered", which is the first question asked when a
    notification did not arrive.
    """
    if not token and not device_id:
        return 0

    statement = update(DeviceToken).where(
        DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True)
    )
    statement = (
        statement.where(DeviceToken.token == token)
        if token
        else statement.where(DeviceToken.device_id == device_id)
    )
    result = db.execute(
        statement.values(
            is_active=False,
            deactivated_reason="signed out",
            updated_at=datetime.now(timezone.utc),
        )
    )
    return int(result.rowcount or 0)


def list_devices(db: Session, *, user_id: uuid.UUID, include_inactive: bool = False):
    """This user's devices, newest first."""
    statement = select(DeviceToken).where(DeviceToken.user_id == user_id)
    if not include_inactive:
        statement = statement.where(DeviceToken.is_active.is_(True))
    return list(db.execute(statement.order_by(DeviceToken.created_at.desc())).scalars())
