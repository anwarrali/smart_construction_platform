"""Accountable project communication and multi-project field coordination."""

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OwnerRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "owner_requests"
    __table_args__ = (
        Index("ix_owner_requests_project_status_priority", "project_id", "status", "priority"),
        Index("ix_owner_requests_assignee_status", "assigned_to_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    floor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    room: Mapped[str | None] = mapped_column(String(120), nullable=True)
    related_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="NORMAL", server_default="NORMAL", index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="SUBMITTED", server_default="SUBMITTED", index=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    converted_design_change_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("design_changes.id", ondelete="SET NULL"), nullable=True, unique=True)

    project: Mapped["Project"] = relationship()
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])


class MessageRecipientState(Base, UUIDPrimaryKeyMixin):
    """Per-recipient read/acknowledgement/response state; opening is not acknowledgement."""
    __tablename__ = "message_recipient_states"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_recipient_state"),
        Index("ix_message_recipient_action", "user_id", "response_status"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNREAD", server_default="UNREAD", index=True)
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    message: Mapped["Message"] = relationship()


class ReminderRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reminder_rules"
    __table_args__ = (UniqueConstraint("project_id", "target_type", "priority", name="uq_reminder_rule_scope"),)

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, default="IMPORTANT_COMMUNICATION", server_default="IMPORTANT_COMMUNICATION")
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    first_reminder_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    repeat_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_reminders: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    escalation_recipient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class ReminderEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "reminder_events"
    __table_args__ = (Index("ix_reminder_events_target_created", "target_type", "target_id", "created_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reminder_rules.id", ondelete="SET NULL"), nullable=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class SiteVisit(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "site_visits"
    __table_args__ = (
        CheckConstraint("scheduled_end > scheduled_start", name="ck_site_visit_time_order"),
        Index("ix_site_visits_engineer_start", "engineer_id", "scheduled_start"),
        Index("ix_site_visits_project_start", "project_id", "scheduled_start"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    engineer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visit_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location: Mapped[str | None] = mapped_column(String(250), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="SCHEDULED", server_default="SCHEDULED", index=True)
    reschedule_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list["SiteVisitParticipant"]] = relationship(back_populates="visit", cascade="all, delete-orphan")


class SiteVisitParticipant(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "site_visit_participants"
    __table_args__ = (UniqueConstraint("site_visit_id", "user_id", name="uq_site_visit_participant"),)

    site_visit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site_visits.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    response_status: Mapped[str] = mapped_column(String(20), nullable=False, default="INVITED", server_default="INVITED")
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    visit: Mapped[SiteVisit] = relationship(back_populates="participants")


class AIInsightSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Normalized traceability and validity state for an AI insight source."""
    __tablename__ = "ai_insight_sources"
    __table_args__ = (
        UniqueConstraint("insight_id", "source_type", "source_id", name="uq_ai_insight_source"),
        Index("ix_ai_insight_source_entity", "source_type", "source_id"),
    )

    insight_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_insights.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(250), nullable=True)
    source_state: Mapped[str] = mapped_column(String(30), nullable=False, default="RAW", server_default="RAW")
    source_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
