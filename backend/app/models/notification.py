"""
Notifications — in-app notifications sent to users.
"""
import uuid

from sqlalchemy import ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import NotificationType, NotificationStatus


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"

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

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    project: Mapped["Project"] = relationship()
    task: Mapped["Task"] = relationship()

    def __repr__(self) -> str:
        return f"<Notification id={self.id} title={self.title} is_read={self.is_read}>"
