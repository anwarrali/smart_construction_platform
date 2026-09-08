
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentType, MediaType


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "documents"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(250), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        PG_ENUM(DocumentType, name="document_type", create_type=True),
        nullable=False,
        default=DocumentType.OTHER,
        server_default=DocumentType.OTHER.name,
        index=True,
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- RAG indexing state -------------------------------------------------
    # A document is only queryable when `index_status` is READY. Every other
    # value — including a run that died halfway — makes retrieval refuse it,
    # so a partial index is unreachable by construction rather than by
    # convention. See `services/rag/ingestion.py`.

    #: NOT_INDEXED | INDEXING | READY | FAILED.
    #: A plain string rather than a PG enum, matching `notifications.category`:
    #: naming a new state should not require an enum migration.
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
    index_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- File intelligence --------------------------------------------------
    # `document_type` above is the uploader's choice and stays authoritative.
    # These record what the file itself turned out to be, so a bill of
    # quantities filed as "other" is still findable, and so a disagreement
    # between the two can be surfaced instead of silently resolved.
    # See `services/file_intelligence.py`.

    #: The format its bytes actually are: PDF, DWG, XLSX, IFC…
    detected_format: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    #: What classification thinks the document is. Advisory, never enforced.
    suggested_document_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    #: Confidence, source, evidence and what else was considered.
    classification_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    project: Mapped["Project"] = relationship(back_populates="documents")
    task: Mapped["Task"] = relationship()
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])
    #: Deleting a document must not orphan its indexed text. The FK cascades
    #: in the database; `passive_deletes` stops the ORM trying to nullify a
    #: NOT NULL column first.
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} title={self.title} type={self.document_type}>"


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Progress documentation media — images/videos uploaded by Contractor or Engineer,
    linked to a specific task and/or site report.
    """

    __tablename__ = "media_assets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site_reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    media_type: Mapped[MediaType] = mapped_column(
        PG_ENUM(MediaType, name="media_type", create_type=True),
        nullable=False,
        default=MediaType.IMAGE,
        server_default=MediaType.IMAGE.name,
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    project_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # e.g. "Foundation", "Floor 12 slab pour" — free-text stage label

    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    project: Mapped["Project"] = relationship()
    task: Mapped["Task"] = relationship(back_populates="media_assets")
    site_report: Mapped["SiteReport"] = relationship(back_populates="media_assets")
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])

    def __repr__(self) -> str:
        return f"<MediaAsset id={self.id} type={self.media_type}>"