import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import EvidencePhotoDirection, FieldSubmissionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FieldSubmission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A Worker's field evidence package awaiting Contractor Engineer review."""

    __tablename__ = "field_submissions"
    __table_args__ = (
        Index(
            "ix_field_submissions_project_status_created",
            "project_id", "status", "created_at",
        ),
        Index("ix_field_submissions_task_status", "task_id", "status"),
        Index("ix_field_submissions_worker_created", "worker_id", "created_at"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[FieldSubmissionStatus] = mapped_column(
        PG_ENUM(FieldSubmissionStatus, name="field_submission_status", create_type=True),
        nullable=False,
        default=FieldSubmissionStatus.SUBMITTED,
        server_default=FieldSubmissionStatus.SUBMITTED.name,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    resubmission_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_submissions.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship()
    task: Mapped["Task"] = relationship()
    worker: Mapped["User"] = relationship(foreign_keys=[worker_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    photos: Mapped[list["FieldSubmissionPhoto"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="FieldSubmissionPhoto.created_at"
    )


class FieldSubmissionPhoto(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Field-specific metadata linked to the canonical Attachment file record."""

    __tablename__ = "field_submission_photos"
    __table_args__ = (
        UniqueConstraint("attachment_id", name="uq_field_submission_photo_attachment"),
        Index("ix_field_submission_photos_created_at", "created_at"),
    )

    field_submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_submissions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    direction: Mapped[EvidencePhotoDirection | None] = mapped_column(
        PG_ENUM(EvidencePhotoDirection, name="evidence_photo_direction", create_type=True),
        nullable=True,
    )
    ai_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission: Mapped["FieldSubmission"] = relationship(back_populates="photos")
    attachment: Mapped["Attachment"] = relationship()
    category_assignments: Mapped[list["PhotoCategoryAssignment"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan"
    )

    @property
    def categories(self) -> list["PhotoCategory"]:
        return [assignment.category for assignment in self.category_assignments]


class PhotoCategory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Global defaults or a project-owned category without duplicating system rows."""

    __tablename__ = "photo_categories"
    __table_args__ = (
        Index(
            "uq_photo_categories_system_code", "code", unique=True,
            postgresql_where=text("project_id IS NULL"),
        ),
        Index(
            "uq_photo_categories_project_code", "project_id", "code", unique=True,
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        Index("ix_photo_categories_project_active", "project_id", "active"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project | None"] = relationship(back_populates="photo_categories")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    photo_assignments: Mapped[list["PhotoCategoryAssignment"]] = relationship(
        back_populates="category"
    )


class PhotoCategoryAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Category provenance. AI fields remain dormant until a later intelligence feature."""

    __tablename__ = "photo_category_assignments"
    __table_args__ = (
        UniqueConstraint(
            "field_submission_photo_id", "category_id",
            name="uq_photo_category_assignment",
        ),
        Index("ix_photo_category_assignments_category_photo", "category_id", "field_submission_photo_id"),
    )

    field_submission_photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_submission_photos.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("photo_categories.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="HUMAN", server_default="HUMAN"
    )
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    ai_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    photo: Mapped["FieldSubmissionPhoto"] = relationship(back_populates="category_assignments")
    category: Mapped["PhotoCategory"] = relationship(back_populates="photo_assignments")
    assigned_by: Mapped["User | None"] = relationship(foreign_keys=[assigned_by_id])
