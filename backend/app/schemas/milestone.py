from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.user import CamelModel


class MilestoneCreate(CamelModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=250)
    description: Optional[str] = Field(default=None, max_length=4000)
    planned_date: date
    task_ids: List[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_tasks(self):
        if len(self.task_ids) != len(set(self.task_ids)):
            raise ValueError("Duplicate milestone task links are not allowed")
        return self


class MilestoneUpdate(CamelModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=250)
    description: Optional[str] = Field(default=None, max_length=4000)
    planned_date: Optional[date] = None
    actual_date: Optional[date] = None
    task_ids: Optional[List[UUID]] = None

    @model_validator(mode="after")
    def unique_tasks(self):
        if self.task_ids is not None and len(self.task_ids) != len(set(self.task_ids)):
            raise ValueError("Duplicate milestone task links are not allowed")
        return self


class MilestoneOut(CamelModel):
    id: UUID
    project_id: UUID
    milestone_code: str
    name: str
    description: Optional[str] = None
    planned_date: date
    actual_date: Optional[date] = None
    status: str
    progress_percentage: float
    task_count: int
    completed_task_count: int
    task_ids: List[UUID]
    created_by_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
