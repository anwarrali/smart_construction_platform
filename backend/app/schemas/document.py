from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.enums import DocumentType, MediaType
from app.schemas.user import CamelModel, UserOut

class DocumentBase(CamelModel):
    title: str
    document_type: DocumentType = DocumentType.OTHER
    file_url: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    version: int = 1
    notes: Optional[str] = None

class DocumentCreate(CamelModel):
    project_id: UUID
    task_id: Optional[UUID] = None
    title: str
    document_type: DocumentType = DocumentType.OTHER
    file_url: str
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    notes: Optional[str] = None

class DocumentOut(DocumentBase):
    id: UUID
    project_id: UUID
    task_id: Optional[UUID] = None
    uploaded_by_id: UUID
    uploaded_by: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime

class MediaAssetBase(CamelModel):
    media_type: MediaType = MediaType.IMAGE
    file_url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    project_stage: Optional[str] = None
    file_size_bytes: Optional[int] = None

class MediaAssetCreate(MediaAssetBase):
    project_id: UUID
    task_id: Optional[UUID] = None
    site_report_id: Optional[UUID] = None

class MediaAssetOut(MediaAssetBase):
    id: UUID
    project_id: UUID
    task_id: Optional[UUID] = None
    site_report_id: Optional[UUID] = None
    uploaded_by_id: UUID
    created_at: datetime
    updated_at: datetime
