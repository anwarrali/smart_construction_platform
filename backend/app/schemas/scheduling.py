from datetime import date
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

class TaskDependencySchema(BaseModel):
    task_id: UUID
    depends_on_task_id: UUID
    dependency_type: str
    lag_days: int

class GanttTaskSchema(BaseModel):
    id: UUID
    task_code: str
    name: str
    start: Optional[date] = None
    end: Optional[date] = None
    progress: float
    dependencies: List[str]  # string IDs of depends_on_task_id
    type: str = "task"
    is_critical: bool = False
    status: str
    priority: str
    duration_days: Optional[int] = None
    total_float_days: Optional[int] = None
    is_disabled: bool = False

    class Config:
        from_attributes = True

class GanttDataResponse(BaseModel):
    tasks: List[GanttTaskSchema]

class ShiftTaskRequest(BaseModel):
    task_id: UUID
    shift_days: int
    reason: Optional[str] = "MANUAL"
    notes: Optional[str] = None
