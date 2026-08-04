import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AIActionVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Append-only application-level version for an AI-assisted mutation."""

    __tablename__ = "ai_action_versions"
    __table_args__ = (
        Index("ix_ai_action_project_created", "project_id", "created_at"),
        Index("ix_ai_action_entity_created", "entity_type", "entity_id", "created_at"),
        UniqueConstraint("actor_user_id", "request_id", name="uq_ai_action_actor_request"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    voice_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_action_versions.id", ondelete="RESTRICT"), nullable=True
    )
    reverted_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_action_versions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    original_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_interpretation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    final_command: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    before_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approval_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    result: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    undo_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="MANUAL_REVIEW", server_default="MANUAL_REVIEW")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class DomainEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_domain_event_project_idempotency"),
        Index("ix_domain_event_status_created", "status", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", server_default="PENDING")
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AIProviderCall(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_provider_calls"
    __table_args__ = (Index("ix_ai_provider_project_created", "project_id", "created_at"),)

    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    voice_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voice_analyses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
