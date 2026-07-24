"""
Engineering coordination: a design change in one discipline triggers
notifications/approval workflow across affected disciplines.
"""
import uuid

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DesignChangeStatus


class DesignChange(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "design_changes"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_drawings: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_cost_impact: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    expected_schedule_impact_days: Mapped[int | None] = mapped_column(nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_discipline: Mapped[str] = mapped_column(String(50), nullable=False)
    # disciplines impacted by this change, stored as a child table (many-to-many)

    proposed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[DesignChangeStatus] = mapped_column(
        PG_ENUM(DesignChangeStatus, name="design_change_status", create_type=True),
        nullable=False,
        default=DesignChangeStatus.PROPOSED,
        server_default=DesignChangeStatus.PROPOSED.name,
        index=True,
    )

    project: Mapped["Project"] = relationship(back_populates="design_changes")
    task: Mapped["Task"] = relationship()
    proposed_by: Mapped["User"] = relationship(foreign_keys=[proposed_by_id])
    approved_by: Mapped["User"] = relationship(foreign_keys=[approved_by_id])

    affected_disciplines: Mapped[list["DesignChangeAffectedDiscipline"]] = relationship(
        back_populates="design_change", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DesignChange id={self.id} title={self.title} status={self.status}>"


class DesignChangeAffectedDiscipline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Which disciplines are notified/affected by a given design change (M:N)."""

    __tablename__ = "design_change_affected_disciplines"

    design_change_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("design_changes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discipline: Mapped[str] = mapped_column(String(50), nullable=False)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged: Mapped[bool] = mapped_column(default=False, nullable=False)

    design_change: Mapped["DesignChange"] = relationship(back_populates="affected_disciplines")
    acknowledged_by: Mapped["User"] = relationship(foreign_keys=[acknowledged_by_id])
