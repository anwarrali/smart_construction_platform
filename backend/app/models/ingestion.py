"""The unified file record: one row per file that entered the platform.

## Why this exists rather than another column on `documents`

Three upload paths grew independently and each owns a model that is right for
its own job and wrong as a general one:

  * `documents.Document` is a *project library entry*. Its `file_url` is a
    public `/uploads/...` URL, and it carries RAG indexing state. It has no
    parent, so a file that arrived inside a ZIP has nowhere to record where it
    came from.
  * `attachment.Attachment` is bound to a domain entity — an issue, a site
    report — by `entity_type`/`entity_id`. A design package belongs to a
    project, not to an entity.
  * `ifc.IFCModelVersion` is a revision of a model group, with version
    numbering, baselines and a comparison graph. Nothing about a PDF fits it.

None of the three can hold package parentage, a shared category vocabulary and
one lifecycle without being distorted into something worse at its own job. So
this table sits *beside* them and points at them: `source_entity_type` /
`source_entity_id` record which subsystem owns the file's domain meaning, and
that subsystem stays authoritative. An IFC upload still produces an
`IFCModelVersion`; this row is how the file becomes visible to a project-wide
file view without the IFC engine being touched.

## What is deliberately not here

No chunks, no embeddings, no extracted-text table. `metadata_json` holds
normalized facts (page count, sheet names, IFC schema) and nothing that belongs
in a retrieval index. RAG 2.0 consumes this record; it is not built into it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IngestedFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ingested_files"
    __table_args__ = (
        Index("ix_ingested_files_project_status", "project_id", "status"),
        Index("ix_ingested_files_project_category", "project_id", "file_category"),
        # Duplicate detection is a lookup, not a constraint — see
        # `duplicate_of_id` below for why this index is not unique.
        Index("ix_ingested_files_project_checksum", "project_id", "checksum_sha256"),
        Index("ix_ingested_files_source", "source_entity_type", "source_entity_id"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    #: The package this file was extracted from, when it did not arrive on its
    #: own. SET NULL rather than CASCADE: deleting a package must not silently
    #: destroy files somebody has since linked to a task.
    parent_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingested_files.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    #: Exactly what the uploader called it, kept for display and for evidence.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The sanitised name the storage key was built from. Never a path.
    normalized_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The MIME type the *client* claimed. A claim, never trusted alone.
    content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    #: What the bytes actually are — PDF, IFC, ZIP_CONTAINER… From
    #: `file_intelligence.identify_format`.
    detected_format: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    #: The normalized `FileCategory` the pipeline dispatches on.
    file_category: Mapped[str] = mapped_column(
        String(30), nullable=False, default="OTHER", server_default="OTHER",
    )
    #: Advisory construction document kind (BOQ, SCHEDULE, DRAWING…). Advisory
    #: in exactly the sense `documents.suggested_document_type` is: a second
    #: opinion that never overwrites a person's choice.
    document_kind: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    classification_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
    )

    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
    )
    #: A key into `services.private_storage`, never a filesystem path, and
    #: never serialised into an API response.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: An earlier file in the same project with identical bytes, when there is
    #: one. Recorded rather than enforced: the IFC subsystem rejects a
    #: duplicate revision because a duplicate revision is meaningless, but a
    #: design package legitimately ships the same title block in six drawings,
    #: and a pipeline that refused them would be unusable. Surfacing the fact
    #: lets each consumer apply its own policy.
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingested_files.id", ondelete="SET NULL"), nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UPLOADED", server_default="UPLOADED", index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: The processor that ran, so a wrong result can be traced to the code that
    #: produced it without guessing from the category.
    processor_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: A code from `services.ingestion.errors`. Safe to publish.
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: The internal detail. Read by operators; never returned by the API.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Normalized extraction output. Shape is per-category and documented by
    #: each processor; the pipeline only guarantees it is a JSON object.
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
    )

    #: Which subsystem owns this file's domain meaning, when one does:
    #: "DOCUMENT", "IFC_MODEL_VERSION", "ATTACHMENT". NULL for a file that
    #: arrived through the unified endpoint and belongs to nothing else yet.
    source_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # --- RAG indexing state -------------------------------------------------
    # The same three columns `documents` carries, holding the same four values
    # from `services/rag/ingestion.py`, driven by the same state machine.
    # Deliberately not a second, subtly different vocabulary: the whole point
    # of putting indexing on this record is that there is eventually *one*
    # answer to "is this file queryable", and two enums is how that becomes
    # two answers.
    #
    # A file is only queryable when `index_status` is READY. Every other
    # value — including a run that died half-way — makes retrieval refuse it,
    # so a partial index is unreachable by construction.

    #: NOT_INDEXED | INDEXING | READY | FAILED.
    index_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_INDEXED",
        server_default="NOT_INDEXED", index=True,
    )
    #: Set only on success, cleared when a re-index begins.
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: When the current run claimed this row. `indexed_at` is set only on
    #: success and `updated_at` moves for any edit, so neither can answer "has
    #: this been INDEXING for an hour" — which is the question the stale-job
    #: reaper asks. Set by `_claim`, cleared when the run settles.
    #: See `services/rag/maintenance.py`.
    index_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Why the last attempt failed, in words a user can act on. NULL when READY.
    #:
    #: Note what this is *not*: a file whose extraction produced no text is
    #: never given an error here, because nothing was attempted. That fact is
    #: already derivable from `metadata_json.extraction`, and writing a failure
    #: for it would make an unindexable file look like a broken one.
    index_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    project: Mapped["Project"] = relationship()
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])
    # `foreign_keys` is required, not decorative: this table has two
    # self-referential foreign keys — the package parent and the duplicate
    # pointer — and SQLAlchemy cannot guess which one a relationship means.
    parent: Mapped["IngestedFile | None"] = relationship(
        back_populates="children", remote_side="IngestedFile.id",
        foreign_keys="IngestedFile.parent_file_id",
    )
    children: Mapped[list["IngestedFile"]] = relationship(
        back_populates="parent", foreign_keys="IngestedFile.parent_file_id",
    )
    jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", passive_deletes=True,
    )
    #: Deleting a file must not orphan its indexed text. The FK cascades in the
    #: database; `passive_deletes` stops the ORM trying to nullify a column the
    #: CHECK constraint forbids being nullified. Same shape as `Document.chunks`.
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="ingested_file", cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<IngestedFile id={self.id} category={self.file_category} status={self.status}>"


class IngestionJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One attempt to process one file.

    Shaped after `ifc.IFCProcessingJob` on purpose, down to the idempotency
    key: the IFC pipeline already established that a job row keyed on
    (file, type, key) is what stops a double-submitted upload from parsing the
    same bytes twice, and reproducing that shape means one thing to learn
    rather than two.
    """

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        UniqueConstraint(
            "file_id", "job_type", "idempotency_key", name="uq_ingestion_job_idempotency",
        ),
        Index("ix_ingestion_jobs_status", "status"),
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingested_files.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    job_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PROCESS", server_default="PROCESS",
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="QUEUED", server_default="QUEUED",
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[IngestedFile] = relationship(back_populates="jobs")

    def __repr__(self) -> str:
        return f"<IngestionJob file={self.file_id} type={self.job_type} status={self.status}>"
