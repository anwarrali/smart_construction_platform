"""One row per unit of background work: the durable job queue.

Heavy work — IFC parsing and geometry, file ingestion, RAG indexing, automatic
agent analysis — used to run on an in-memory thread pool inside the web
process. Work queued there vanished on any restart, and the pool's ceiling was
per process, so two uvicorn workers meant twice the intended memory bound.

A row here is the job. It is inserted in the same transaction as the upload or
event that causes it, so a job exists exactly when its cause committed, and it
survives a restart. Workers claim rows with `FOR UPDATE SKIP LOCKED`; see
`app.services.jobs`.

The domain rows (`ifc_model_versions`, `ingested_files`, …) stay the authority
on their own progress. This table only answers "has this work been handed to a
worker, and did the worker finish".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

STATUS_QUEUED = "QUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
#: Raised every attempt it was allowed. Not retried again.
STATUS_FAILED = "FAILED"
#: Not a known kind on this deployment, or its payload could not be read.
STATUS_REJECTED = "REJECTED"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

#: One live job per dedupe key. A partial unique index rather than a check in
#: code, for the reason `rag_index_jobs` gives: two requests would both read
#: "nothing queued" before either wrote, and the work would run twice.
ACTIVE_DEDUPE_INDEX = "ix_background_jobs_one_active_per_key"


class BackgroundJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index(
            ACTIVE_DEDUPE_INDEX, "queue", "dedupe_key", unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING') AND dedupe_key IS NOT NULL"),
        ),
        # What a worker scans: queued work in its queue, oldest due first.
        Index("ix_background_jobs_claim", "queue", "status", "run_after"),
    )

    #: Which workers may take it. Lets a test session, or a separate tier,
    #: share the database without taking each other's work.
    queue: Mapped[str] = mapped_column(String(60), nullable=False, default="default", server_default="default")
    #: Registered handler name, e.g. `ifc.process_version`.
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_QUEUED, server_default=STATUS_QUEUED)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: For visibility and cleanup; nothing about running a job reads it.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    #: Not before. A retry is pushed back by a growing delay.
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    #: Which worker holds it, since when, and when it last said it was alive.
    #: A running job whose heartbeat is older than JOB_STALE_SECONDS belonged
    #: to a worker that died; the reaper hands it back.
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES
