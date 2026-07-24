from datetime import datetime
from typing import Optional
from uuid import UUID

from app.schemas.user import CamelModel, UserOut


class AttachmentOut(CamelModel):
    id: UUID
    original_filename: str
    storage_key: str
    file_url: str
    mime_type: str
    file_size_bytes: int
    uploaded_by_id: UUID
    project_id: UUID
    entity_type: str
    entity_id: UUID
    uploaded_by: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime
