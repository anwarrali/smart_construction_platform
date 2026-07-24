"""
Issues — raised by Project Managers / Engineers / Contractors against a project or task.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import IssueSeverity, IssueStatus


class Issue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "issues"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    affects_schedule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    severity: Mapped[IssueSeverity] = mapped_column(
        PG_ENUM(IssueSeverity, name="issue_severity", create_type=True),
        nullable=False,
        default=IssueSeverity.MEDIUM,
        server_default=IssueSeverity.MEDIUM.name,
    )
    status: Mapped[IssueStatus] = mapped_column(
        PG_ENUM(IssueStatus, name="issue_status", create_type=True),
        nullable=False,
        default=IssueStatus.OPEN,
        server_default=IssueStatus.OPEN.name,
        index=True,
    )

    raised_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="issues")
    task: Mapped["Task"] = relationship()
    raised_by: Mapped["User"] = relationship(foreign_keys=[raised_by_id])
    assigned_to: Mapped["User"] = relationship(foreign_keys=[assigned_to_id])

    def __repr__(self) -> str:
        return f"<Issue id={self.id} title={self.title} status={self.status}>"
