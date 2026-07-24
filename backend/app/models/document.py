
import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
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

    project: Mapped["Project"] = relationship(back_populates="documents")
    task: Mapped["Task"] = relationship()
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])

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