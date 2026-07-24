from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.models.enums import EvidencePhotoDirection, FieldSubmissionStatus
from app.schemas.attachment import AttachmentOut
from app.schemas.user import CamelModel, UserOut


class PhotoCategoryOut(CamelModel):
    id: UUID
    name: str
    code: str
    project_id: Optional[UUID] = None
    is_system: bool
    active: bool
    created_by_id: Optional[UUID] = None
    created_at: datetime


class FieldSubmissionPhotoOut(CamelModel):
    id: UUID
    field_submission_id: UUID
    attachment_id: UUID
    direction: Optional[EvidencePhotoDirection] = None
    categories: list[PhotoCategoryOut] = Field(default_factory=list)
    attachment: AttachmentOut
    created_at: datetime


class FieldSubmissionOut(CamelModel):
    id: UUID
    project_id: UUID
    task_id: UUID
    worker_id: UUID
    description: Optional[str] = None
    voice_metadata: Optional[str] = None
    status: FieldSubmissionStatus
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[UUID] = None
    review_comment: Optional[str] = None
    resubmission_of_id: Optional[UUID] = None
    worker: UserOut
    reviewed_by: Optional[UserOut] = None
    photos: list[FieldSubmissionPhotoOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FieldSubmissionReview(CamelModel):
    comment: Optional[str] = Field(default=None, max_length=2000)


class FieldSubmissionRejection(CamelModel):
    reason: str = Field(min_length=3, max_length=2000)


class PhotoCategoryCreate(CamelModel):
    name: str = Field(min_length=2, max_length=100)


class PhotoCategoryUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    active: Optional[bool] = None


class PhotoCategoryReplace(CamelModel):
    category_ids: list[UUID] = Field(default_factory=list, max_length=20)


class EvidencePhotoArchiveItem(CamelModel):
    id: UUID
    field_submission_id: UUID
    project_id: UUID
    task_id: UUID
    task_code: str
    task_title: str
    discipline: Optional[str] = None
    worker_id: UUID
    worker_name: str
    uploader_id: UUID
    uploader_name: str
    submission_status: FieldSubmissionStatus
    submission_created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[UUID] = None
    reviewer_name: Optional[str] = None
    direction: Optional[EvidencePhotoDirection] = None
    categories: list[PhotoCategoryOut] = Field(default_factory=list)
    attachment: AttachmentOut


class EvidencePhotoArchivePage(CamelModel):
    items: list[EvidencePhotoArchiveItem]
    page: int
    page_size: int
    total: int
    total_pages: int
