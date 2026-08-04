from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import NotificationType, NotificationStatus
from app.schemas.user import CamelModel

class NotificationOut(CamelModel):
    id: UUID
    user_id: UUID
    title: str
    message: str
    type: NotificationType
    status: NotificationStatus
    is_read: bool
    project_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[UUID] = None
    category: str = "SYSTEM"
    requires_action: bool = False
    action_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class NotificationResponse(CamelModel):
    items: list[NotificationOut]
    total: int
    page: int
    limit: int
    total_pages: int
