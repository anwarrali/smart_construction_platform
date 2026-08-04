from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import String, cast, func, or_
from typing import List, Optional
import uuid
from datetime import date, datetime, timedelta, timezone

from app.db.database import get_db
from app.models.user import User, EngineerProfile
from app.models.enums import (
    UserRole, UserStatus, EngineerDiscipline, CostValidationStatus, MediaType,
    TaskStatus, TaskPriority, IssueStatus, IssueSeverity, ProjectStatus,
    DesignChangeStatus,
)
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember
from app.models.task import Task, TaskReview
from app.models.milestone import Milestone as MilestoneModel
from app.models.cost_validation import CostValidation
from app.models.document import MediaAsset
from app.models.issue import Issue
from app.models.design_change import DesignChange
from app.models.audit_log import AuditLog
from app.models.collaboration import OwnerRequest, SiteVisit
from app.models.site_report import SiteReport
from app.schemas.project import (
    ProjectOut, ProjectCreate, ProjectUpdate, ProjectMemberOut,
    ProjectSummary, ProjectsListResponse, OwnerDashboardOut, CostSummaryOut,
    MilestoneOut, RecentActivityOut, RecentPhotoOut,
    ProjectMemberAssignExisting, ProjectMemberCreateEngineer,
    ProjectMemberCreateOwner,
    ProjectMemberAssignmentUpdate,
    ProjectMemberTransfer,
    ProjectApprovalConfigOut,
    ProjectApprovalConfigUpdate,
)
from app.schemas.user import UserCreateResponse, UserOut
from app.core.deps import (
    get_current_user,
    get_project_or_403,
    get_manageable_project_or_403,
    require_project_creation,
    user_has_project_access,
    is_main_contractor_engineer,
    is_consultant_engineer,
)
from app.core.permissions import can_view_all_projects, is_admin
from app.services.user_service import create_provisioned_user, add_user_to_project
from app.services.audit_service import record_audit
from app.models.notification import Notification
from app.models.enums import NotificationType
from app.services.consultant_approval_service import normalize_discipline

router = APIRouter(prefix="/projects", tags=["Projects"])


def _approval_config_response(project: Project) -> ProjectApprovalConfigOut:
    discipline_reviewers: dict[str, list[uuid.UUID]] = {}
    centralized_reviewer_id = None
    for assignment in project.consultant_reviewer_assignments:
        if assignment.discipline is None:
            centralized_reviewer_id = assignment.user_id
        else:
            discipline_reviewers.setdefault(assignment.discipline, []).append(assignment.user_id)
    return ProjectApprovalConfigOut(
        project_id=project.id,
        mode=project.consultant_approval_mode,
        centralized_reviewer_id=centralized_reviewer_id,
        discipline_reviewers=discipline_reviewers,
        reviewers=project.consultant_reviewer_assignments,
    )


