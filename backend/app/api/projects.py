from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import String, and_, cast, func, or_
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
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember, ProjectViewState
from app.models.rbac import Discipline, ProjectMemberDiscipline, ProjectParty, Role
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
    CONSULTANT_AFFILIATION,
    get_current_user,
    get_project_or_403,
    user_has_project_access,
)
from app.services import rbac
from app.services.user_service import create_provisioned_user, add_user_to_project
from app.services.audit_service import record_audit
from app.services.authorization import (
    can_view_all_projects_effective, has_permission, manageable_project, require,
    require_permission,
)
from app.models.notification import Notification
from app.models.enums import NotificationType
from app.services.consultant_approval_service import normalize_discipline
from app.services.project_view_service import record_visit, visit_boundary

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


def _validated_project_role(db: Session, role_id, party_id, project_id):
    """A role this person may actually be given on this project.

    Two rules, both structural rather than configurable:

      * the role must exist and be assignable on a project (`scope` is not
        ORG-only), otherwise the assignment says something the platform cannot
        honour;
      * a role marked `is_internal_only` cannot be given to somebody taking
        part for an outside party. `app.services.rbac` strips office authority
        from external participants at resolution time regardless, so this is
        the honest refusal rather than the security boundary — but an
        administrator should be told, not silently ignored.
    """
    if role_id is None:
        return None
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Project role not found")
    if role.scope == "ORG":
        raise HTTPException(
            status_code=422,
            detail=f"{role.name_en} is an office role and cannot be given on a project",
        )
    if party_id is not None and role.is_internal_only:
        raise HTTPException(
            status_code=422,
            detail=f"{role.name_en} is for office staff and cannot be given to an external participant",
        )
    return role


def _set_member_disciplines(db: Session, member: ProjectMember, discipline_ids) -> None:
    """Replace the disciplines this person covers on this project."""
    wanted = set(discipline_ids or [])
    if wanted:
        known = {
            row.id for row in db.query(Discipline).filter(Discipline.id.in_(wanted)).all()
        }
        if known != wanted:
            raise HTTPException(status_code=400, detail="Unknown discipline")
    existing = db.query(ProjectMemberDiscipline).filter(
        ProjectMemberDiscipline.project_member_id == member.id
    ).all()
    for row in existing:
        if row.discipline_id not in wanted:
            db.delete(row)
        else:
            wanted.discard(row.discipline_id)
    for discipline_id in wanted:
        db.add(ProjectMemberDiscipline(
            project_member_id=member.id, discipline_id=discipline_id,
        ))


def _scoped_projects_query(db: Session, current_user: User):
    query = db.query(Project)
    # The "view all" gate is checked before the Project Manager branch (not
    # the other way around, as this used to read) so that granting
    # `platform.view_all_projects` to a specific PM actually does something:
    # previously a PM's "only my assigned project" filter applied
    # unconditionally, so the permission could never have any effect for that
    # role. The static default is unchanged (only ADMIN holds this by
    # default, via the catalogue, not a hardcoded role check — see
    # `can_view_all_projects_effective`), so nobody's visibility shifts unless
    # an administrator configures it. This mirrors `accessible_project_ids`
    # (app.core.deps), which already had this ordering.
    if not can_view_all_projects_effective(db, current_user):
        # One union for everybody — membership, ownership or management. The
        # branch this replaces gave a PROJECT_MANAGER only what they managed
        # and ignored their memberships entirely.
        member_project_ids = db.query(ProjectMember.project_id).filter(
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_active == True,
        ).subquery()
        query = query.filter(
            (Project.owner_id == current_user.id)
            | (Project.project_manager_id == current_user.id)
            | Project.id.in_(member_project_ids)
        )
    # No `company_id` filter here, deliberately: cross-company collaboration
    # is how this app is actually modelled, not an edge case. The seeded demo
    # project (app.db.seed_demo) is owned by one company while its Main
    # Contractor engineers and reviewing consultants belong to two different
    # companies entirely, joined only through `ProjectMember`; company_id is
    # how `Project`/`User` record which company someone belongs to (used for
    # e.g. scoping the user directory in app.api.users and `/company/settings`),
    # not a project-visibility boundary. An unconditional `Project.company_id
    # == current_user.company_id` AND-filter here used to hide a project from
    # every contractor/consultant member whose own company differs from the
    # project's owning company — which is every non-owner-side member in the
    # seeded project — even though `accessible_project_ids` /
    # `user_has_project_access` (app.core.deps) and `get_dashboard_stats`
    # (app.api.dashboard) never applied any such filter and already granted
    # them access. This just brings the project list in line with the access
    # every other endpoint already gives the same person.
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
    # `_scoped_projects_query` already narrows to the projects this person is
    # on. The retired refusal additionally required an Engineer to be
    # contractor- or consultant-side, which excluded the office's own staff
    # from listing the projects they had been assigned to.
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
    # Commercial figures follow the cost permission rather than a role list.
    if not has_permission(db, current_user, "cost_validation.review"):
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
    # A portfolio summary is commercial. It follows the cost permission rather
    # than a list of roles that are not allowed to see money.
    if not has_permission(db, current_user, "cost_validation.review"):
        raise HTTPException(status_code=403, detail="You are not authorized to see portfolio financials")
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Commercial figures are for whoever the office lets see them. `get_project_or_403`
    # has already established membership; this only hides money from people
    # whose role does not carry the cost permission.
    if not has_permission(db, current_user, "cost_validation.review", project.id):
        project.budget_total = None
        project.budget_spent = None
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("platform.create_project")),
):
    # Whoever the office nominates to run the project, provided they can
    # actually run one. `project.manage_members` is that capability; the role
    # comparison this replaces meant an office could not nominate somebody in a
    # role it had created, however it had permissioned them.
    pm_id = project_data.project_manager_id or current_user.id
    if pm_id != current_user.id:
        pm = db.query(User).filter(User.id == pm_id).first()
        if not pm or not rbac.is_staffable(db, pm) or not has_permission(
            db, pm, "project.manage_members"
        ):
            raise HTTPException(
                status_code=400,
                detail="The nominated project manager must be an active member who can manage a project team",
            )

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
    project = manageable_project(db, current_user, project_id, "project.edit")

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
    # Was `is_admin(current_user.role)`. `project.delete` is a new code rather
    # than a reuse of an existing one: this cascades across 39 tables, and no
    # permission already in the catalogue says so. It defaults to the
    # administrator alone, which is the same set `is_admin` admitted.
    project = manageable_project(db, current_user, project_id, "project.delete")

    db.delete(project)
    db.commit()
    return {"message": "Project deleted successfully"}


