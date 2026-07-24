from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.enums import DesignChangeStatus
from app.schemas.user import CamelModel, UserOut

class DesignChangeAffectedDisciplineBase(CamelModel):
    discipline: str
    acknowledged: bool = False
    acknowledged_by_id: Optional[UUID] = None

class DesignChangeAffectedDisciplineOut(DesignChangeAffectedDisciplineBase):
    id: UUID
    design_change_id: UUID
    acknowledged_by: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime

class DesignChangeBase(CamelModel):
    title: str
    description: Optional[str] = None
    reason: Optional[str] = None
    related_drawings: Optional[str] = None
    expected_cost_impact: Optional[float] = None
    expected_schedule_impact_days: Optional[int] = None
    review_notes: Optional[str] = None
    source_discipline: str
    status: DesignChangeStatus = DesignChangeStatus.PROPOSED

class DesignChangeCreate(CamelModel):
    project_id: UUID
    task_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    reason: Optional[str] = None
    related_drawings: Optional[str] = None
    expected_cost_impact: Optional[float] = None
    expected_schedule_impact_days: Optional[int] = None
    source_discipline: str
    affected_disciplines: List[str]

class DesignChangeOut(DesignChangeBase):
    id: UUID
    project_id: UUID
    task_id: Optional[UUID] = None
    proposed_by_id: UUID
    approved_by_id: Optional[UUID] = None
    proposed_by: Optional[UserOut] = None
    approved_by: Optional[UserOut] = None
    affected_disciplines: List[DesignChangeAffectedDisciplineOut] = []
    created_at: datetime
    updated_at: datetime
    attachment_count: int = 0
