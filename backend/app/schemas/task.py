from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from app.models.enums import (
    TaskStatus,
    TaskPriority,
    DependencyType,
    RescheduleReason,
    IssueSeverity,
)
from app.schemas.user import CamelModel, UserOut
from app.core.schedule_dates import inclusive_duration_days

class TaskDependencyBase(CamelModel):
    task_id: UUID
    depends_on_task_id: UUID
    dependency_type: DependencyType = DependencyType.FINISH_TO_START
    lag_days: int = 0

class TaskDependencyCreate(CamelModel):
    depends_on_task_id: UUID
    dependency_type: DependencyType = DependencyType.FINISH_TO_START
    lag_days: int = 0

class TaskDependencyOut(TaskDependencyBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    depends_on_task_code: Optional[str] = None
    depends_on_task_name: Optional[str] = None
    depends_on_task_status: Optional[TaskStatus] = None

class TaskRescheduleLogOut(CamelModel):
    id: UUID
    task_id: UUID
    triggered_by_task_id: Optional[UUID] = None
    triggered_by_user_id: Optional[UUID] = None
    reason: RescheduleReason
    notes: Optional[str] = None
    previous_start_date: Optional[date] = None
    previous_end_date: Optional[date] = None
    new_start_date: Optional[date] = None
    new_end_date: Optional[date] = None
    shift_days: int
    is_automatic: bool
    created_at: datetime

class TaskBase(CamelModel):
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    discipline: Optional[str] = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    duration_days: Optional[int] = Field(default=None, ge=1)
    progress_percentage: float = Field(default=0.0, ge=0, le=100)
    is_critical_path: bool = False
    is_milestone: bool = False
    total_float_days: Optional[int] = None

class TaskCreate(CamelModel):
    project_id: UUID
    name: str
    description: Optional[str] = None
    discipline: Optional[str] = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_ids: List[UUID] = Field(default_factory=list)
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    is_milestone: bool = False
    dependency_ids: List[UUID] = Field(default_factory=list)
    milestone_id: Optional[UUID] = None
    review_required: bool = True
    review_due_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.planned_start_date and self.planned_end_date:
            inclusive_duration_days(self.planned_start_date, self.planned_end_date)
        return self

    @model_validator(mode="after")
    def validate_unique_dependencies(self):
        if len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ValueError("Duplicate task dependencies are not allowed")
        return self

    @model_validator(mode="after")
    def validate_unique_assignees(self):
        if len(self.assignee_ids) != len(set(self.assignee_ids)):
            raise ValueError("Duplicate task assignees are not allowed")
        return self

class TaskUpdate(CamelModel):
    name: Optional[str] = None
    description: Optional[str] = None
    discipline: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee_ids: Optional[List[UUID]] = None
    planned_start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    progress_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    is_critical_path: Optional[bool] = None
    is_milestone: Optional[bool] = None
    total_float_days: Optional[int] = None
    dependency_ids: Optional[List[UUID]] = None
    milestone_id: Optional[UUID] = None
    review_required: Optional[bool] = None
    review_due_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_complete_date_range(self):
        if self.planned_start_date and self.planned_end_date:
            inclusive_duration_days(self.planned_start_date, self.planned_end_date)
        return self

    @model_validator(mode="after")
    def validate_unique_dependencies(self):
        if self.dependency_ids is not None and len(self.dependency_ids) != len(set(self.dependency_ids)):
            raise ValueError("Duplicate task dependencies are not allowed")
        return self


    @model_validator(mode="after")
    def validate_unique_assignees(self):
        if self.assignee_ids is not None and len(self.assignee_ids) != len(set(self.assignee_ids)):
            raise ValueError("Duplicate task assignees are not allowed")
        return self


class TaskReviewRequest(CamelModel):
    comments: Optional[str] = None
    rejection_reason: Optional[str] = None
    required_corrections: Optional[str] = None


class TaskReviewSubmission(CamelModel):
    completion_note: Optional[str] = Field(default=None, max_length=4000)


class TaskClarificationRequest(CamelModel):
    question: str = Field(..., min_length=3, max_length=4000)


class TaskClarificationResponse(CamelModel):
    response: str = Field(..., min_length=3, max_length=4000)


class TaskProgressUpdate(CamelModel):
    progress_percentage: float = Field(..., ge=0, le=100)
    note: Optional[str] = Field(default=None, max_length=2000)


class TaskWorkUpdateCreate(CamelModel):
    progress_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    work_completed_today: str = Field(..., min_length=1, max_length=4000)
    remaining_work: Optional[str] = Field(default=None, max_length=2000)
    workers_count: Optional[int] = Field(default=None, ge=0, le=100000)
    equipment_used: Optional[str] = Field(default=None, max_length=2000)
    materials_used: Optional[str] = Field(default=None, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=2000)
    problems_encountered: Optional[str] = Field(default=None, max_length=2000)


class TaskBlockerCreate(CamelModel):
    category: str = Field(..., min_length=2, max_length=80)
    description: str = Field(..., min_length=3, max_length=4000)
    severity: IssueSeverity = IssueSeverity.MEDIUM

class TaskCommentCreate(CamelModel):
    content: str = Field(..., min_length=1, max_length=4000)

class TaskCommentOut(CamelModel):
    id: UUID
    task_id: UUID
    author_id: UUID
    content: str
    author: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime

class TaskReviewOut(CamelModel):
    id: UUID
    task_id: UUID
    submitted_by_id: Optional[UUID] = None
    reviewed_by_id: Optional[UUID] = None
    status: str
    comments: Optional[str] = None
    rejection_reason: Optional[str] = None
    required_corrections: Optional[str] = None
    completion_note: Optional[str] = None
    submission_number: int = 1
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    clarification_question: Optional[str] = None
    clarification_response: Optional[str] = None
    clarification_requested_at: Optional[datetime] = None
    clarification_responded_at: Optional[datetime] = None
    evidence_snapshot: Optional[str] = None
    resubmission_of_id: Optional[UUID] = None
    submitted_by: Optional[UserOut] = None
    reviewed_by: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime

class TaskOut(TaskBase):
    id: UUID
    task_code: str
    project_id: UUID
    milestone_id: Optional[UUID] = None
    created_by_id: UUID
    created_by: Optional[UserOut] = None
    assignee_ids: List[UUID] = Field(default_factory=list)
    assignees: List[UserOut] = Field(default_factory=list)
    submitted_for_review_at: Optional[date] = None
    reviewed_at: Optional[date] = None
    reviewed_by_id: Optional[UUID] = None
    consultant_comments: Optional[str] = None
    rejection_reason: Optional[str] = None
    review_status: Optional[str] = None
    review_required: bool = True
    review_due_date: Optional[date] = None
    dependencies: List[TaskDependencyOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def calculate_inclusive_duration(self):
        if self.planned_start_date and self.planned_end_date:
            self.duration_days = inclusive_duration_days(self.planned_start_date, self.planned_end_date)
        else:
            self.duration_days = None
        return self

class TaskReorderRequest(CamelModel):
    task_ids: List[UUID]

class TaskAnalytics(CamelModel):
    total_tasks: int
    todo_tasks: int
    in_progress_tasks: int
    under_review_tasks: int
    rework_required_tasks: int
    done_tasks: int
    blocked_tasks: int
    critical_path_tasks_count: int
    completion_rate: float
