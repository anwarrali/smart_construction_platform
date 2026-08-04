from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pydantic.alias_generators import to_camel
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from app.models.enums import ConsultantApprovalMode, ProjectStatus, UserRole, EngineerDiscipline
from app.schemas.user import UserOut, CamelModel

class ProjectMemberBase(CamelModel):
    user_id: UUID
    role_on_project: UserRole
    is_active: bool = True

class ProjectMemberCreate(CamelModel):
    user_id: UUID
    role_on_project: UserRole

class ProjectMemberOut(CamelModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    role_on_project: UserRole
    is_active: bool
    assignment_title: Optional[str] = None
    project_discipline: Optional[str] = None
    project_notes: Optional[str] = None
    is_site_engineer: bool = False
    assigned_by_id: Optional[UUID] = None
    user: Optional[UserOut] = None
    created_at: datetime
    updated_at: datetime

class ProjectBase(CamelModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    project_type: Optional[str] = None
    status: ProjectStatus = ProjectStatus.PLANNING
    start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    budget_total: Optional[float] = None
    budget_spent: Optional[float] = 0.0
    completion_percentage: float = 0.0
    cover_image_url: Optional[str] = None

class ProjectCreate(CamelModel):
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    project_type: Optional[str] = None
    status: ProjectStatus = ProjectStatus.PLANNING
    start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    budget_total: Optional[float] = Field(default=None, ge=0)
    owner_id: Optional[UUID] = None
    project_manager_id: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.planned_end_date and self.planned_end_date < self.start_date:
            raise ValueError("Planned end date must be on or after start date")
        return self


class ProjectMemberAssignExisting(CamelModel):
    user_id: UUID
    role_on_project: UserRole
    assignment_title: Optional[str] = None
    project_discipline: Optional[EngineerDiscipline] = None
    project_notes: Optional[str] = Field(default=None, max_length=1000)
    is_site_engineer: bool = False


class ProjectMemberAssignmentUpdate(CamelModel):
    assignment_title: Optional[str] = None
    is_site_engineer: Optional[bool] = None
    project_discipline: Optional[EngineerDiscipline] = None
    project_notes: Optional[str] = Field(default=None, max_length=1000)


class ProjectMemberTransfer(CamelModel):
    target_project_id: UUID
    is_site_engineer: bool = False


class ProjectApprovalConfigUpdate(CamelModel):
    mode: ConsultantApprovalMode
    centralized_reviewer_id: Optional[UUID] = None
    discipline_reviewers: dict[str, List[UUID]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_reviewers(self):
        if self.mode == ConsultantApprovalMode.CENTRALIZED_REVIEW:
            if not self.centralized_reviewer_id:
                raise ValueError("A centralized Consultant reviewer is required")
            if self.discipline_reviewers:
                raise ValueError("Discipline reviewers are not valid in centralized review mode")
        elif not any(self.discipline_reviewers.values()):
            raise ValueError("At least one discipline reviewer is required")
        return self


class ProjectConsultantReviewerOut(CamelModel):
    id: UUID
    user_id: UUID
    discipline: Optional[str] = None
    user: UserOut


class ProjectApprovalConfigOut(CamelModel):
    project_id: UUID
    mode: ConsultantApprovalMode
    centralized_reviewer_id: Optional[UUID] = None
    discipline_reviewers: dict[str, List[UUID]] = Field(default_factory=dict)
    reviewers: List[ProjectConsultantReviewerOut] = Field(default_factory=list)


class ProjectMemberCreateEngineer(CamelModel):
    full_name: str
    email: EmailStr
    phone_number: str
    discipline: EngineerDiscipline = EngineerDiscipline.CIVIL
    employee_id: Optional[str] = None


class ProjectMemberCreateOwner(CamelModel):
    full_name: str
    email: EmailStr
    phone_number: str
    organization: Optional[str] = None

class ProjectUpdate(CamelModel):
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    project_type: Optional[str] = None
    status: Optional[ProjectStatus] = None
    start_date: Optional[date] = None
    planned_end_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    budget_total: Optional[float] = None
    budget_spent: Optional[float] = None
    completion_percentage: Optional[float] = None
    owner_id: Optional[UUID] = None
    project_manager_id: Optional[UUID] = None
    cover_image_url: Optional[str] = None

class ProjectOut(ProjectBase):
    id: UUID
    owner_id: Optional[UUID] = None
    project_manager_id: Optional[UUID] = None
    consultant_approval_mode: ConsultantApprovalMode
    members: List[ProjectMemberOut] = []
    open_issue_count: int = 0
    created_at: datetime
    updated_at: datetime

class ProjectsListResponse(CamelModel):
    data: List[ProjectOut]
    total: int
    page: int
    limit: int
    total_pages: int

class ProjectSummary(CamelModel):
    total_projects: int
    active_projects: int
    completed_projects: int
    delayed_projects: int
    average_completion: float
    total_budget: float
    total_spent: float

class MilestoneOut(CamelModel):
    id: UUID
    name: str
    planned_date: Optional[date]
    actual_date: Optional[date] = None
    status: str

class RecentActivityOut(CamelModel):
    id: UUID
    type: str
    description: str
    timestamp: datetime
    user: str

class RecentPhotoOut(CamelModel):
    id: UUID
    url: str
    caption: Optional[str]
    task_name: Optional[str]
    uploaded_at: datetime

class CostSummaryOut(CamelModel):
    project_id: UUID
    budget_total: float
    budget_spent: float
    committed_cost: float
    pending_cost: float
    variance: float
    variance_percentage: float
    updated_at: datetime

class OwnerDashboardOut(CamelModel):
    project_summary: dict
    cost_summary: CostSummaryOut
    milestones: List[MilestoneOut] = []
    recent_activities: List[RecentActivityOut] = []
    recent_photos: List[RecentPhotoOut] = []
    project_health: str
    delayed_tasks: List[dict] = []
    open_issues: List[dict] = []
    attention_required: List[dict] = []
    project_breakdown: List[dict] = []
    design_changes: List[dict] = []
    consultant_approvals: dict = {}
    latest_executive_updates: List[dict] = []
    pending_owner_requests: List[dict] = []
    upcoming_site_visits: List[dict] = []
    recent_verified_site_reports: List[dict] = []
    since_last_visit: dict = {}
