import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import VoiceProcessingStatus

class VoiceRecording(Base, UUIDPrimaryKeyMixin, TimestampMixin):


    __tablename__ = "voice_recordings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    linked_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    audio_file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(nullable=True)

    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    status: Mapped[VoiceProcessingStatus] = mapped_column(
        PG_ENUM(VoiceProcessingStatus, name="voice_processing_status", create_type=True),
        nullable=False,
        default=VoiceProcessingStatus.UPLOADED,
        server_default=VoiceProcessingStatus.UPLOADED.name,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship()
    recorded_by: Mapped["User"] = relationship(foreign_keys=[recorded_by_id])
    linked_task: Mapped["Task"] = relationship(foreign_keys=[linked_task_id])

    def __repr__(self) -> str:
        return f"<VoiceRecording id={self.id} status={self.status}>"
