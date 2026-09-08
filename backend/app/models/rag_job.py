"""One row per project-wide re-index run.

## Why a table, and why this one

The platform already has two job tables, and neither fits. `ifc_processing_jobs`
is keyed on an IFC version; `ingestion_jobs` is keyed on an ingested file. Both
are *per-entity*, because the work they record is per-entity. A project
re-index is not: it walks every eligible source in a project, and its
interesting facts — how many were attempted, how many succeeded, how many were
skipped — belong to the run rather than to any one source.

So the shape is copied from `IngestionJob` deliberately, down to the
idempotency key and the attempt counter, and only the scope and the counts
differ. Two job tables that look alike are one thing to learn; two that look
different for no reason are two.

## Duplicate prevention is a database guarantee

`ix_rag_index_jobs_one_active_per_project` is a **partial unique index** over
`project_id` where the status is QUEUED or RUNNING. Two simultaneous requests
therefore cannot both create a run: one of them violates the index and is told
a run is already under way.

A check-then-insert in application code would be a race — the two requests
would both read "no active job" before either wrote one, and the second would
start a second full re-embedding pass over the same project. That is precisely
the expensive duplicate this exists to prevent.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

#: The lifecycle. Deliberately the same words the ingestion pipeline uses for
#: its jobs, so "QUEUED" means the same thing in both places.
STATUS_QUEUED = "QUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
#: Every source was attempted; at least one failed and at least one succeeded.
#: Distinct from FAILED because the successful work is real and kept — see
#: `services/rag/maintenance.py`.
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

#: Statuses that mean a run is still holding this project.
ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)
SETTLED_STATUSES = (STATUS_COMPLETED, STATUS_PARTIAL, STATUS_FAILED)

ACTIVE_JOB_INDEX = "ix_rag_index_jobs_one_active_per_project"


class RagIndexJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rag_index_jobs"
    __table_args__ = (
        Index(
            ACTIVE_JOB_INDEX,
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
        Index("ix_rag_index_jobs_status", "status"),
        Index("ix_rag_index_jobs_project_created", "project_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Who asked for it. RESTRICT, like every other actor column in the schema:
    #: a run with no requester is a record nobody can account for.
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )

    #: STALE | FAILED | ALL — which sources this run was asked to touch. Stored
    #: because "why did this run skip 40 documents" is otherwise unanswerable
    #: after the fact.
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="STALE", server_default="STALE",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_QUEUED,
        server_default=STATUS_QUEUED,
    )
    #: How many times this run has been started. A run recovered from stale
    #: keeps its row and increments this rather than producing a second row,
    #: so the history of one project's re-index is one row per request.
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # --- Counts -------------------------------------------------------------
    # Written as the run progresses, not at the end: a run that dies half-way
    # should still say how far it got.
    total_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    processed_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    succeeded_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: Sources deliberately not attempted — already being indexed by somebody
    #: else, or no longer indexable. Not a failure.
    skipped_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    #: The embedding model this run wrote with, so "which model is this
    #: project's corpus on" is answerable without reading a chunk.
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: A safe, machine-readable code. Published; never carries internal detail.
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: The internal detail, for an operator. Never returned by the API.
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship()
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def __repr__(self) -> str:
        return f"<RagIndexJob project={self.project_id} status={self.status}>"
