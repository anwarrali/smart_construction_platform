import uuid
from datetime import date

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VoiceProcessingStatus


class SiteReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Daily/ad-hoc site report — can be created via text form or voice recording."""

    __tablename__ = "site_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percentage_reported: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    weather_conditions: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workers_count: Mapped[int | None] = mapped_column(nullable=True)
    equipment: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_completed: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_in_progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    delays: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", index=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    voice_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_recordings.id", ondelete="SET NULL"), nullable=True
    )
    voice_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_analyses.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="reports")
    task: Mapped["Task"] = relationship(back_populates="site_reports")
    submitted_by: Mapped["User"] = relationship(foreign_keys=[submitted_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    voice_recording: Mapped["VoiceRecording"] = relationship(foreign_keys=[voice_recording_id])
    voice_analysis: Mapped["VoiceAnalysis | None"] = relationship(foreign_keys=[voice_analysis_id])
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="site_report")

    def __repr__(self) -> str:
        return f"<SiteReport id={self.id} date={self.report_date}>"