@router.get("/{project_id}/approval-workflow", response_model=ProjectApprovalConfigOut)
def get_project_approval_workflow(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    # Choosing who reviews on a project is project setup, so it is gated on the
    # permission that already means "edit this project's settings".
    # `project.edit` defaults to the administrator alone — the same answer the
    # hardcoded role check gave — and is `office_only`, so no configuration can
    # hand it to a contractor. `manageable_project` additionally re-checks
    # project access, which a bare role comparison never did.
    project = manageable_project(db, current_user, project_id, "project.edit")

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
            ProjectMember.is_active == True,
            User.status == UserStatus.ACTIVE,
            # Office staff, and nobody else: naming a reviewer is naming who
            # carries the office's review authority on this project. Was
            # "role is ENGINEER and affiliation is external_consultant", which
            # is the retired Consultant Engineer identity — under the confirmed
            # direction the office *is* the consultant, so its own people are
            # the candidates and `task.review` (never_external) is what they
            # must hold.
            User.is_internal.is_(True),
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
    # The full team list belongs to whoever staffs the project. Everybody else
    # reaches the people they work with through the project's own screens.
    if not has_permission(db, current_user, "project.manage_members", project_id):
        raise HTTPException(status_code=403, detail="You are not authorized to see the complete project team")

    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    return members

@router.get("/{project_id}/available-engineers", response_model=List[UserOut])
def get_available_engineers(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # This list exists only to feed member assignment, so it is gated by the
    # capability that assignment itself requires. Was "administrator, or the
    # manager this project is assigned to" — a rule read off the retired enum,
    # which resolves identically for every account here but could not express an
    # office role the administrator had granted the same authority.
    manageable_project(db, current_user, project_id, "project.manage_members")
    assigned_ids = db.query(ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id, ProjectMember.is_active == True
    )
    # The same "may be staffed onto a project" predicate the assignment
    # endpoint uses. Was two retired enum values plus two affiliation strings.
    return db.query(User).filter(
        rbac.staffable_filter(db),
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
    # Same staffing picker, same gate as `available-engineers` above.
    manageable_project(db, current_user, project_id, "project.manage_members")
    if role is not None and role not in {UserRole.ENGINEER, UserRole.CONSULTANT}:
        raise HTTPException(status_code=400, detail="Eligible team roles are Engineer and Consultant")
    assigned_ids = db.query(ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id, ProjectMember.is_active == True
    )
    # A consultant is either an account whose global role is Consultant, or an
    # Engineer account marked as an external consultant. Only the second form was
    # listed here, so a Consultant account an administrator had created could
    # never be picked for a project even though the assignment endpoint accepts it.
    consultant_user = or_(
        User.role == UserRole.CONSULTANT,
        and_(User.role == UserRole.ENGINEER, User.engineer_affiliation == CONSULTANT_AFFILIATION),
    )
    # Who may be staffed onto a project, asked once and in the new model:
    # active, and not parked on a role that exists only to hold history. This
    # used to read `User.role.in_([ENGINEER, CONSULTANT])`, which meant an
    # office could not put its own General Manager or Document Controller on a
    # project — the candidate list only knew two of six retired enum values.
    query = db.query(User).outerjoin(EngineerProfile).filter(
        rbac.staffable_filter(db),
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
        # Selecting on affiliation alone also matched Workers who carry the
        # external-consultant affiliation. Assigning one of those as a Consultant
        # was then rejected as a role mismatch by POST /members.
        query = query.filter(consultant_user)
    elif role == UserRole.ENGINEER:
        query = query.filter(User.role == UserRole.ENGINEER, User.engineer_affiliation != CONSULTANT_AFFILIATION)
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
    project = manageable_project(db, current_user, project_id, "project.manage_members")

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not rbac.is_staffable(db, user):
        # The same rule the candidate list applies, so the endpoint and the list
        # that feeds it cannot disagree. Covers a deactivated account and a
        # retired one parked on the archived role — assigning the latter would
        # create a membership that grants nothing and confuse whoever did it.
        raise HTTPException(
            status_code=400,
            detail="This account cannot be assigned to a project",
        )
    # The configurable role, when the client sent one. Everything below still
    # writes `role_on_project` so the legacy column stays truthful until the
    # contract migration drops it.
    project_role = _validated_project_role(db, data.project_role_id, data.party_id, project_id)
    # `role_on_project` is the retired column. It is still NOT NULL, so it is
    # still written — derived from the account rather than asked for, because
    # nothing reads it to make a decision any more.
    #
    # What used to stand here was two branches on the *actor's* legacy role: a
    # project manager could add only Engineers and Consultants and only to the
    # project they managed, an administrator could add one of four fixed enum
    # values, and both demanded the requested value match the account's global
    # role. Every one of those is the retired model. Who may staff a project is
    # `project.manage_members`, already checked by `manageable_project` above;
    # what somebody may be *on* the project is `_validated_project_role`, which
    # enforces the rule that actually matters — an internal-only role cannot be
    # given to somebody taking part for an outside party.
    expected_project_role = (
        UserRole.CONSULTANT
        if user.role == UserRole.ENGINEER
        and user.engineer_affiliation == "external_consultant"
        else user.role
    )
    data.role_on_project = expected_project_role

    active_member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id, ProjectMember.is_active == True).first()
    if active_member:
        raise HTTPException(status_code=409, detail="User is already an active member of this project")
    # Site responsibility is a project assignment, not a job title. What used
    # to stand here was `user.role != UserRole.ENGINEER or is_external_consultant`,
    # and its first half was the retired model: it read the legacy enum on the
    # *account*, so an office's own manager, architect or surveyor could not
    # carry the site on a project the office itself runs — which is the whole
    # point of a configurable role model. That half is gone.
    #
    # What replaces it is structural and reads the *membership*: somebody
    # taking part for an outside party does not carry the office's site
    # responsibility. That is the rule `update_member_assignment` has always
    # enforced, and the rule the write below already applied — this guard
    # simply stopped disagreeing with it.
    #
    # The `external_consultant` half is gone too, now that the product
    # direction is settled: a consultant-side user is consulting-office staff.
    # The office *is* the consultant, so an account carrying that retired
    # affiliation is internal, and there is no reason it cannot carry the site
    # on a project the office runs. `rbac_backfill` already migrates those
    # accounts onto `senior_engineer`, an internal role, so the guard was the
    # last place still treating them as outsiders.
    if data.is_site_engineer and data.party_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Somebody taking part for an outside party cannot carry site responsibility",
        )

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
    if project_role is not None:
        member.project_role_id = project_role.id
    member.party_id = data.party_id
    # Site responsibility is a project assignment, not a role: any number of
    # people may carry it, of any discipline. The one structural rule is that
    # somebody taking part for an outside party does not carry the office's
    # site responsibility.
    member.is_site_engineer = bool(data.is_site_engineer and data.party_id is None)
    member.assigned_by_id = current_user.id
    _set_member_disciplines(db, member, data.discipline_ids)
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
    project = manageable_project(db, current_user, project_id, "project.manage_members")
    member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id, ProjectMember.is_active == True).first()
    if not member:
        raise HTTPException(status_code=404, detail="Active project member not found")
    previous = member.is_site_engineer
    if data.assignment_title is not None:
        member.assignment_title = data.assignment_title.strip() or None
    if data.is_site_engineer is not None:
        if data.is_site_engineer and member.party_id is not None:
            raise HTTPException(
                status_code=400,
                detail="Somebody taking part for an outside party cannot carry site responsibility",
            )
        member.is_site_engineer = data.is_site_engineer
    if data.project_role_id is not None:
        role = _validated_project_role(db, data.project_role_id, member.party_id, project_id)
        if role is not None:
            member.project_role_id = role.id
    if data.discipline_ids is not None:
        _set_member_disciplines(db, member, data.discipline_ids)
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
    manageable_project(db, current_user, project_id, "project.manage_members")

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # The office's principals are changed in project setup, not here. The
    # branch above this asked whether the *actor* was a PROJECT_MANAGER and
    # narrowed what they could remove to two enum values, which said nothing
    # about a role an office had created.
    if member.role_on_project in {UserRole.OWNER, UserRole.PROJECT_MANAGER}:
        raise HTTPException(status_code=400, detail="Reassign the project owner or manager before removing this membership")

    assigned_tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignees.any(User.id == user_id),
    ).all()
    active_tasks = [task for task in assigned_tasks if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}]
    # Somebody who sees the whole project can take the consequences of
    # unassigning live work; somebody narrowed to their own cannot.
    if active_tasks and not has_permission(db, current_user, "task.view_all", project_id):
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
    # Moving somebody between projects touches both teams, so it needs the
    # team-management capability on each of them.
    #
    # The target project was the gap. Both projects went through
    # `get_manageable_project_or_403`, which asked "administrator, or the manager
    # this project is assigned to" — so `project.manage_members` governed the
    # source (via the `require` below) and had no say at all over the
    # destination. An office role granted team management on both projects
    # passed the first check and was refused by the second; the permission model
    # simply did not reach the target. Both now resolve through the same code.
    #
    # The `require` is kept ahead of the same-project check so an unauthorised
    # caller still gets 403 rather than learning, via a 400, that the two ids
    # they guessed happen to match.
    require(db, current_user, "project.manage_members", project_id)
    if data.target_project_id == project_id:
        raise HTTPException(status_code=400, detail="Source and target projects must be different")

    source_project = manageable_project(db, current_user, project_id, "project.manage_members")
    target_project = manageable_project(
        db, current_user, data.target_project_id, "project.manage_members"
    )
    source_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.is_active == True,
    ).first()
    if not source_member:
        raise HTTPException(status_code=404, detail="Active source project membership not found")
    if source_member.role_on_project not in {UserRole.ENGINEER, UserRole.CONSULTANT}:
        raise HTTPException(status_code=400, detail="Only Engineers and Consultants can be transferred")

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
    # Same rule as the two endpoints above, and for the same reason: site
    # responsibility follows the assignment, not the account's legacy role.
    target_member.party_id = source_member.party_id
    target_member.is_site_engineer = bool(
        data.is_site_engineer and source_member.party_id is None
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
    # `client_portal.view` is this check, named. Its default holders are ADMIN
    # and OWNER, exactly the set the role comparison admitted, and it is
    # deliberately not `office_only`: the client is an external party and this
    # is the one view the platform builds for them, so the ceiling that strips
    # the office's own authority must not strip this too.
    #
    # `require` re-checks project access for a project-scoped code, which is
    # what the second refusal below used to do by hand.
    require(db, current_user, "client_portal.view", project_id)

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
    # "What changed since I was last here" uses this owner's own previous visit.
    # The 7-day window is only a first-visit fallback, not the general answer.
    now = datetime.now(timezone.utc)
    view_state = db.query(ProjectViewState).filter(
        ProjectViewState.user_id == current_user.id, ProjectViewState.project_id == project_id,
    ).first()
    since, first_visit = visit_boundary(view_state, now=now)
    verified_tasks_since = db.query(Task).filter(
        Task.project_id == project_id, Task.status == TaskStatus.DONE,
        Task.review_status == "approved", Task.updated_at >= since,
    ).count()
    approved_changes_since = db.query(DesignChange).filter(
        DesignChange.project_id == project_id, DesignChange.status == DesignChangeStatus.APPROVED,
        DesignChange.updated_at >= since,
    ).count()
    # Record this visit last, so the numbers above describe the *previous* one.
    record_visit(db, user_id=current_user.id, project_id=project_id, now=now)
    db.commit()
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
        since_last_visit={"periodDays": max(1, (now - since).days),
                          "since": since,
                          "basis": "FIRST_RECORDED_VISIT" if first_visit else "YOUR_PREVIOUS_VISIT",
                          "previousVisitAt": None if first_visit else since,
                          "verifiedTasks": verified_tasks_since,
                          "approvedDesignChanges": approved_changes_since,
                          "verifiedSiteReports": sum(item.created_at >= since for item in verified_reports),
                          "requestsAwaitingClarification": sum(item.status == "NEEDS_CLARIFICATION" for item in pending_owner_requests),
                          "nextEngineerVisit": upcoming_site_visits[0].scheduled_start if upcoming_site_visits else None,
                          "officialInformationOnly": True},
    )
