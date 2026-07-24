from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.enums import IssueSeverity, IssueStatus
from app.schemas.user import CamelModel, UserOut

class IssueBase(CamelModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[date] = None
    affects_schedule: bool = False
    resolved_at: Optional[datetime] = None
    severity: IssueSeverity = IssueSeverity.MEDIUM
    status: IssueStatus = IssueStatus.OPEN
    resolution_notes: Optional[str] = None

class IssueCreate(CamelModel):
    project_id: UUID
    task_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[date] = None
    affects_schedule: bool = False
    severity: IssueSeverity = IssueSeverity.MEDIUM
    assigned_to_id: Optional[UUID] = None

class IssueUpdate(CamelModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[date] = None
    affects_schedule: Optional[bool] = None
    severity: Optional[IssueSeverity] = None
    status: Optional[IssueStatus] = None
    assigned_to_id: Optional[UUID] = None
    resolution_notes: Optional[str] = None

class IssueOut(IssueBase):
    id: UUID
    project_id: UUID
    task_id: Optional[UUID] = None
    raised_by_id: UUID
    assigned_to_id: Optional[UUID] = None
    raised_by: Optional[UserOut] = None
    assigned_to: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime
    attachment_count: int = 0
