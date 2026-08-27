"""The record of an agent having run.

Phase 6 produced findings but kept the run itself in memory, so afterwards
there was no way to answer the questions that matter when a finding is
disputed: which agent produced it, what made it run, what it actually looked
at, and whether other agents succeeded in the same pass.

A finding is reviewable on its own. A *run* is what makes the finding
accountable — and the two need to be separable, because an agent that ran and
found nothing is a meaningful outcome that leaves no `AIInsight` behind.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_run_project_agent_created", "project_id", "agent_name", "created_at"),
        Index("ix_agent_run_status_created", "status", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    #: MANUAL — a person asked. EVENT — a domain event matched a subscription.
    #: Recorded because "why did this appear in my queue?" is the first question
    #: a reviewer asks about a finding they did not request.
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL",
                                              server_default="MANUAL", index=True)
    #: The event that caused this run, when one did. Null for a manual run.
    trigger_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_events.id", ondelete="SET NULL"), nullable=True
    )
    #: In words: "a document was uploaded", "requested by a project manager".
    trigger_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Whose authority the run used. Every tool call was checked against this
    #: person, so the run cannot have seen more than they can.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    #: SUCCEEDED | FAILED | SKIPPED. SKIPPED is not a failure: it is an agent
    #: correctly declining to run, and conflating the two would make a healthy
    #: pass look broken.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="SUCCEEDED",
                                        server_default="SUCCEEDED", index=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Every tool the agent called, in order, with whether it succeeded. The
    #: agent's reasoning is only reviewable if what it looked at is known.
    tool_calls_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list,
                                                  server_default="[]")
    #: Finding codes produced, and the insights they were stored as.
    finding_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list,
                                                     server_default="[]")
    insight_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list,
                                                   server_default="[]")
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: Highest confidence among the findings, so a queue can be sorted without
    #: reopening each one.
    highest_confidence: Mapped[float | None] = mapped_column(nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AgentRun {self.agent_name} {self.status} findings={self.finding_count}>"
