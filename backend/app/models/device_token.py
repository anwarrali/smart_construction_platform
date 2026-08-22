"""Push device registrations — one row per (user, device) that can receive push.

Deliberately *not* a column on `users`. A person carries an Android phone, an
iPhone and two browsers, and a notification that only reached whichever device
registered last would be worse than no push at all: the user would learn to
distrust it. So the relationship is one-to-many, every active row is a
delivery target, and a token that FCM rejects is deactivated rather than
deleted — keeping the row is what lets us tell "this device was never
registered" apart from "this device unsubscribed", which matters when a
delivery failure is being diagnosed.

The FCM registration token is the only secret here and it is a *delivery
address*, not a credential: possessing it lets someone send a notification to
the device, never read anything. It is still treated as sensitive — the token
is unique so it cannot be silently claimed by a second account, and the API
never returns it to a client.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import DevicePlatform
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DeviceToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "device_tokens"
    __table_args__ = (
        # The dispatch query: "every live delivery address for this person".
        Index("ix_device_tokens_user_active", "user_id", "is_active"),
        # Re-registration lookup. A device re-registers on every cold start and
        # after every token refresh, so this runs far more often than any read.
        Index("ix_device_tokens_token", "token", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: The FCM registration token. Long: FCM tokens have no documented maximum
    #: and have grown past 200 characters more than once.
    token: Mapped[str] = mapped_column(String(512), nullable=False)

    platform: Mapped[DevicePlatform] = mapped_column(
        PG_ENUM(DevicePlatform, name="device_platform", create_type=True),
        nullable=False,
    )

    #: A stable per-installation identifier supplied by the client, used to
    #: retire the *previous* token of the same installation when FCM rotates
    #: it. Without this a phone accumulates a new row on every token refresh
    #: and the dead ones are only discovered when a send fails.
    device_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    #: Free-form, for support ("Pixel 8 / Android 14", "Chrome 129 on Windows").
    device_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    #: Last time this token was seen alive — refreshed on re-registration and
    #: on a successful send. A token untouched for months is a stale install.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )

    #: Why FCM stopped accepting it, kept for diagnosis. NULL while active.
    deactivated_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    user: Mapped["User"] = relationship(back_populates="device_tokens")

    def __repr__(self) -> str:
        return (
            f"<DeviceToken id={self.id} user={self.user_id} "
            f"platform={self.platform} active={self.is_active}>"
        )