def _remove_reviewer_assignments(
    db: Session, project_id: uuid.UUID, user_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    assignments = db.query(ProjectConsultantReviewer).filter(
        ProjectConsultantReviewer.project_id == project_id,
        ProjectConsultantReviewer.user_id == user_id,
    ).all()
    for assignment in assignments:
        action = (
            "centralized_reviewer_removed"
            if assignment.discipline is None
            else "discipline_reviewer_removed"
        )
        record_audit(
            db, actor_id=actor_id, action=action, entity_type="project",
            entity_id=project_id, project_id=project_id,
            details={"reviewer_id": user_id, "discipline": assignment.discipline},
        )
        db.delete(assignment)


def _scoped_projects_query(db: Session, current_user: User):
    query = db.query(Project)
    if current_user.role == UserRole.PROJECT_MANAGER:
        query = query.filter(Project.project_manager_id == current_user.id)
    elif not can_view_all_projects(current_user.role):
        member_project_ids = db.query(ProjectMember.project_id).filter(
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_active == True,
        ).subquery()
        query = query.filter(
            (Project.owner_id == current_user.id)
            | (Project.project_manager_id == current_user.id)
            | Project.id.in_(member_project_ids)
        )
    if current_user.company_id and current_user.role != UserRole.ADMIN:
        query = query.filter(Project.company_id == current_user.company_id)
    return query


@router.get("", response_model=ProjectsListResponse)
def list_projects(
    status: Optional[str] = None,
    search: Optional[str] = None,
    owner_id: Optional[uuid.UUID] = None,
    project_manager_id: Optional[uuid.UUID] = None,
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.ENGINEER and not (
        is_main_contractor_engineer(current_user) or is_consultant_engineer(current_user)
    ):
        raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    query = _scoped_projects_query(db, current_user)
    if status:
        query = query.filter(Project.status == status)
    if owner_id:
        query = query.filter(Project.owner_id == owner_id)
    if project_manager_id:
        query = query.filter(Project.project_manager_id == project_manager_id)
    if search:
        query = query.filter(Project.name.ilike(f"%{search}%") | Project.description.ilike(f"%{search}%"))

    total = query.count()
    total_pages = max(1, (total + limit - 1) // limit)
    offset = (page - 1) * limit
    projects = query.offset(offset).limit(limit).all()
    if current_user.role in {UserRole.ENGINEER, UserRole.WORKER}:
        for project in projects:
            project.budget_total = None
            project.budget_spent = None
    issue_counts = dict(db.query(Issue.project_id, func.count(Issue.id)).filter(
        Issue.project_id.in_([project.id for project in projects]),
        Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
    ).group_by(Issue.project_id).all()) if projects else {}
    for project in projects:
        project.open_issue_count = issue_counts.get(project.id, 0)

    return ProjectsListResponse(
        data=projects,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/summary", response_model=ProjectSummary)
def get_projects_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role in {UserRole.ENGINEER, UserRole.WORKER}:
        raise HTTPException(status_code=403, detail="Field users cannot access portfolio or financial summaries")
    projects = _scoped_projects_query(db, current_user).all()
    total_projects = len(projects)
    active_projects = sum(1 for p in projects if p.status.value == "active")
    completed_projects = sum(1 for p in projects if p.status.value == "completed")
    delayed_projects = sum(1 for p in projects if p.status.value == "delayed")

    avg_completion = 0.0
    total_budget = 0.0
    total_spent = 0.0

    if total_projects > 0:
        avg_completion = sum(float(p.completion_percentage) for p in projects) / total_projects
        total_budget = sum(float(p.budget_total) for p in projects if p.budget_total)
        total_spent = sum(float(p.budget_spent) for p in projects if p.budget_spent)

    return ProjectSummary(
        total_projects=total_projects,
        active_projects=active_projects,
        completed_projects=completed_projects,
        delayed_projects=delayed_projects,
        average_completion=avg_completion,
        total_budget=total_budget,
        total_spent=total_spent,
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_by_id(
    project: Project = Depends(get_project_or_403),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.ENGINEER and not (
        is_main_contractor_engineer(current_user) or is_consultant_engineer(current_user)
    ):
        raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    if current_user.role in {UserRole.ENGINEER, UserRole.WORKER}:
        project.budget_total = None
        project.budget_spent = None
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_project_creation),
):
    pm_id = project_data.project_manager_id
    if current_user.role == UserRole.PROJECT_MANAGER:
        pm_id = current_user.id
    elif pm_id:
        pm = db.query(User).filter(User.id == pm_id).first()
        if not pm or pm.role != UserRole.PROJECT_MANAGER or pm.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Assigned project manager must be an active Project Manager")

    if project_data.owner_id:
        owner = db.query(User).filter(User.id == project_data.owner_id).first()
        if not owner or owner.role != UserRole.OWNER or owner.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Assigned owner must be an active Owner")

    new_project = Project(
        name=project_data.name,
        description=project_data.description,
        location=project_data.location,
        project_type=project_data.project_type,
        start_date=project_data.start_date,
        planned_end_date=project_data.planned_end_date,
        budget_total=project_data.budget_total,
        budget_spent=0.0,
        completion_percentage=0.0,
        owner_id=project_data.owner_id,
        project_manager_id=pm_id,
        company_id=current_user.company_id,
        status=project_data.status,
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    if new_project.owner_id:
        add_user_to_project(
            db,
            project_id=new_project.id,
            user_id=new_project.owner_id,
            role_on_project=UserRole.OWNER,
        )

    if new_project.project_manager_id:
        add_user_to_project(
            db,
            project_id=new_project.id,
            user_id=new_project.project_manager_id,
            role_on_project=UserRole.PROJECT_MANAGER,
        )

    recipients = {new_project.owner_id, new_project.project_manager_id} - {None, current_user.id}
    for recipient in recipients:
        db.add(Notification(user_id=recipient, title="Project Assignment",
            message=f"You have been assigned to {new_project.name}.", type=NotificationType.SYSTEM,
            project_id=new_project.id, related_entity_type="PROJECT", related_entity_id=new_project.id))
    db.commit()

    db.refresh(new_project)
    return new_project


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    project_data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only administrators can edit project setup")
    project = get_manageable_project_or_403(project_id, db, current_user)

    if project_data.name is not None:
        project.name = project_data.name
    if project_data.description is not None:
        project.description = project_data.description
    if project_data.location is not None:
        project.location = project_data.location
    if project_data.project_type is not None:
        project.project_type = project_data.project_type
    if project_data.status is not None:
        project.status = project_data.status
    if project_data.start_date is not None:
        project.start_date = project_data.start_date
    if project_data.planned_end_date is not None:
        project.planned_end_date = project_data.planned_end_date
    if project_data.actual_end_date is not None:
        project.actual_end_date = project_data.actual_end_date
    if project_data.budget_total is not None:
        project.budget_total = project_data.budget_total
    if project_data.budget_spent is not None:
        project.budget_spent = project_data.budget_spent
    if project_data.completion_percentage is not None:
        project.completion_percentage = project_data.completion_percentage
    if project_data.cover_image_url is not None:
        project.cover_image_url = project_data.cover_image_url

    if project_data.owner_id is not None:
        owner = db.query(User).filter(User.id == project_data.owner_id).first()
        if not owner or owner.role != UserRole.OWNER or owner.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Assigned owner must be an active Owner")
        project.owner_id = project_data.owner_id
        add_user_to_project(
            db,
            project_id=project.id,
            user_id=project_data.owner_id,
            role_on_project=UserRole.OWNER,
        )

    if project_data.project_manager_id is not None:
        if project_data.project_manager_id != project.project_manager_id:
            pm = db.query(User).filter(User.id == project_data.project_manager_id).first()
            if not pm or pm.role != UserRole.PROJECT_MANAGER or pm.status != UserStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="Assigned project manager must be an active Project Manager")
            project.project_manager_id = project_data.project_manager_id
            if project_data.project_manager_id:
                add_user_to_project(
                    db,
                    project_id=project.id,
                    user_id=project_data.project_manager_id,
                    role_on_project=UserRole.PROJECT_MANAGER,
                )
                db.add(Notification(user_id=project_data.project_manager_id, title="Project Assignment",
                    message=f"You have been assigned to {project.name}.", type=NotificationType.SYSTEM,
                    project_id=project.id, related_entity_type="PROJECT", related_entity_id=project.id))

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not is_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Not authorized to delete this project")

    db.delete(project)
    db.commit()
    return {"message": "Project deleted successfully"}


@router.get("/{project_id}/approval-workflow", response_model=ProjectApprovalConfigOut)
def get_project_approval_workflow(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.WORKER:
        raise HTTPException(status_code=403, detail="Workers cannot access Consultant approval configuration")
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _approval_config_response(project)


@router.put("/{project_id}/approval-workflow", response_model=ProjectApprovalConfigOut)
def update_project_approval_workflow(
    project_id: uuid.UUID,
    data: ProjectApprovalConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only Administrators can configure Consultant approval")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    desired: set[tuple[uuid.UUID, str | None]] = set()
    if data.centralized_reviewer_id:
        desired.add((data.centralized_reviewer_id, None))
    for raw_discipline, reviewer_ids in data.discipline_reviewers.items():
        discipline = normalize_discipline(raw_discipline)
        if not discipline:
            raise HTTPException(status_code=422, detail="Reviewer discipline cannot be blank")
        desired.update((reviewer_id, discipline) for reviewer_id in reviewer_ids)

    reviewer_ids = {user_id for user_id, _ in desired}
    eligible_ids = {
        row[0] for row in db.query(ProjectMember.user_id).join(
            User, User.id == ProjectMember.user_id
        ).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id.in_(reviewer_ids),
            ProjectMember.role_on_project == UserRole.CONSULTANT,
            ProjectMember.is_active == True,
            User.role == UserRole.ENGINEER,
            User.engineer_affiliation == "external_consultant",
            User.status == UserStatus.ACTIVE,
        ).all()
    } if reviewer_ids else set()
    if eligible_ids != reviewer_ids:
        raise HTTPException(
            status_code=422,
            detail="Every reviewer must be an active Consultant Engineer member of this project",
        )

    existing_rows = list(project.consultant_reviewer_assignments)
    existing = {(item.user_id, item.discipline) for item in existing_rows}
    previous_mode = project.consultant_approval_mode
    project.consultant_approval_mode = data.mode

    if previous_mode != data.mode:
        record_audit(
            db, actor_id=current_user.id, action="consultant_approval_mode_changed",
            entity_type="project", entity_id=project.id, project_id=project.id,
            details={"from": previous_mode.value, "to": data.mode.value},
        )

    old_central = next((user_id for user_id, discipline in existing if discipline is None), None)
    new_central = next((user_id for user_id, discipline in desired if discipline is None), None)
    if old_central != new_central and (old_central or new_central):
        action = "centralized_reviewer_replaced" if old_central and new_central else (
            "centralized_reviewer_assigned" if new_central else "centralized_reviewer_removed"
        )
        record_audit(
            db, actor_id=current_user.id, action=action, entity_type="project",
            entity_id=project.id, project_id=project.id,
            details={"previous_reviewer_id": old_central, "reviewer_id": new_central},
        )

    for user_id, discipline in sorted(existing - desired, key=lambda item: (item[1] or "", str(item[0]))):
        if discipline is not None:
            record_audit(
                db, actor_id=current_user.id, action="discipline_reviewer_removed",
                entity_type="project", entity_id=project.id, project_id=project.id,
                details={"reviewer_id": user_id, "discipline": discipline},
            )
    for user_id, discipline in sorted(desired - existing, key=lambda item: (item[1] or "", str(item[0]))):
        if discipline is not None:
            record_audit(
                db, actor_id=current_user.id, action="discipline_reviewer_assigned",
                entity_type="project", entity_id=project.id, project_id=project.id,
                details={"reviewer_id": user_id, "discipline": discipline},
            )

    for assignment in existing_rows:
        db.delete(assignment)
    db.flush()
    for user_id, discipline in desired:
        db.add(ProjectConsultantReviewer(
            project_id=project.id,
            user_id=user_id,
            discipline=discipline,
            assigned_by_id=current_user.id,
        ))
    db.commit()
    db.refresh(project)
    return _approval_config_response(project)


@router.get("/{project_id}/members", response_model=List[ProjectMemberOut])
def get_project_members(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    if current_user.role in {UserRole.ENGINEER, UserRole.WORKER}:
        raise HTTPException(status_code=403, detail="Field users cannot access the complete project team")

    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return members

@router.get("/{project_id}/available-engineers", response_model=List[UserOut])
def get_available_engineers(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_manageable_project_or_403(project_id, db, current_user)
    assigned_ids = db.query(ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id, ProjectMember.is_active == True
    )
    return db.query(User).filter(
        User.role == UserRole.ENGINEER,
        User.engineer_affiliation.in_(["internal_engineer", "main_contractor"]),
        User.status == UserStatus.ACTIVE,
        ~User.id.in_(assigned_ids),
    ).order_by(User.full_name).all()


@router.get("/{project_id}/available-team-members", response_model=List[UserOut])
def get_available_team_members(
    project_id: uuid.UUID,
    search: Optional[str] = None,
    role: Optional[UserRole] = None,
    discipline: Optional[EngineerDiscipline] = None,
    affiliation: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backend-filtered active Engineers and Consultants eligible for a project."""
    get_manageable_project_or_403(project_id, db, current_user)
    if role is not None and role not in {UserRole.ENGINEER, UserRole.CONSULTANT, UserRole.WORKER}:
        raise HTTPException(status_code=400, detail="Eligible team roles are Engineer, Consultant, and Worker")
    assigned_ids = db.query(ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id, ProjectMember.is_active == True
    )
    query = db.query(User).outerjoin(EngineerProfile).filter(
        User.role.in_([UserRole.ENGINEER, UserRole.WORKER]),
        User.status == UserStatus.ACTIVE,
        ~User.id.in_(assigned_ids),
    )
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            User.full_name.ilike(term),
            User.email.ilike(term),
            User.organization.ilike(term),
            User.engineer_affiliation.ilike(term),
            cast(User.role, String).ilike(term),
            cast(EngineerProfile.discipline, String).ilike(term),
        ))
    if role == UserRole.CONSULTANT:
        query = query.filter(User.engineer_affiliation == "external_consultant")
    elif role == UserRole.ENGINEER:
        query = query.filter(User.role == UserRole.ENGINEER, User.engineer_affiliation != "external_consultant")
    elif role == UserRole.WORKER:
        query = query.filter(User.role == UserRole.WORKER)
    if discipline:
        query = query.filter(EngineerProfile.discipline == discipline)
    if affiliation:
        query = query.filter(User.engineer_affiliation == affiliation)
    return query.order_by(User.full_name).limit(100).all()


@router.post("/{project_id}/members", response_model=ProjectMemberOut)
def add_project_member(
    project_id: uuid.UUID,
    data: ProjectMemberAssignExisting,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_manageable_project_or_403(project_id, db, current_user)

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Only active users can be assigned to projects")
    is_external_consultant = (
        user.role == UserRole.ENGINEER and user.engineer_affiliation == "external_consultant"
    )
    expected_project_role = UserRole.CONSULTANT if is_external_consultant else user.role
    if current_user.role == UserRole.PROJECT_MANAGER:
        if project.project_manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only manage your assigned project team")
        if user.role not in {UserRole.ENGINEER, UserRole.CONSULTANT, UserRole.WORKER}:
            raise HTTPException(status_code=403, detail="Project Managers can assign only Engineers, Consultants, and Workers")
        if data.role_on_project != expected_project_role:
            raise HTTPException(status_code=400, detail="Project member role must match the user's global role")
    elif current_user.role == UserRole.ADMIN:
        if data.role_on_project not in {
            UserRole.OWNER,
            UserRole.PROJECT_MANAGER,
            UserRole.ENGINEER,
            UserRole.CONSULTANT,
            UserRole.WORKER,
        }:
            raise HTTPException(status_code=400, detail="Unsupported project member role")
        if expected_project_role != data.role_on_project:
            raise HTTPException(status_code=400, detail="Project member role must match the user's system role")

    active_member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id, ProjectMember.is_active == True).first()
    if active_member:
        raise HTTPException(status_code=409, detail="User is already an active member of this project")
    if data.is_site_engineer and (user.role != UserRole.ENGINEER or is_external_consultant):
        raise HTTPException(status_code=400, detail="Only contractor-side Engineers can be assigned as Site Engineers")

    member = add_user_to_project(
        db,
        project_id=project_id,
        user_id=data.user_id,
        role_on_project=data.role_on_project,
    )
    member.assignment_title = data.assignment_title
    member.project_discipline = data.project_discipline.value if data.project_discipline else (
        user.engineer_profile.discipline.value if user.engineer_profile else None)
    member.project_notes = data.project_notes
    member.is_site_engineer = bool(data.is_site_engineer and user.role == UserRole.ENGINEER and not is_external_consultant)
    member.assigned_by_id = current_user.id
    record_audit(db, actor_id=current_user.id, action="project_member_assigned", entity_type="project_member",
                 entity_id=member.id, project_id=project_id, details={"user_id": user.id, "site_engineer": member.is_site_engineer})
    db.add(Notification(user_id=user.id, title="Project Assignment", message=f"You have been assigned to {project.name}.",
                        type=NotificationType.SYSTEM, project_id=project_id, related_entity_type="PROJECT", related_entity_id=project_id))
    db.commit()
    db.refresh(member)
    return member


@router.patch("/{project_id}/members/{user_id}/assignment", response_model=ProjectMemberOut)
def update_member_assignment(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ProjectMemberAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_manageable_project_or_403(project_id, db, current_user)
    member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id, ProjectMember.is_active == True).first()
    if not member:
        raise HTTPException(status_code=404, detail="Active project member not found")
    previous = member.is_site_engineer
    if data.assignment_title is not None:
        member.assignment_title = data.assignment_title.strip() or None
    if data.is_site_engineer is not None:
        if data.is_site_engineer and member.role_on_project != UserRole.ENGINEER:
            raise HTTPException(status_code=400, detail="Only Engineers can be assigned as Site Engineers")
        member.is_site_engineer = data.is_site_engineer
    if data.project_discipline is not None:
        member.project_discipline = data.project_discipline.value
    if data.project_notes is not None:
        member.project_notes = data.project_notes.strip() or None
    member.assigned_by_id = current_user.id
    action = "site_engineer_assigned" if member.is_site_engineer and not previous else (
        "site_engineer_removed" if previous and not member.is_site_engineer else "project_assignment_updated")
    record_audit(db, actor_id=current_user.id, action=action, entity_type="project_member", entity_id=member.id,
                 project_id=project_id, details={"user_id": user_id, "assignment_title": member.assignment_title,
                    "project_discipline": member.project_discipline, "site_engineer": member.is_site_engineer})
    notification_title = "Site Engineer Assignment" if action == "site_engineer_assigned" else (
        "Site Engineer Assignment Removed" if action == "site_engineer_removed" else "Project Responsibility Updated")
    notification_message = (f"You have been assigned as a Site Engineer for {project.name}." if action == "site_engineer_assigned"
        else f"Your Site Engineer responsibility for {project.name} was removed." if action == "site_engineer_removed"
        else f"Your responsibility in {project.name} was updated.")
    db.add(Notification(user_id=user_id, title=notification_title,
                        message=notification_message, type=NotificationType.SYSTEM,
                        project_id=project_id, related_entity_type="PROJECT", related_entity_id=project_id))
    db.commit()
    db.refresh(member)
    return member


@router.post("/{project_id}/members/engineer", response_model=UserCreateResponse)
def create_and_add_engineer(
    project_id: uuid.UUID,
    data: ProjectMemberCreateEngineer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=403,
        detail="Project members must be assigned from existing administrator-created users",
    )


@router.post("/{project_id}/members/owner", response_model=UserCreateResponse)
def create_and_add_owner(
    project_id: uuid.UUID,
    data: ProjectMemberCreateOwner,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raise HTTPException(
        status_code=403,
        detail="Project owners must be assigned from existing administrator-created users",
    )


@router.delete("/{project_id}/members/{user_id}")
def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_manageable_project_or_403(project_id, db, current_user)

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if current_user.role == UserRole.PROJECT_MANAGER and member.role_on_project not in {
        UserRole.ENGINEER, UserRole.CONSULTANT, UserRole.WORKER
    }:
        raise HTTPException(status_code=403, detail="Project Managers can remove only Engineers, Consultants, and Workers")
    if member.role_on_project in {UserRole.OWNER, UserRole.PROJECT_MANAGER}:
        raise HTTPException(status_code=400, detail="Reassign the project owner or manager before removing this membership")

    assigned_tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignees.any(User.id == user_id),
    ).all()
    active_tasks = [task for task in assigned_tasks if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}]
    if active_tasks and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=409,
            detail=f"Reassign or complete {len(active_tasks)} active task(s) before removing this member")
    for task in assigned_tasks:
        task.assignees = [assignee for assignee in task.assignees if assignee.id != user_id]
    unassigned_active_tasks = sum(1 for task in active_tasks if not task.assignees)

    member.is_active = False
    member.is_site_engineer = False
    _remove_reviewer_assignments(db, project_id, user_id, current_user.id)
    record_audit(db, actor_id=current_user.id, action="project_member_removed", entity_type="project_member",
                 entity_id=member.id, project_id=project_id,
                 details={"user_id": user_id, "removed_task_assignments": len(assigned_tasks),
                          "unassigned_active_tasks": unassigned_active_tasks,
                          "global_account_preserved": True})
    project = db.get(Project, project_id)
    db.add(Notification(user_id=user_id, title="Project Assignment Removed",
        message=f"Your assignment to {project.name if project else 'the project'} was removed."
                + (f" {unassigned_active_tasks} active task(s) are now unassigned." if unassigned_active_tasks else ""),
        type=NotificationType.SYSTEM, project_id=project_id,
        related_entity_type="PROJECT", related_entity_id=project_id))
    db.commit()
    return {"message": "Member removed from project"}


@router.post("/{project_id}/members/{user_id}/transfer", response_model=ProjectMemberOut)
def transfer_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    data: ProjectMemberTransfer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only Administrators can transfer project members")
    if data.target_project_id == project_id:
        raise HTTPException(status_code=400, detail="Source and target projects must be different")

    source_project = get_manageable_project_or_403(project_id, db, current_user)
    target_project = get_manageable_project_or_403(data.target_project_id, db, current_user)
    source_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.is_active == True,
    ).first()
    if not source_member:
        raise HTTPException(status_code=404, detail="Active source project membership not found")
    if source_member.role_on_project not in {UserRole.ENGINEER, UserRole.CONSULTANT, UserRole.WORKER}:
        raise HTTPException(status_code=400, detail="Only Engineers, Consultants, and Workers can be transferred")

    assigned_tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignees.any(User.id == user_id),
    ).all()
    active_tasks = [task for task in assigned_tasks if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}]
    for task in assigned_tasks:
        task.assignees = [assignee for assignee in task.assignees if assignee.id != user_id]
    unassigned_active_tasks = sum(1 for task in active_tasks if not task.assignees)

    target_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == data.target_project_id,
        ProjectMember.user_id == user_id,
    ).first()
    if target_member and target_member.is_active:
        raise HTTPException(status_code=409, detail="User is already an active member of the target project")
    if target_member is None:
        target_member = ProjectMember(
            project_id=data.target_project_id,
            user_id=user_id,
            role_on_project=source_member.role_on_project,
        )
        db.add(target_member)

    target_member.is_active = True
    target_member.role_on_project = source_member.role_on_project
    target_member.assignment_title = source_member.assignment_title
    target_member.project_discipline = source_member.project_discipline
    target_member.project_notes = source_member.project_notes
    target_member.is_site_engineer = bool(
        data.is_site_engineer and source_member.role_on_project == UserRole.ENGINEER
    )
    target_member.assigned_by_id = current_user.id
    source_member.is_active = False
    source_member.is_site_engineer = False
    source_member.assigned_by_id = current_user.id
    _remove_reviewer_assignments(db, project_id, user_id, current_user.id)
    db.flush()

    details = {
        "user_id": user_id,
        "source_project_id": project_id,
        "target_project_id": data.target_project_id,
        "global_account_preserved": True,
        "removed_source_task_assignments": len(assigned_tasks),
        "unassigned_active_source_tasks": unassigned_active_tasks,
    }
    record_audit(db, actor_id=current_user.id, action="project_member_transferred_out",
                 entity_type="project_member", entity_id=source_member.id,
                 project_id=project_id, details=details)
    record_audit(db, actor_id=current_user.id, action="project_member_transferred_in",
                 entity_type="project_member", entity_id=target_member.id,
                 project_id=data.target_project_id, details=details)
    db.add(Notification(
        user_id=user_id,
        title="Project Assignment Transferred",
        message=f"Your assignment was transferred from {source_project.name} to {target_project.name}.",
        type=NotificationType.SYSTEM,
        project_id=data.target_project_id,
        related_entity_type="PROJECT",
        related_entity_id=data.target_project_id,
    ))
    db.commit()
    db.refresh(target_member)
    return target_member


@router.get("/{project_id}/owner-dashboard", response_model=OwnerDashboardOut)
def get_owner_dashboard(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {UserRole.OWNER, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Owner executive dashboard access required")
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    days_remaining = 0
    if project.planned_end_date:
        delta = project.planned_end_date - date.today()
        days_remaining = delta.days

    active_task_statuses = [
        TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.IN_PROGRESS,
        TaskStatus.UNDER_REVIEW, TaskStatus.REWORK_REQUIRED, TaskStatus.BLOCKED,
    ]
    project_tasks = db.query(Task).filter(Task.project_id == project_id).all()
    overdue_tasks = [
        task for task in project_tasks
        if task.planned_end_date and task.planned_end_date < date.today()
        and task.status in active_task_statuses
    ]
    critical_delayed_tasks = [
        task for task in overdue_tasks
        if task.is_critical_path or task.priority == TaskPriority.CRITICAL
    ]
    has_overdue_tasks = bool(overdue_tasks)
    is_delayed = project.status.value == "delayed" or has_overdue_tasks or (days_remaining < 0 and project.status.value != "completed")
    current_task = next((
        task for task in sorted(
            project_tasks,
            key=lambda item: (item.planned_start_date or date.max, item.sort_order),
        )
        if task.status in active_task_statuses
    ), None)
    current_phase = (
        (current_task.discipline or current_task.milestone.name)
        if current_task and (current_task.discipline or current_task.milestone)
        else ("Completed" if project.status == ProjectStatus.COMPLETED else "Planning")
    )

    project_summary = {
        "name": project.name,
        "status": project.status.value,
        "completionPercentage": float(project.completion_percentage),
        "currentPhase": current_phase.replace("_", " ").title(),
        "startDate": project.start_date.isoformat() if project.start_date else None,
        "plannedEndDate": project.planned_end_date.isoformat() if project.planned_end_date else None,
        "daysRemaining": days_remaining,
        "isDelayed": is_delayed,
    }

    budget_tot = float(project.budget_total or 0.0)
    budget_spt = float(project.budget_spent or 0.0)

    committed_cost = db.query(func.sum(CostValidation.certified_amount)).filter(
        CostValidation.project_id == project_id,
        CostValidation.status == CostValidationStatus.APPROVED,
    ).scalar() or 0.0

    pending_cost = db.query(func.sum(CostValidation.requested_cost)).filter(
        CostValidation.project_id == project_id,
        CostValidation.status == CostValidationStatus.PENDING,
    ).scalar() or 0.0

    variance = budget_tot - budget_spt
    var_percent = (variance / budget_tot * 100.0) if budget_tot > 0 else 0.0

    cost_summary = CostSummaryOut(
        project_id=project_id,
        budget_total=budget_tot,
        budget_spent=budget_spt,
        committed_cost=float(committed_cost),
        pending_cost=float(pending_cost),
        variance=variance,
        variance_percentage=var_percent,
        updated_at=project.updated_at,
    )

    milestones_db = db.query(MilestoneModel).filter(
        MilestoneModel.project_id == project_id,
    ).order_by(MilestoneModel.planned_date.asc()).limit(10).all()

    milestones = []
    for milestone in milestones_db:
        status_label = "pending"
        if milestone.actual_date or (milestone.tasks and all(task.status == TaskStatus.DONE for task in milestone.tasks)):
            status_label = "completed"
        elif milestone.planned_date < date.today():
            status_label = "delayed"

        milestones.append(MilestoneOut(
            id=milestone.id,
            name=milestone.name,
            planned_date=milestone.planned_date,
            actual_date=milestone.actual_date,
            status=status_label,
        ))

    active_issues = db.query(Issue).filter(
        Issue.project_id == project_id,
        Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
    ).order_by(Issue.severity.desc(), Issue.created_at.desc()).all()
    important_changes = db.query(DesignChange).filter(
        DesignChange.project_id == project_id,
    ).order_by(DesignChange.created_at.desc()).limit(8).all()
    rejected_reviews = db.query(TaskReview).join(Task, Task.id == TaskReview.task_id).filter(
        Task.project_id == project_id,
        TaskReview.status == "rejected",
    ).order_by(TaskReview.updated_at.desc()).limit(5).all()

    attention_required = []
    for task in critical_delayed_tasks[:5]:
        attention_required.append({
            "id": str(task.id), "type": "major_delay", "severity": "critical",
            "title": f"Critical delay: {task.name}",
            "summary": f"{(date.today() - task.planned_end_date).days} day(s) behind schedule.",
            "entityType": "TASK", "entityId": str(task.id),
        })
    for issue in active_issues:
        if issue.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL}:
            attention_required.append({
                "id": str(issue.id), "type": "critical_issue", "severity": issue.severity.value,
                "title": issue.title, "summary": issue.description or "An important project issue is unresolved.",
                "entityType": "ISSUE", "entityId": str(issue.id),
            })
    for review in rejected_reviews:
        attention_required.append({
            "id": str(review.id), "type": "rejected_review", "severity": "high",
            "title": f"Consultant review rejected: {review.task.name}",
            "summary": review.rejection_reason or review.comments or "Corrections are required.",
            "entityType": "TASK", "entityId": str(review.task_id),
        })
    for milestone in milestones_db:
        completed = milestone.actual_date or (
            milestone.tasks and all(task.status == TaskStatus.DONE for task in milestone.tasks)
        )
        if not completed and milestone.planned_date < date.today():
            attention_required.append({
                "id": str(milestone.id), "type": "milestone_missed", "severity": "high",
                "title": f"Milestone missed: {milestone.name}",
                "summary": f"Planned for {milestone.planned_date.isoformat()}.",
                "entityType": "MILESTONE", "entityId": str(milestone.id),
            })
    for change in important_changes:
        if (
            change.status in {DesignChangeStatus.PROPOSED, DesignChangeStatus.UNDER_REVIEW}
            and ((change.expected_schedule_impact_days or 0) > 0 or float(change.expected_cost_impact or 0) > 0)
        ):
            attention_required.append({
                "id": str(change.id), "type": "design_change", "severity": "high",
                "title": change.title,
                "summary": change.reason or change.description or "An important design change requires attention.",
                "entityType": "DESIGN_CHANGE", "entityId": str(change.id),
            })

    discipline_groups = {}
    for task in project_tasks:
        phase = (task.discipline or "General").replace("_", " ").title()
        group = discipline_groups.setdefault(phase, {"name": phase, "total": 0, "progress": 0.0})
        group["total"] += 1
        group["progress"] += float(task.progress_percentage or 0)
    project_breakdown = [{
        "name": group["name"],
        "taskCount": group["total"],
        "completionPercentage": round(group["progress"] / group["total"], 1),
    } for group in discipline_groups.values()]

    project_health = "delayed" if is_delayed else (
        "at_risk" if any(issue.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL} for issue in active_issues)
        or any(change.status in {DesignChangeStatus.PROPOSED, DesignChangeStatus.UNDER_REVIEW} for change in important_changes)
        else "on_track"
    )
    approved_reviews = db.query(TaskReview).join(Task, Task.id == TaskReview.task_id).filter(
        Task.project_id == project_id, TaskReview.status == "approved",
    ).count()
    pending_reviews = db.query(Task).filter(
        Task.project_id == project_id, Task.status == TaskStatus.UNDER_REVIEW,
    ).count()

    recent_activities = []
    recent_tasks = db.query(Task).filter(Task.project_id == project_id).order_by(Task.updated_at.desc()).limit(5).all()
    for t in recent_tasks:
        recent_activities.append(RecentActivityOut(
            id=t.id,
            type="task",
            description=f"Task '{t.name}' status updated to {t.status.value}",
            timestamp=t.updated_at,
            user=", ".join(assignee.full_name for assignee in t.assignees) or "Unassigned",
        ))

    recent_photos_db = db.query(MediaAsset).filter(
        MediaAsset.project_id == project_id,
        MediaAsset.media_type == MediaType.IMAGE,
    ).order_by(MediaAsset.created_at.desc()).limit(6).all()

    recent_photos = []
    for asset in recent_photos_db:
        recent_photos.append(RecentPhotoOut(
            id=asset.id,
            url=asset.file_url,
            caption=asset.caption,
            task_name=asset.task.name if asset.task else None,
            uploaded_at=asset.created_at,
        ))

    pending_owner_requests = db.query(OwnerRequest).filter(
        OwnerRequest.project_id == project_id,
        OwnerRequest.status.in_(["SUBMITTED", "ASSIGNED", "UNDER_REVIEW", "NEEDS_CLARIFICATION", "ACCEPTED", "CONVERTED_TO_DESIGN_CHANGE"]),
    ).order_by(OwnerRequest.created_at.desc()).limit(10).all()
    upcoming_site_visits = db.query(SiteVisit).filter(
        SiteVisit.project_id == project_id, SiteVisit.scheduled_start >= datetime.now(timezone.utc),
        SiteVisit.status.notin_(["CANCELLED", "COMPLETED"]),
    ).order_by(SiteVisit.scheduled_start).limit(8).all()
    verified_reports = db.query(SiteReport).filter(
        SiteReport.project_id == project_id, SiteReport.review_status == "approved",
    ).order_by(SiteReport.report_date.desc()).limit(8).all()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    verified_tasks_since = db.query(Task).filter(
        Task.project_id == project_id, Task.status == TaskStatus.DONE,
        Task.review_status == "approved", Task.updated_at >= since,
    ).count()
    approved_changes_since = db.query(DesignChange).filter(
        DesignChange.project_id == project_id, DesignChange.status == DesignChangeStatus.APPROVED,
        DesignChange.updated_at >= since,
    ).count()
    return OwnerDashboardOut(
        project_summary=project_summary,
        cost_summary=cost_summary,
        milestones=milestones,
        recent_activities=recent_activities,
        recent_photos=recent_photos,
        project_health=project_health,
        delayed_tasks=[{
            "id": str(task.id), "name": task.name, "taskCode": task.task_code,
            "daysDelayed": (date.today() - task.planned_end_date).days,
            "isCriticalPath": task.is_critical_path,
        } for task in critical_delayed_tasks],
        open_issues=[{
            "id": str(issue.id), "title": issue.title, "severity": issue.severity.value,
            "status": issue.status.value, "summary": issue.description,
        } for issue in active_issues],
        attention_required=attention_required[:12],
        project_breakdown=project_breakdown,
        design_changes=[{
            "id": str(change.id), "title": change.title, "summary": change.description,
            "reason": change.reason, "status": change.status.value,
            "costImpact": float(change.expected_cost_impact or 0),
            "scheduleImpactDays": change.expected_schedule_impact_days or 0,
        } for change in important_changes],
        consultant_approvals={
            "approved": approved_reviews,
            "pending": pending_reviews,
            "rejected": len(rejected_reviews),
        },
        latest_executive_updates=[{
            "id": str(log.id), "action": log.action, "entityType": log.entity_type,
            "timestamp": log.created_at,
        } for log in db.query(AuditLog).filter(
            AuditLog.project_id == project_id,
            AuditLog.entity_type.in_(["project", "milestone", "design_change", "site_report", "issue", "task"]),
        ).order_by(AuditLog.created_at.desc()).limit(8).all()],
        pending_owner_requests=[{"id": str(item.id), "title": item.title, "status": item.status,
                                 "priority": item.priority, "discipline": item.discipline,
                                 "needsOwnerInput": item.status == "NEEDS_CLARIFICATION"} for item in pending_owner_requests],
        upcoming_site_visits=[{"id": str(item.id), "title": item.title, "scheduledStart": item.scheduled_start,
                               "visitType": item.visit_type, "status": item.status, "location": item.location} for item in upcoming_site_visits],
        recent_verified_site_reports=[{"id": str(item.id), "reportDate": item.report_date,
                                       "summary": item.summary_text, "reviewStatus": item.review_status} for item in verified_reports],
        since_last_visit={"periodDays": 7, "verifiedTasks": verified_tasks_since,
                          "approvedDesignChanges": approved_changes_since,
                          "verifiedSiteReports": sum(item.created_at >= since for item in verified_reports),
                          "requestsAwaitingClarification": sum(item.status == "NEEDS_CLARIFICATION" for item in pending_owner_requests),
                          "nextEngineerVisit": upcoming_site_visits[0].scheduled_start if upcoming_site_visits else None,
                          "officialInformationOnly": True},
    )
