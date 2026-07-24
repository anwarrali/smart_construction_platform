import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import VoiceAnalysisStatus, VoiceConfirmationStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VoiceAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Durable AI-assisted field update; AI output is never executable by itself."""

    __tablename__ = "voice_analyses"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    field_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_submissions.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    audio_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True, unique=True,
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status: Mapped[VoiceAnalysisStatus] = mapped_column(
        PG_ENUM(VoiceAnalysisStatus, name="voice_analysis_status", create_type=True),
        nullable=False, default=VoiceAnalysisStatus.UPLOADED,
        server_default=VoiceAnalysisStatus.UPLOADED.name, index=True,
    )
    structured_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_status: Mapped[VoiceConfirmationStatus] = mapped_column(
        PG_ENUM(
            VoiceConfirmationStatus,
            name="voice_confirmation_status",
            create_type=True,
        ),
        nullable=False, default=VoiceConfirmationStatus.PENDING,
        server_default=VoiceConfirmationStatus.PENDING.name, index=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    action_results: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    retention_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PRESERVE", server_default="PRESERVE",
    )

    project: Mapped["Project"] = relationship()
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    task: Mapped["Task | None"] = relationship(foreign_keys=[task_id])
    field_submission: Mapped["FieldSubmission | None"] = relationship()
    audio_attachment: Mapped["Attachment | None"] = relationship()
    confirmed_by: Mapped["User | None"] = relationship(foreign_keys=[confirmed_by_id])
