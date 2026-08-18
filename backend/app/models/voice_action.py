import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VoiceActionDraft(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "voice_action_drafts"
    __table_args__ = (
        UniqueConstraint(
            "voice_analysis_id", "client_action_id",
            name="uq_voice_action_draft_client_id",
        ),
    )

    voice_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_action_id: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Position in the model's own `suggestedActions` list.
    #:
    #: The relationship used to be ordered by `created_at`, which is identical
    #: for every draft of one analysis, so the order was a tie and could
    #: change between requests — see the `c87g2b4d0f69` migration for the
    #: failure that caused. This is the one ordering the drafts, the
    #: suggestions and the execution results all agree on.
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    extracted_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    user_edited_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    target_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    missing_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="LOW", server_default="LOW"
    )
    required_evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    selected_for_execution: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    execution_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DRAFT", server_default="DRAFT", index=True
    )
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    voice_analysis: Mapped["VoiceAnalysis"] = relationship(back_populates="action_drafts")
    clarifications: Mapped[list["VoiceClarification"]] = relationship(
        back_populates="action_draft"
    )
    execution_logs: Mapped[list["VoiceExecutionLog"]] = relationship(
        back_populates="action_draft"
    )


class VoiceClarification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "voice_clarifications"
    __table_args__ = (
        UniqueConstraint(
            "voice_analysis_id", "sequence",
            name="uq_voice_clarification_sequence",
        ),
    )

    voice_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    voice_action_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_action_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    field_path: Mapped[str] = mapped_column(String(300), nullable=False)
    question_ar: Mapped[str] = mapped_column(Text, nullable=False)
    question_en: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer_type: Mapped[str] = mapped_column(String(40), nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_audio_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="SET NULL"), nullable=True
    )
    answer_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    voice_analysis: Mapped["VoiceAnalysis"] = relationship(back_populates="clarifications")
    action_draft: Mapped["VoiceActionDraft | None"] = relationship(back_populates="clarifications")


class VoiceExecutionLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "voice_execution_logs"

    voice_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    voice_action_draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voice_action_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    voice_analysis: Mapped["VoiceAnalysis"] = relationship(back_populates="execution_logs")
    action_draft: Mapped["VoiceActionDraft"] = relationship(back_populates="execution_logs")
