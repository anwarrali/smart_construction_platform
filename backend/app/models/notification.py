"""
Notifications — in-app notifications sent to users.
"""
import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import NotificationType, NotificationStatus


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        # The two hottest reads. `list_notifications` always filters on
        # user_id and orders by created_at DESC; `unread-count` filters on
        # user_id plus is_read, which had no index at all before.
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_unread", "user_id", "is_read"),
        # Deduplication lookup: "has this exact notification already been
        # raised for this user?" — see `notification_service.notify`.
        Index("ix_notifications_user_dedupe", "user_id", "dedupe_key"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    type: Mapped[NotificationType] = mapped_column(
        PG_ENUM(NotificationType, name="notification_type", create_type=True),
        nullable=False,
        default=NotificationType.SYSTEM,
        server_default=NotificationType.SYSTEM.name,
    )

    status: Mapped[NotificationStatus] = mapped_column(
        PG_ENUM(NotificationStatus, name="notification_status", create_type=True),
        nullable=False,
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.name,
        index=True,
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    related_entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="SYSTEM", server_default="SYSTEM", index=True)
    requires_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Smart notification fields ------------------------------------------
    # Kept deliberately small: `category` already carries the DIRECT / WORKFLOW
    # / REMINDER / DEADLINE grouping (it is a plain String, so no new enum and
    # no migration is needed to name another one), and `related_entity_*`
    # already carries the subject. Only what genuinely could not be expressed
    # is added here.

    #: INFO | NORMAL | IMPORTANT | CRITICAL — how loudly to present this.
    #: Escalation is modelled as a *new* notification at a higher priority
    #: rather than mutating an old one, so the user's history stays truthful
    #: about what they were told and when.
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NORMAL", server_default="NORMAL", index=True
    )
    #: Stable identity of "this exact thing, for this user, at this stage".
    #: Two sweeps that observe the same state produce the same key, which is
    #: what makes repeated evaluation idempotent. NULL for one-off event
    #: notifications that are allowed to repeat (e.g. each new message).
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Localization, reusing the pattern already proven on `AIInsight`:
    #: the key names the sentence and the params fill it, so the client can
    #: render Arabic or English. `title`/`message` stay populated with English
    #: as the fallback for older rows and for any client that does not
    #: understand the key.
    message_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    message_params_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    project: Mapped["Project"] = relationship()
    task: Mapped["Task"] = relationship()

    def __repr__(self) -> str:
        return f"<Notification id={self.id} title={self.title} is_read={self.is_read}>"
