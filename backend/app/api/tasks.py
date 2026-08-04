from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
import uuid
import json
from datetime import date, datetime, timezone

from app.db.database import get_db
from app.models.enums import (
    TaskStatus,
    TaskPriority,
    UserRole,
    UserStatus,
    NotificationType,
    IssueSeverity,
    IssueStatus,
)
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.task import Task, TaskDependency, TaskComment, TaskReview
from app.models.notification import Notification
from app.models.milestone import Milestone
from app.models.audit_log import AuditLog
from app.models.attachment import Attachment
from app.models.user import User
from app.schemas.task import (
    TaskOut,
    TaskCreate,
    TaskUpdate,
    TaskDependencyOut,
    TaskDependencyCreate,
    TaskAnalytics,
    TaskReorderRequest,
    TaskReviewRequest,
    TaskCommentCreate,
    TaskCommentOut,
    TaskReviewOut,
    TaskProgressUpdate,
    TaskWorkUpdateCreate,
    TaskBlockerCreate,
    TaskReviewSubmission,
    TaskClarificationRequest,
    TaskClarificationResponse,
)
from app.schemas.issue import IssueOut
from app.core.deps import (
    get_current_user,
    user_has_project_access,
    accessible_project_ids,
    is_main_contractor_engineer,
    is_consultant_engineer,
    is_worker,
)
from app.core.schedule_dates import inclusive_duration_days
from app.services.audit_service import record_audit
from app.services.consultant_approval_service import (
    authorized_consultant_ids,
    can_consultant_review_task,
    normalize_discipline,
)
from app.services.file_storage import delete_upload

router = APIRouter(prefix="/tasks", tags=["Tasks"])

ENGINEER_ROLES = {UserRole.ENGINEER}
TASK_ASSIGNEE_ROLES = {
    UserRole.ENGINEER, UserRole.CONSULTANT, UserRole.PROJECT_MANAGER, UserRole.WORKER
}

def _notify(db: Session, user_id, title: str, message: str, task: Task, notification_type: NotificationType) -> None:
    if not user_id:
        return
    db.add(Notification(user_id=user_id, title=title, message=message, type=notification_type,
                        project_id=task.project_id, task_id=task.id,
                        related_entity_type="TASK", related_entity_id=task.id))

def _refresh_project_progress(db: Session, project_id) -> None:
    db.flush()
    project = db.get(Project, project_id)
    if not project:
        return
    values = [float(value or 0) for (value,) in db.query(Task.progress_percentage).filter(Task.project_id == project_id).all()]
    project.completion_percentage = round(sum(values) / len(values), 2) if values else 0

def _duration_days(start: date, end: date) -> int:
    try:
        return inclusive_duration_days(start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Planned end date must be on or after start date") from exc

def _invalidate_critical_path(db: Session, project_id) -> None:
    db.query(Task).filter(Task.project_id == project_id).update(
        {Task.is_critical_path: False, Task.total_float_days: None},
        synchronize_session=False,
    )


def _accessible_project_ids(db: Session, current_user: User):
    return accessible_project_ids(db, current_user)


def _get_task_or_403(task_id: uuid.UUID, db: Session, current_user: User) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not user_has_project_access(db, current_user, task.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this task")
    if current_user.role == UserRole.ENGINEER:
        if is_main_contractor_engineer(current_user):
            if not any(assignee.id == current_user.id for assignee in task.assignees):
                raise HTTPException(status_code=403, detail="This task is not assigned to you")
        elif is_consultant_engineer(current_user):
            has_submission = db.query(TaskReview.id).filter(TaskReview.task_id == task.id).first() is not None
            if not task.review_required or not has_submission or not _can_consult_task(db, current_user, task):
                raise HTTPException(status_code=403, detail="You are not authorized to review this task")
        else:
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    elif is_worker(current_user):
        if not any(assignee.id == current_user.id for assignee in task.assignees):
            raise HTTPException(status_code=403, detail="This task is not assigned to you")
    return task


def _has_project_role(db: Session, user: User, project_id: uuid.UUID, role: UserRole) -> bool:
    return bool(db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.role_on_project == role,
        ProjectMember.is_active == True,
    ).first())


def _is_project_manager(db: Session, user: User, project_id: uuid.UUID) -> bool:
    project = db.get(Project, project_id)
    return bool(user.role == UserRole.PROJECT_MANAGER and project and project.project_manager_id == user.id)


def _is_consultant(db: Session, user: User, project_id: uuid.UUID) -> bool:
    return is_consultant_engineer(user) and _has_project_role(db, user, project_id, UserRole.CONSULTANT)

def _can_consult_task(db: Session, user: User, task: Task) -> bool:
    return can_consultant_review_task(db, user, task)


def _can_review_task(db: Session, user: User, task: Task) -> bool:
    return _is_project_manager(db, user, task.project_id) or _can_consult_task(db, user, task)


def _validate_milestone_id(db: Session, project_id: uuid.UUID, milestone_id: uuid.UUID | None) -> uuid.UUID | None:
    if milestone_id is None:
        return None
    milestone = db.get(Milestone, milestone_id)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    if milestone.project_id != project_id:
        raise HTTPException(status_code=400, detail="Task milestone must belong to the same project")
    return milestone.id


def _normalized_discipline(value: str | None) -> str | None:
    return normalize_discipline(value)


def _validate_task_assignees(
    db: Session,
    project_id: uuid.UUID,
    assignee_ids: list[uuid.UUID],
    discipline: str | None = None,
) -> list[User]:
    if len(assignee_ids) != len(set(assignee_ids)):
        raise HTTPException(status_code=409, detail="Duplicate task assignees are not allowed")
    if not assignee_ids:
        return []
    rows = db.query(ProjectMember, User).join(User, User.id == ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id.in_(assignee_ids),
        ProjectMember.role_on_project.in_(TASK_ASSIGNEE_ROLES),
        ProjectMember.is_active == True,
        User.role.in_(TASK_ASSIGNEE_ROLES),
        User.status == UserStatus.ACTIVE,
    ).all()
    by_id = {user.id: (membership, user) for membership, user in rows}
    if set(by_id) != set(assignee_ids):
        raise HTTPException(
            status_code=400,
            detail="Every assignee must be an active Engineer, Worker, Consultant, or assigned Project Manager on this project",
        )
    project = db.get(Project, project_id)
    effective_discipline = _normalized_discipline(discipline)
    for assignee_id in assignee_ids:
        membership, assignee = by_id[assignee_id]
        if membership.role_on_project == UserRole.PROJECT_MANAGER:
            if not project or project.project_manager_id != assignee_id:
                raise HTTPException(status_code=400, detail="Only this project's assigned Project Manager is eligible")
        if assignee.role == UserRole.ENGINEER:
            if assignee.engineer_affiliation != "main_contractor":
                raise HTTPException(status_code=400, detail="Execution tasks may only be assigned to Main Contractor Engineers")
            profile_discipline = _normalized_discipline(
                assignee.engineer_profile.discipline.value if assignee.engineer_profile else None
            )
            if effective_discipline and profile_discipline != effective_discipline:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{assignee.full_name} is a {profile_discipline or 'non-specialized'} Engineer "
                        f"and cannot be assigned to a {effective_discipline} task"
                    ),
                )
    return [by_id[assignee_id][1] for assignee_id in assignee_ids]


def _is_task_engineer(task: Task, user: User) -> bool:
    return is_main_contractor_engineer(user) and any(assignee.id == user.id for assignee in task.assignees)


def _notify_assignees(
    db: Session,
    task: Task,
    title: str,
    message: str,
    notification_type: NotificationType,
    exclude_ids: set[uuid.UUID] | None = None,
) -> None:
    excluded = exclude_ids or set()
    for assignee in task.assignees:
        if assignee.id not in excluded:
            _notify(db, assignee.id, title, message, task, notification_type)


def _consultant_reviewer_ids(db: Session, task: Task) -> set[uuid.UUID]:
    """Return active Consultants authorized by the project's current configuration."""
    return authorized_consultant_ids(db, task.project_id, task.discipline)


def _active_review_query(db: Session, task_id: uuid.UUID):
    return db.query(TaskReview).filter(
        TaskReview.task_id == task_id,
        TaskReview.status.in_(["pending", "in_review", "clarification_requested"]),
    )


def _claimed_by_authorized_other(
    db: Session, review: TaskReview, current_user: User, task: Task
) -> bool:
    if not review.reviewed_by_id or review.reviewed_by_id == current_user.id:
        return False
    previous_reviewer = db.get(User, review.reviewed_by_id)
    return bool(
        previous_reviewer
        and can_consultant_review_task(db, previous_reviewer, task)
    )


def _notify_project_manager(
    db: Session,
    task: Task,
    title: str,
    message: str,
    notification_type: NotificationType = NotificationType.TASK_UPDATED,
) -> None:
    project = db.get(Project, task.project_id)
    if project and project.project_manager_id:
        _notify(db, project.project_manager_id, title, message, task, notification_type)


def _next_task_code(db: Session, project_id: uuid.UUID) -> str:
    project = db.query(Project).filter(Project.id == project_id).with_for_update().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.task_code_counter = int(project.task_code_counter or 0) + 1
    db.flush()
    return f"TSK-{project.task_code_counter:03d}"


def _validate_dependency_ids(db: Session, task: Task, dependency_ids: list[uuid.UUID]) -> list[Task]:
    if len(dependency_ids) != len(set(dependency_ids)):
        raise HTTPException(status_code=409, detail="Duplicate task dependencies are not allowed")
    if task.id in dependency_ids:
        raise HTTPException(status_code=400, detail="A task cannot depend on itself")
    predecessors = db.query(Task).filter(Task.id.in_(dependency_ids)).all() if dependency_ids else []
    if len(predecessors) != len(dependency_ids):
        raise HTTPException(status_code=404, detail="One or more dependency tasks do not exist")
    if any(predecessor.project_id != task.project_id for predecessor in predecessors):
        raise HTTPException(status_code=400, detail="Task dependencies must belong to the same project")

    for predecessor in predecessors:
        pending = [predecessor.id]
        visited = set()
        while pending:
            current_id = pending.pop()
            if current_id == task.id:
                raise HTTPException(status_code=400, detail="Dependency would create a circular task chain")
            if current_id in visited:
                continue
            visited.add(current_id)
            pending.extend(
                predecessor_id for (predecessor_id,) in db.query(TaskDependency.depends_on_task_id)
                .filter(TaskDependency.task_id == current_id).all()
            )
    return predecessors


def _replace_task_dependencies(db: Session, task: Task, dependency_ids: list[uuid.UUID]) -> tuple[list[uuid.UUID], list[Task]]:
    predecessors = _validate_dependency_ids(db, task, dependency_ids)
    previous_ids = [dependency_id for (dependency_id,) in db.query(TaskDependency.depends_on_task_id)
                    .filter(TaskDependency.task_id == task.id).all()]
    db.query(TaskDependency).filter(TaskDependency.task_id == task.id).delete(synchronize_session=False)
    for predecessor in predecessors:
        db.add(TaskDependency(
            task_id=task.id,
            depends_on_task_id=predecessor.id,
        ))
    db.flush()
    return previous_ids, predecessors

def _ensure_dependencies_complete(db: Session, task: Task) -> None:
    incomplete = db.query(TaskDependency).join(
        Task, Task.id == TaskDependency.depends_on_task_id
    ).filter(TaskDependency.task_id == task.id, Task.status != TaskStatus.DONE).first()
    if incomplete:
        raise HTTPException(status_code=400, detail="Task cannot start until all dependencies are Done")


@router.get("", response_model=List[TaskOut])
def list_tasks(
    project_id: Optional[uuid.UUID] = None,
    assignee_id: Optional[uuid.UUID] = None,
    status: Optional[TaskStatus] = None,
    discipline: Optional[str] = None,
    priority: Optional[TaskPriority] = None,
    search: Optional[str] = None,
    is_critical_path: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Task)
    accessible_project_ids = _accessible_project_ids(db, current_user)
    if accessible_project_ids is not None:
        query = query.filter(Task.project_id.in_(accessible_project_ids))
    if current_user.role == UserRole.ENGINEER:
        if not project_id:
            raise HTTPException(status_code=400, detail="Engineer task queries require a selected project")
        if is_main_contractor_engineer(current_user):
            query = query.filter(Task.assignees.any(User.id == current_user.id))
        elif is_consultant_engineer(current_user):
            query = query.filter(
                Task.review_required == True,
                Task.id.in_(db.query(TaskReview.task_id)),
            )
        else:
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    elif is_worker(current_user):
        query = query.filter(Task.assignees.any(User.id == current_user.id))
    elif current_user.role == UserRole.CONSULTANT and current_user.engineer_profile:
        discipline = current_user.engineer_profile.discipline.value
        accepted = [discipline, "architectural"] if discipline == "architect" else [discipline]
        query = query.filter(Task.discipline.in_(accepted))
    if project_id:
        if not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        query = query.filter(Task.project_id == project_id)
    if assignee_id:
        query = query.filter(Task.assignees.any(User.id == assignee_id))
    if status:
        query = query.filter(Task.status == status)
    if discipline:
        query = query.filter(Task.discipline == discipline)
    if priority:
        query = query.filter(Task.priority == priority)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            Task.name.ilike(term)
            | Task.task_code.ilike(term)
            | Task.description.ilike(term)
        )
    if is_critical_path is not None:
        query = query.filter(Task.is_critical_path == is_critical_path)
    tasks = query.order_by(Task.sort_order, Task.created_at).all()
    if is_consultant_engineer(current_user):
        tasks = [task for task in tasks if _can_consult_task(db, current_user, task)]
    return tasks


@router.get("/my-tasks", response_model=List[TaskOut])
def get_my_tasks(
    status: Optional[TaskStatus] = None,
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.ENGINEER and not is_main_contractor_engineer(current_user):
        raise HTTPException(status_code=403, detail="Only Main Contractor Engineers have execution tasks")
    if current_user.role in {UserRole.ENGINEER, UserRole.WORKER} and not project_id:
        raise HTTPException(status_code=400, detail="Field task queries require a selected project")
    query = db.query(Task).filter(Task.assignees.any(User.id == current_user.id))
    if project_id:
        if not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        query = query.filter(Task.project_id == project_id)
    if status:
        query = query.filter(Task.status == status)
    return query.all()


@router.get("/project/{project_id}", response_model=List[TaskOut])
def get_tasks_by_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(Task).filter(Task.project_id == project_id)
    if current_user.role == UserRole.ENGINEER:
        if is_main_contractor_engineer(current_user):
            query = query.filter(Task.assignees.any(User.id == current_user.id))
        elif is_consultant_engineer(current_user):
            query = query.filter(
                Task.review_required == True,
                Task.id.in_(db.query(TaskReview.task_id)),
            )
        else:
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    elif is_worker(current_user):
        query = query.filter(Task.assignees.any(User.id == current_user.id))
    tasks = query.order_by(Task.task_code).all()
    if is_consultant_engineer(current_user):
        tasks = [task for task in tasks if _can_consult_task(db, current_user, task)]
    return tasks


@router.get("/analytics/project/{project_id}", response_model=TaskAnalytics)
def get_task_analytics(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_worker(current_user):
        raise HTTPException(status_code=403, detail="Workers cannot access task analytics")
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    task_query = db.query(Task).filter(Task.project_id == project_id)
    if current_user.role == UserRole.ENGINEER:
        if not is_main_contractor_engineer(current_user):
            raise HTTPException(status_code=403, detail="Use the Consultant Engineer dashboard for review metrics")
        task_query = task_query.filter(Task.assignees.any(User.id == current_user.id))
    tasks = task_query.all()
    total = len(tasks)

    todo = sum(1 for t in tasks if t.status.value == "todo")
    in_progress = sum(1 for t in tasks if t.status.value == "in_progress")
    under_review = sum(1 for t in tasks if t.status.value == "under_review")
    rework_required = sum(1 for t in tasks if t.status.value == "rework_required")
    blocked = sum(1 for t in tasks if t.status.value == "blocked")
    done = sum(1 for t in tasks if t.status.value == "done")
    critical_path_count = sum(1 for t in tasks if t.is_critical_path)
    rate = (done / total * 100.0) if total > 0 else 0.0

    return TaskAnalytics(
        total_tasks=total,
        todo_tasks=todo,
        in_progress_tasks=in_progress,
        under_review_tasks=under_review,
        rework_required_tasks=rework_required,
        done_tasks=done,
        blocked_tasks=blocked,
        critical_path_tasks_count=critical_path_count,
        completion_rate=rate,
    )


@router.get("/{task_id}", response_model=TaskOut)
def get_task_by_id(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_task_or_403(task_id, db, current_user)


@router.post("", response_model=TaskOut)
def create_task(
    task_data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _is_project_manager(db, current_user, task_data.project_id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can create project tasks")
    if task_data.status not in {TaskStatus.BACKLOG, TaskStatus.TODO}:
        raise HTTPException(status_code=400, detail="New tasks must start in Backlog or To Do")
    assignees = _validate_task_assignees(
        db, task_data.project_id, task_data.assignee_ids, task_data.discipline
    )
    milestone_id = _validate_milestone_id(db, task_data.project_id, task_data.milestone_id)

    task_code = _next_task_code(db, task_data.project_id)

    new_task = Task(
        project_id=task_data.project_id,
        milestone_id=milestone_id,
        task_code=task_code,
        name=task_data.name,
        description=task_data.description,
        discipline=task_data.discipline,
        status=task_data.status,
        priority=task_data.priority,
        assignees=assignees,
        created_by_id=current_user.id,
        planned_start_date=task_data.planned_start_date,
        planned_end_date=task_data.planned_end_date,
        is_milestone=task_data.is_milestone,
        progress_percentage=0.0,
        review_required=task_data.review_required,
        review_due_date=task_data.review_due_date,
    )

    if new_task.planned_start_date and new_task.planned_end_date:
        new_task.duration_days = _duration_days(new_task.planned_start_date, new_task.planned_end_date)

    db.add(new_task)
    db.flush()
    _, predecessors = _replace_task_dependencies(db, new_task, task_data.dependency_ids)
    _invalidate_critical_path(db, new_task.project_id)
    project = db.get(Project, new_task.project_id)
    _notify_assignees(
        db, new_task, "New Task Assigned",
        f'You were assigned to {new_task.task_code} — "{new_task.name}" in {project.name if project else "a project"}.',
        NotificationType.TASK_ASSIGNED,
    )
    _refresh_project_progress(db, new_task.project_id)
    record_audit(db, actor_id=current_user.id, action="created", entity_type="task", entity_id=new_task.id,
                 project_id=new_task.project_id, details={"task_code": new_task.task_code,
                    "assignee_ids": [str(value) for value in new_task.assignee_ids],
                    "dependency_ids": [str(predecessor.id) for predecessor in predecessors]})
    from app.services.domain_event_dispatcher import emit_domain_event
    emit_domain_event(
        db, project_id=new_task.project_id, event_type="TASK_CREATED",
        entity_type="TASK", entity_id=new_task.id, actor_user_id=current_user.id,
        payload={"taskCode": new_task.task_code, "status": new_task.status.value},
        correlation_id=f"task:{new_task.id}", idempotency_key=f"TASK_CREATED:{new_task.id}",
    )
    db.commit()
    db.refresh(new_task)
    return new_task


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: uuid.UUID,
    task_data: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    is_pm = _is_project_manager(db, current_user, task.project_id)
    is_assignee = _is_task_engineer(task, current_user)
    if not is_pm and not is_assignee:
        raise HTTPException(status_code=403, detail="Only the assigned PM or task engineer can update this task")
    if is_assignee and (task_data.model_fields_set - {"status", "progress_percentage"}):
        raise HTTPException(status_code=403, detail="Engineers can update execution status and progress only")

    if task_data.status in {TaskStatus.DONE, TaskStatus.UNDER_REVIEW} and task_data.status != task.status:
        raise HTTPException(status_code=400, detail="Use the review workflow to submit or complete tasks")
    assignments_changed = "assignee_ids" in task_data.model_fields_set
    replacement_assignees: list[User] = []
    if assignments_changed:
        if not is_pm:
            raise HTTPException(status_code=403, detail="Only the Project Manager can assign tasks")
        replacement_assignees = _validate_task_assignees(
            db,
            task.project_id,
            task_data.assignee_ids or [],
            task_data.discipline if task_data.discipline is not None else task.discipline,
        )
    elif task_data.discipline is not None and is_pm:
        _validate_task_assignees(
            db, task.project_id, list(task.assignee_ids), task_data.discipline
        )
    previous_assignee_ids = set(task.assignee_ids)
    previous_status = task.status
    schedule_changed = bool(task_data.model_fields_set & {"planned_start_date", "planned_end_date"})
    dependencies_changed = "dependency_ids" in task_data.model_fields_set
    milestone_changed = "milestone_id" in task_data.model_fields_set
    review_rule_changed = bool(task_data.model_fields_set & {"review_required", "review_due_date"})
    if review_rule_changed and not is_pm:
        raise HTTPException(status_code=403, detail="Only the Project Manager can configure Consultant review requirements")
    if task_data.review_required is False and db.query(TaskReview.id).filter(TaskReview.task_id == task.id).first():
        raise HTTPException(status_code=409, detail="Review requirement cannot be removed after a submission exists")

    if task_data.name is not None:
        task.name = task_data.name
    if task_data.description is not None:
        task.description = task_data.description
    if task_data.discipline is not None:
        task.discipline = task_data.discipline
    if task_data.status is not None:
        if is_assignee and task_data.status != TaskStatus.IN_PROGRESS:
            raise HTTPException(status_code=403, detail="Use the execution workflow actions to change task status")
        if is_assignee and task_data.status == TaskStatus.IN_PROGRESS and task.status not in {
            TaskStatus.TODO,
            TaskStatus.REWORK_REQUIRED,
        }:
            raise HTTPException(status_code=400, detail="Only To Do or Rework Required tasks can be started")
        if task_data.status == TaskStatus.IN_PROGRESS:
            _ensure_dependencies_complete(db, task)
        task.status = task_data.status
        if task_data.status == TaskStatus.UNDER_REVIEW:
            task.progress_percentage = 100.0
            task.submitted_for_review_at = date.today()
            task.review_status = "pending"
            task.rejection_reason = None
        elif task_data.status == TaskStatus.IN_PROGRESS and float(task.progress_percentage) == 0.0:
            task.actual_start_date = date.today()
    if task_data.priority is not None:
        task.priority = task_data.priority
    if assignments_changed:
        task.assignees = replacement_assignees
    if task_data.planned_start_date is not None:
        task.planned_start_date = task_data.planned_start_date
    if task_data.planned_end_date is not None:
        task.planned_end_date = task_data.planned_end_date
    if task_data.actual_start_date is not None:
        task.actual_start_date = task_data.actual_start_date
    if task_data.actual_end_date is not None:
        task.actual_end_date = task_data.actual_end_date
    if task_data.progress_percentage is not None:
        if is_assignee and task.status not in {TaskStatus.IN_PROGRESS, TaskStatus.REWORK_REQUIRED}:
            raise HTTPException(status_code=400, detail="Start the task before updating progress")
        if (
            is_assignee
            and float(task_data.progress_percentage) < float(task.progress_percentage or 0)
            and task.status != TaskStatus.REWORK_REQUIRED
            and task.review_status != "rejected"
        ):
            raise HTTPException(status_code=400, detail="Progress cannot decrease unless the task was returned for rework")
        if is_assignee and task_data.progress_percentage > 0:
            _ensure_dependencies_complete(db, task)
        task.progress_percentage = task_data.progress_percentage
        if task_data.progress_percentage > 0.0 and task.status in {TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.REWORK_REQUIRED}:
            task.status = TaskStatus.IN_PROGRESS
            task.actual_start_date = date.today()
    if task_data.is_critical_path is not None:
        task.is_critical_path = task_data.is_critical_path
    if task_data.is_milestone is not None:
        task.is_milestone = task_data.is_milestone
    if task_data.total_float_days is not None:
        task.total_float_days = task_data.total_float_days
    if task_data.review_required is not None:
        task.review_required = task_data.review_required
    if "review_due_date" in task_data.model_fields_set:
        task.review_due_date = task_data.review_due_date
    if milestone_changed:
        if not is_pm:
            raise HTTPException(status_code=403, detail="Only the Project Manager can link tasks to milestones")
        task.milestone_id = _validate_milestone_id(db, task.project_id, task_data.milestone_id)

    project = db.get(Project, task.project_id)
    newly_assigned_ids = set(task.assignee_ids) - previous_assignee_ids
    for assignee_id in newly_assigned_ids:
        _notify(db, assignee_id, "New Task Assigned",
                f'You were assigned to {task.task_code} — "{task.name}" in {project.name if project else "a project"}.',
                task, NotificationType.TASK_ASSIGNED)
    engineer_relevant_changes = task_data.model_fields_set & {
        "name", "description", "discipline", "priority", "planned_start_date",
        "planned_end_date", "dependency_ids", "milestone_id",
        "review_required", "review_due_date",
    }
    if is_pm and engineer_relevant_changes:
        changed_label = ", ".join(sorted(value.replace("_", " ") for value in engineer_relevant_changes))
        _notify_assignees(
            db,
            task,
            "Task Details Updated",
            f"{task.task_code} was updated: {changed_label}.",
            NotificationType.TASK_UPDATED,
            exclude_ids={current_user.id} | newly_assigned_ids,
        )
    if task.status == TaskStatus.BLOCKED and previous_status != TaskStatus.BLOCKED:
        recipients = set(task.assignee_ids) | ({project.project_manager_id} if project and project.project_manager_id else set())
        recipients.discard(current_user.id)
        for recipient in recipients:
            _notify(db, recipient, "Task Blocked", f'"{task.name}" is now blocked.', task, NotificationType.TASK_UPDATED)

    if task.planned_start_date and task.planned_end_date:
        task.duration_days = _duration_days(task.planned_start_date, task.planned_end_date)
    elif schedule_changed:
        task.duration_days = None
    previous_dependency_ids: list[uuid.UUID] = []
    predecessors: list[Task] = []
    if dependencies_changed:
        previous_dependency_ids, predecessors = _replace_task_dependencies(
            db, task, task_data.dependency_ids or []
        )
    if schedule_changed or dependencies_changed:
        _invalidate_critical_path(db, task.project_id)

    _refresh_project_progress(db, task.project_id)
    record_audit(db, actor_id=current_user.id, action="updated", entity_type="task", entity_id=task.id,
                 project_id=task.project_id, details={"task_code": task.task_code,
                    "previous_assignee_ids": [str(value) for value in previous_assignee_ids] if assignments_changed else None,
                    "assignee_ids": [str(value) for value in task.assignee_ids] if assignments_changed else None,
                    "previous_dependency_ids": [str(value) for value in previous_dependency_ids] if dependencies_changed else None,
                    "dependency_ids": [str(value.id) for value in predecessors] if dependencies_changed else None})
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_project_manager(db, current_user, task.project_id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can delete tasks")
    record_audit(db, actor_id=current_user.id, action="deleted", entity_type="task", entity_id=task.id, project_id=task.project_id)

    # Clear both incoming and outgoing dependency edges explicitly. Besides
    # keeping the schedule graph consistent, this avoids ORM state conflicts
    # when a reviewed predecessor is deleted while dependants still exist.
    db.query(TaskDependency).filter(
        or_(TaskDependency.task_id == task.id, TaskDependency.depends_on_task_id == task.id)
    ).delete(synchronize_session=False)

    # Generic attachments intentionally do not have polymorphic foreign keys.
    # Remove task/review files explicitly before deleting their owning records,
    # and delete review attempts first so resubmission self-links cannot leave a
    # reviewed task undeletable.
    review_ids = [row[0] for row in db.query(TaskReview.id).filter(TaskReview.task_id == task.id).all()]
    attachment_filters = [and_(Attachment.entity_type == "TASK", Attachment.entity_id == task.id)]
    if review_ids:
        attachment_filters.append(
            and_(Attachment.entity_type == "TASK_REVIEW", Attachment.entity_id.in_(review_ids))
        )
    linked_attachments = db.query(Attachment).filter(or_(*attachment_filters)).all()
    for attachment in linked_attachments:
        delete_upload(attachment.file_url)
        db.delete(attachment)
    if review_ids:
        db.query(TaskReview).filter(
            TaskReview.id.in_(review_ids),
            TaskReview.resubmission_of_id.is_not(None),
        ).update({TaskReview.resubmission_of_id: None}, synchronize_session=False)
        db.flush()
        db.query(TaskReview).filter(TaskReview.id.in_(review_ids)).delete(synchronize_session=False)

    db.delete(task)
    project_id = task.project_id
    db.flush()
    _invalidate_critical_path(db, project_id)
    _refresh_project_progress(db, project_id)
    db.commit()
    return {"message": "Task deleted successfully"}


@router.put("/{task_id}/progress", response_model=TaskOut)
def update_task_progress(
    task_id: uuid.UUID,
    data: TaskProgressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    is_pm = _is_project_manager(db, current_user, task.project_id)
    is_assignee = _is_task_engineer(task, current_user)
    if not is_pm and not is_assignee:
        raise HTTPException(status_code=403, detail="Only the assigned PM or task engineer can update progress")

    progress = float(data.progress_percentage)
    if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE}:
        raise HTTPException(status_code=400, detail="Progress cannot change while work is under review or completed")
    previous_progress = float(task.progress_percentage or 0)
    previous_status = task.status
    if is_assignee and task.status not in {TaskStatus.IN_PROGRESS, TaskStatus.REWORK_REQUIRED}:
        raise HTTPException(status_code=400, detail="Start the task before updating progress")
    if (
        is_assignee
        and progress < previous_progress
        and task.status != TaskStatus.REWORK_REQUIRED
        and task.review_status != "rejected"
    ):
        raise HTTPException(status_code=400, detail="Progress cannot decrease unless the task was returned for rework")
    if progress > 0:
        _ensure_dependencies_complete(db, task)
    task.progress_percentage = progress
    if task.progress_percentage > 0.0 and task.status in {TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.REWORK_REQUIRED}:
        task.status = TaskStatus.IN_PROGRESS
        task.actual_start_date = date.today()

    _refresh_project_progress(db, task.project_id)
    if data.note and data.note.strip():
        db.add(TaskComment(
            task_id=task.id,
            author_id=current_user.id,
            content=f"Work update: {data.note.strip()}",
        ))
    record_audit(
        db,
        actor_id=current_user.id,
        action="progress_updated",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        details={
            "previous_progress": previous_progress,
            "progress": progress,
            "previous_status": previous_status.value,
            "status": task.status.value,
            "note": data.note.strip() if data.note else None,
        },
    )
    from app.services.ai_traceability_service import invalidate_insights_for_source
    invalidate_insights_for_source(db, project_id=task.project_id, source_type="TASK", source_id=task.id,
                                   reason="Task progress or workflow state changed")
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}/start", response_model=TaskOut)
def start_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can start this task")
    if task.status != TaskStatus.TODO:
        raise HTTPException(status_code=400, detail="Only a To Do task can be started")
    _ensure_dependencies_complete(db, task)
    open_blocker = db.query(Issue).filter(
        Issue.task_id == task.id,
        Issue.category.like("blocker:%"),
        Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
    ).first()
    if open_blocker:
        raise HTTPException(status_code=400, detail="Task cannot start while a reported blocker is unresolved")
    task.status = TaskStatus.IN_PROGRESS
    task.actual_start_date = task.actual_start_date or date.today()
    project = db.get(Project, task.project_id)
    if project and project.project_manager_id and project.project_manager_id != current_user.id:
        _notify(
            db,
            project.project_manager_id,
            "Task Started",
            f'{current_user.full_name} started {task.task_code} — "{task.name}".',
            task,
            NotificationType.TASK_UPDATED,
        )
    record_audit(db, actor_id=current_user.id, action="task_started", entity_type="task",
                 entity_id=task.id, project_id=task.project_id)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}/start-rework", response_model=TaskOut)
def start_rework(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can start rework")
    if task.status != TaskStatus.REWORK_REQUIRED:
        raise HTTPException(status_code=400, detail="Only a Rework Required task can enter corrective work")
    task.status = TaskStatus.IN_PROGRESS
    record_audit(db, actor_id=current_user.id, action="rework_started", entity_type="task",
                 entity_id=task.id, project_id=task.project_id)
    project = db.get(Project, task.project_id)
    if project and project.project_manager_id:
        _notify(db, project.project_manager_id, "Rework Started",
                f'{current_user.full_name} started corrections for {task.task_code}.', task,
                NotificationType.TASK_UPDATED)
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/work-updates", response_model=TaskCommentOut, status_code=201)
def add_work_update(
    task_id: uuid.UUID,
    data: TaskWorkUpdateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can add work updates")
    if task.status != TaskStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Work updates can only be added while the task is In Progress")
    previous_progress = float(task.progress_percentage or 0)
    if data.progress_percentage is not None:
        progress = float(data.progress_percentage)
        if progress < previous_progress and task.review_status != "rejected":
            raise HTTPException(status_code=400, detail="Progress cannot decrease during normal execution")
        if progress > 0:
            _ensure_dependencies_complete(db, task)
        task.progress_percentage = progress
    sections = [f"Work completed today: {data.work_completed_today.strip()}"]
    optional_sections = (
        ("Remaining work", data.remaining_work),
        ("Workers", str(data.workers_count) if data.workers_count is not None else None),
        ("Equipment", data.equipment_used),
        ("Materials", data.materials_used),
        ("Problems", data.problems_encountered),
        ("Notes", data.notes),
    )
    sections.extend(f"{label}: {value.strip()}" for label, value in optional_sections if value and value.strip())
    comment = TaskComment(
        task_id=task.id,
        author_id=current_user.id,
        content="\n".join(sections),
    )
    db.add(comment)
    _refresh_project_progress(db, task.project_id)
    record_audit(
        db,
        actor_id=current_user.id,
        action="work_update_added",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        details={
            "previous_progress": previous_progress,
            "progress": float(task.progress_percentage or 0),
            "workers_count": data.workers_count,
        },
    )
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/{task_id}/blockers", response_model=List[IssueOut])
def get_task_blockers(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    return db.query(Issue).filter(
        Issue.task_id == task.id,
        Issue.category.like("blocker:%"),
    ).order_by(Issue.created_at.desc()).all()


@router.post("/{task_id}/blockers", response_model=IssueOut, status_code=201)
def report_task_blocker(
    task_id: uuid.UUID,
    data: TaskBlockerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can report a blocker")
    if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE, TaskStatus.CANCELLED}:
        raise HTTPException(status_code=400, detail="A blocker cannot be added to this task state")
    category = data.category.strip().lower().replace(" ", "_")
    allowed_categories = {
        "material_unavailable",
        "previous_task_incomplete",
        "drawing_unavailable",
        "consultant_clarification_required",
        "equipment_unavailable",
        "labor_shortage",
        "site_access_issue",
        "safety_restriction",
        "technical_conflict",
        "other",
    }
    if category not in allowed_categories:
        raise HTTPException(status_code=400, detail="Unsupported blocker category")
    previous_status = task.status
    blocker = Issue(
        project_id=task.project_id,
        task_id=task.id,
        title=f"Blocker · {task.task_code} · {category.replace('_', ' ').title()}",
        description=data.description.strip(),
        category=f"blocker:{category}",
        affects_schedule=True,
        severity=data.severity,
        raised_by_id=current_user.id,
        status=IssueStatus.OPEN,
    )
    db.add(blocker)
    task.status = TaskStatus.BLOCKED
    db.flush()
    project = db.get(Project, task.project_id)
    if project and project.project_manager_id:
        _notify(
            db,
            project.project_manager_id,
            "Task Blocker Reported",
            f'{current_user.full_name} reported a {data.severity.value} blocker on {task.task_code}.',
            task,
            NotificationType.TASK_UPDATED,
        )
    record_audit(
        db,
        actor_id=current_user.id,
        action="blocker_reported",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        details={
            "blocker_id": blocker.id,
            "category": category,
            "severity": data.severity.value,
            "previous_status": previous_status.value,
        },
    )
    db.commit()
    db.refresh(blocker)
    return blocker


@router.put("/{task_id}/resume-after-blocker", response_model=TaskOut)
def resume_after_blocker(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can resume this task")
    if task.status != TaskStatus.BLOCKED:
        raise HTTPException(status_code=400, detail="Only a Blocked task can be resumed")
    unresolved = db.query(Issue).filter(
        Issue.task_id == task.id,
        Issue.category.like("blocker:%"),
        Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
    ).count()
    if unresolved:
        raise HTTPException(status_code=400, detail="The Project Manager must resolve all task blockers before work resumes")
    _ensure_dependencies_complete(db, task)
    task.status = TaskStatus.IN_PROGRESS
    record_audit(db, actor_id=current_user.id, action="task_resumed", entity_type="task",
                 entity_id=task.id, project_id=task.project_id)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}/submit-review", response_model=TaskOut)
def submit_task_for_review(
    task_id: uuid.UUID,
    data: TaskReviewSubmission | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    is_pm = _is_project_manager(db, current_user, task.project_id)
    is_assignee = _is_task_engineer(task, current_user)
    if not is_pm and not is_assignee:
        raise HTTPException(status_code=403, detail="Only the assigned PM or task engineer can submit work for review")
    if task.status not in {TaskStatus.IN_PROGRESS, TaskStatus.REWORK_REQUIRED}:
        raise HTTPException(status_code=400, detail="Only work in progress or rework can be submitted for review")
    if not task.review_required:
        raise HTTPException(status_code=400, detail="This task does not require Consultant review")
    if is_assignee and float(task.progress_percentage or 0) != 100.0:
        raise HTTPException(status_code=400, detail="Set execution progress to 100% before submitting for review")
    if is_pm:
        task.progress_percentage = 100.0
    if _active_review_query(db, task.id).with_for_update().first():
        raise HTTPException(status_code=409, detail="This task already has an active review submission")
    latest_review = db.query(TaskReview).filter(TaskReview.task_id == task.id).order_by(
        TaskReview.submission_number.desc(), TaskReview.created_at.desc()
    ).first()
    previous_review_count = db.query(TaskReview).filter(TaskReview.task_id == task.id).count()
    is_resubmission = previous_review_count > 0
    task.status = TaskStatus.UNDER_REVIEW
    task.submitted_for_review_at = date.today()
    task.review_status = "pending"
    task.rejection_reason = None
    evidence = db.query(Attachment).filter(
        Attachment.project_id == task.project_id,
        Attachment.entity_type == "TASK",
        Attachment.entity_id == task.id,
    ).order_by(Attachment.created_at.asc()).all()
    now = datetime.now(timezone.utc)
    review = TaskReview(
        task_id=task.id,
        submitted_by_id=current_user.id,
        submitted_at=now,
        submission_number=(latest_review.submission_number + 1) if latest_review else 1,
        resubmission_of_id=latest_review.id if latest_review else None,
        completion_note=(data.completion_note.strip() if data and data.completion_note else None),
        evidence_snapshot=json.dumps([
            {
                "id": str(item.id),
                "filename": item.original_filename,
                "mime_type": item.mime_type,
                "file_size_bytes": item.file_size_bytes,
                "file_url": item.file_url,
                "uploaded_at": item.created_at.isoformat(),
            }
            for item in evidence
        ]),
        status="pending",
    )
    db.add(review)
    reviewer_ids = _consultant_reviewer_ids(db, task)
    project = db.get(Project, task.project_id)
    if project and project.project_manager_id:
        reviewer_ids.add(project.project_manager_id)
    reviewer_ids.discard(current_user.id)
    for reviewer_id in reviewer_ids:
        _notify(db, reviewer_id, "Work submitted for review", task.name, task, NotificationType.APPROVAL_REQUEST)
    _refresh_project_progress(db, task.project_id)
    record_audit(
        db,
        actor_id=current_user.id,
        action="resubmitted_for_review" if is_resubmission else "submitted_for_review",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        details={"submission_attempt": review.submission_number, "evidence_count": len(evidence)},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This task already has an active review submission") from exc
    db.refresh(task)
    return task


@router.get("/{task_id}/review-authority")
def get_task_review_authority(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if is_worker(current_user):
        raise HTTPException(status_code=403, detail="Workers cannot access Consultant review authority")
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not user_has_project_access(db, current_user, task.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this task")
    reviewer_ids = _consultant_reviewer_ids(db, task)
    reviewers = db.query(User).filter(User.id.in_(reviewer_ids)).order_by(User.full_name).all() if reviewer_ids else []
    project = db.get(Project, task.project_id)
    return {
        "taskId": str(task.id),
        "approvalMode": project.consultant_approval_mode.value if project else None,
        "canReview": _can_review_task(db, current_user, task),
        "reviewers": [
            {"id": str(user.id), "fullName": user.full_name, "organization": user.organization}
            for user in reviewers
        ],
    }


@router.put("/{task_id}/complete-execution", response_model=TaskOut)
def complete_execution_without_review(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete internal contractor work without fabricating a Consultant decision."""
    _get_task_or_403(task_id, db, current_user)
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can complete execution")
    if task.review_required:
        raise HTTPException(status_code=400, detail="This task requires Consultant review before completion")
    if task.status != TaskStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Only work in progress can be completed")
    if float(task.progress_percentage or 0) != 100.0:
        raise HTTPException(status_code=400, detail="Set execution progress to 100% before completing the task")
    _ensure_dependencies_complete(db, task)
    task.status = TaskStatus.DONE
    task.actual_end_date = date.today()
    task.review_status = None
    _refresh_project_progress(db, task.project_id)
    _notify_project_manager(db, task, "Task completed", f'{current_user.full_name} completed {task.task_code}.')
    record_audit(db, actor_id=current_user.id, action="execution_completed", entity_type="task",
                 entity_id=task.id, project_id=task.project_id, details={"review_required": False})
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}/start-review", response_model=TaskReviewOut)
def start_task_review(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _can_consult_task(db, current_user, task):
        raise HTTPException(status_code=403, detail="Only an authorized Consultant Engineer can start this review")
    if task.status != TaskStatus.UNDER_REVIEW or not task.review_required:
        raise HTTPException(status_code=400, detail="This task is not eligible for Consultant review")
    review = _active_review_query(db, task.id).with_for_update().first()
    if not review:
        raise HTTPException(status_code=409, detail="This submission has already been reviewed or superseded")
    if review.status == "pending":
        review.status = "in_review"
        review.reviewed_by_id = current_user.id
        task.review_status = "in_review"
        record_audit(db, actor_id=current_user.id, action="review_started", entity_type="task_review",
                     entity_id=review.id, project_id=task.project_id,
                     details={"task_id": task.id, "submission_number": review.submission_number})
        db.commit()
        db.refresh(review)
    elif review.reviewed_by_id and review.reviewed_by_id != current_user.id:
        if _claimed_by_authorized_other(db, review, current_user, task):
            raise HTTPException(status_code=409, detail="Another Consultant Engineer has already started this review")
        previous_reviewer_id = review.reviewed_by_id
        review.reviewed_by_id = current_user.id
        record_audit(
            db, actor_id=current_user.id, action="review_reassigned_after_configuration_change",
            entity_type="task_review", entity_id=review.id, project_id=task.project_id,
            details={"task_id": task.id, "previous_reviewer_id": previous_reviewer_id},
        )
        db.commit()
        db.refresh(review)
    return review


@router.put("/{task_id}/approve", response_model=TaskOut)
def approve_task(
    task_id: uuid.UUID,
    data: TaskReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not _can_review_task(db, current_user, task):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager or an assigned consultant can approve submitted work")
    if task.status != TaskStatus.UNDER_REVIEW:
        raise HTTPException(status_code=409, detail="This submission has already been reviewed or is no longer valid")
    if not task.review_required:
        raise HTTPException(status_code=400, detail="This task does not require Consultant review")
    review = _active_review_query(db, task.id).with_for_update().first()
    if not review or review.status not in {"pending", "in_review"}:
        raise HTTPException(status_code=409, detail="This submission has already been reviewed or needs clarification")
    if _can_consult_task(db, current_user, task) and _claimed_by_authorized_other(
        db, review, current_user, task
    ):
        raise HTTPException(status_code=409, detail="Another Consultant Engineer is reviewing this submission")
    task.status = TaskStatus.DONE
    task.progress_percentage = 100.0
    task.actual_end_date = date.today()
    task.reviewed_at = date.today()
    task.reviewed_by_id = current_user.id
    task.consultant_comments = data.comments
    task.rejection_reason = None
    task.review_status = "approved"
    review.status, review.reviewed_by_id, review.comments = "approved", current_user.id, data.comments
    review.reviewed_at = datetime.now(timezone.utc)
    _notify_assignees(db, task, "Work approved", task.name, NotificationType.TASK_UPDATED)
    _notify_project_manager(db, task, "Work approved", f'{current_user.full_name} approved {task.task_code}.')
    _refresh_project_progress(db, task.project_id)
    record_audit(db, actor_id=current_user.id, action="approved", entity_type="task_review", entity_id=review.id,
                 project_id=task.project_id, details={"task_id": task.id, "submission_number": review.submission_number})
    from app.services.domain_event_dispatcher import emit_domain_event
    emit_domain_event(
        db, project_id=task.project_id, event_type="CONSULTANT_REVIEW_COMPLETED",
        entity_type="TASK_REVIEW", entity_id=review.id, actor_user_id=current_user.id,
        payload={"taskId": str(task.id), "decision": "APPROVED", "submissionNumber": review.submission_number},
        correlation_id=f"review:{review.id}", idempotency_key=f"CONSULTANT_REVIEW_APPROVED:{review.id}",
    )
    from app.services.ai_traceability_service import invalidate_insights_for_source
    invalidate_insights_for_source(db, project_id=task.project_id, source_type="TASK", source_id=task.id,
                                   reason="Task was completed and verified by an authorized reviewer")
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}/reject", response_model=TaskOut)
def reject_task(
    task_id: uuid.UUID,
    data: TaskReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not _can_review_task(db, current_user, task):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager or an assigned consultant can reject submitted work")
    if task.status != TaskStatus.UNDER_REVIEW:
        raise HTTPException(status_code=409, detail="This submission has already been reviewed or is no longer valid")
    if not task.review_required:
        raise HTTPException(status_code=400, detail="This task does not require Consultant review")
    review = _active_review_query(db, task.id).with_for_update().first()
    if not review or review.status not in {"pending", "in_review"}:
        raise HTTPException(status_code=409, detail="This submission has already been reviewed or needs clarification")
    if _can_consult_task(db, current_user, task) and _claimed_by_authorized_other(
        db, review, current_user, task
    ):
        raise HTTPException(status_code=409, detail="Another Consultant Engineer is reviewing this submission")
    consultant_decision = _can_consult_task(db, current_user, task)
    if consultant_decision:
        if not (data.rejection_reason or "").strip():
            raise HTTPException(status_code=400, detail="Rejection reason is required")
        if not (data.comments or "").strip():
            raise HTTPException(status_code=400, detail="Review comments are required")
        if not (data.required_corrections or "").strip():
            raise HTTPException(status_code=400, detail="Required corrective action is required")
    reason = (data.rejection_reason or data.comments or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A rejection comment is required")
    corrections = (data.required_corrections or reason).strip()
    task.status = TaskStatus.REWORK_REQUIRED
    task.reviewed_at = date.today()
    task.reviewed_by_id = current_user.id
    task.consultant_comments = data.comments
    task.rejection_reason = reason
    task.review_status = "rejected"
    review.status, review.reviewed_by_id = "rejected", current_user.id
    review.comments, review.rejection_reason = data.comments, task.rejection_reason
    review.required_corrections = corrections
    review.reviewed_at = datetime.now(timezone.utc)
    _notify_assignees(db, task, "Rework required", task.rejection_reason or task.name, NotificationType.TASK_UPDATED)
    _notify_project_manager(db, task, "Rework requested", f'{current_user.full_name} returned {task.task_code} for correction.')
    record_audit(db, actor_id=current_user.id, action="rework_requested", entity_type="task_review",
                 entity_id=review.id, project_id=task.project_id,
                 details={"task_id": task.id, "reason": task.rejection_reason,
                           "required_corrections": corrections, "submission_number": review.submission_number})
    from app.services.domain_event_dispatcher import emit_domain_event
    emit_domain_event(
        db, project_id=task.project_id, event_type="CONSULTANT_REVIEW_COMPLETED",
        entity_type="TASK_REVIEW", entity_id=review.id, actor_user_id=current_user.id,
        payload={"taskId": str(task.id), "decision": "REJECTED", "submissionNumber": review.submission_number},
        correlation_id=f"review:{review.id}", idempotency_key=f"CONSULTANT_REVIEW_REJECTED:{review.id}",
    )
    from app.services.ai_traceability_service import invalidate_insights_for_source
    invalidate_insights_for_source(db, project_id=task.project_id, source_type="TASK", source_id=task.id,
                                   reason="Responsible reviewer rejected the submitted task state", rejected=True)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}/request-clarification", response_model=TaskReviewOut)
def request_task_clarification(
    task_id: uuid.UUID,
    data: TaskClarificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not _can_consult_task(db, current_user, task):
        raise HTTPException(status_code=403, detail="Only an authorized Consultant Engineer can request clarification")
    if task.status != TaskStatus.UNDER_REVIEW or not task.review_required:
        raise HTTPException(status_code=400, detail="This task is not eligible for clarification")
    review = _active_review_query(db, task.id).with_for_update().first()
    if not review or review.status not in {"pending", "in_review"}:
        raise HTTPException(status_code=409, detail="This submission cannot receive a clarification request")
    if review.reviewed_by_id and review.reviewed_by_id != current_user.id:
        raise HTTPException(status_code=409, detail="Another Consultant Engineer is reviewing this submission")
    review.status = "clarification_requested"
    review.reviewed_by_id = current_user.id
    review.clarification_question = data.question.strip()
    review.clarification_response = None
    review.clarification_requested_at = datetime.now(timezone.utc)
    review.clarification_responded_at = None
    task.review_status = "clarification_requested"
    _notify_assignees(db, task, "Clarification requested", review.clarification_question,
                      NotificationType.TASK_UPDATED)
    _notify_project_manager(db, task, "Clarification requested", f'{current_user.full_name} requested clarification for {task.task_code}.')
    record_audit(db, actor_id=current_user.id, action="clarification_requested", entity_type="task_review",
                 entity_id=review.id, project_id=task.project_id,
                 details={"task_id": task.id, "submission_number": review.submission_number})
    db.commit()
    db.refresh(review)
    return review


@router.put("/{task_id}/respond-clarification", response_model=TaskReviewOut)
def respond_to_task_clarification(
    task_id: uuid.UUID,
    data: TaskClarificationResponse,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not _is_task_engineer(task, current_user):
        raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can respond")
    if task.status != TaskStatus.UNDER_REVIEW:
        raise HTTPException(status_code=400, detail="This task is not under review")
    review = _active_review_query(db, task.id).with_for_update().first()
    if not review or review.status != "clarification_requested":
        raise HTTPException(status_code=409, detail="No clarification response is currently required")
    review.clarification_response = data.response.strip()
    review.clarification_responded_at = datetime.now(timezone.utc)
    review.status = "pending"
    review.reviewed_by_id = None
    task.review_status = "pending"
    for reviewer_id in _consultant_reviewer_ids(db, task):
        _notify(db, reviewer_id, "Clarification response received",
                f'{current_user.full_name} responded on {task.task_code}.', task,
                NotificationType.TASK_UPDATED)
    _notify_project_manager(db, task, "Clarification response received", f'{current_user.full_name} responded on {task.task_code}.')
    record_audit(db, actor_id=current_user.id, action="clarification_responded", entity_type="task_review",
                 entity_id=review.id, project_id=task.project_id,
                 details={"task_id": task.id, "submission_number": review.submission_number})
    db.commit()
    db.refresh(review)
    return review


@router.get("/{task_id}/dependencies", response_model=List[TaskDependencyOut])
def get_task_dependencies(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    return db.query(TaskDependency).filter(TaskDependency.task_id == task_id).all()


@router.post("/{task_id}/dependencies", response_model=TaskDependencyOut)
def create_task_dependency(
    task_id: uuid.UUID,
    dep_data: TaskDependencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_project_manager(db, current_user, task.project_id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can manage dependencies")
    predecessor = db.query(Task).filter(Task.id == dep_data.depends_on_task_id).first()
    if not predecessor:
        raise HTTPException(status_code=404, detail="Predecessor task does not exist")
    if db.query(TaskDependency).filter(TaskDependency.task_id == task_id,
            TaskDependency.depends_on_task_id == dep_data.depends_on_task_id).first():
        raise HTTPException(status_code=409, detail="Dependency already exists")
    _validate_dependency_ids(db, task, [dep_data.depends_on_task_id])

    new_dep = TaskDependency(
        task_id=task_id,
        depends_on_task_id=dep_data.depends_on_task_id,
        dependency_type=dep_data.dependency_type,
        lag_days=dep_data.lag_days,
    )
    db.add(new_dep)
    _invalidate_critical_path(db, task.project_id)
    record_audit(db, actor_id=current_user.id, action="dependency_added", entity_type="task",
                 entity_id=task.id, project_id=task.project_id,
                 details={"task_code": task.task_code, "predecessor_id": predecessor.id,
                          "predecessor_code": predecessor.task_code})
    db.commit()
    db.refresh(new_dep)
    return new_dep

@router.delete("/{task_id}/dependencies/{dependency_id}")
def delete_task_dependency(
    task_id: uuid.UUID,
    dependency_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    if not _is_project_manager(db, current_user, task.project_id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can manage dependencies")
    dependency = db.query(TaskDependency).filter(
        TaskDependency.id == dependency_id, TaskDependency.task_id == task.id
    ).first()
    if not dependency:
        raise HTTPException(status_code=404, detail="Task dependency not found")
    db.delete(dependency)
    _invalidate_critical_path(db, task.project_id)
    record_audit(db, actor_id=current_user.id, action="dependency_removed", entity_type="task",
                 entity_id=task.id, project_id=task.project_id,
                 details={"dependency_id": dependency_id})
    db.commit()
    return {"message": "Dependency removed"}


@router.post("/reorder")
def reorder_tasks(
    data: TaskReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks = db.query(Task).filter(Task.id.in_(data.task_ids)).all()
    if len(tasks) != len(data.task_ids):
        raise HTTPException(status_code=400, detail="One or more tasks do not exist")
    project_ids = {task.project_id for task in tasks}
    if len(project_ids) != 1 or not _is_project_manager(db, current_user, next(iter(project_ids))):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can reorder project tasks")
    by_id = {task.id: task for task in tasks}
    for index, task_id in enumerate(data.task_ids):
        by_id[task_id].sort_order = index
    db.commit()
    return {"message": "Tasks reordered successfully"}


@router.get("/{task_id}/comments", response_model=List[TaskCommentOut])
def get_task_comments(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_task_or_403(task_id, db, current_user)
    return db.query(TaskComment).filter(TaskComment.task_id == task_id).order_by(TaskComment.created_at).all()


@router.post("/{task_id}/comments")
def add_task_comment(
    task_id: uuid.UUID,
    data: TaskCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    comment = TaskComment(task_id=task.id, author_id=current_user.id, content=data.content.strip())
    db.add(comment)
    db.flush()
    _notify_assignees(
        db, task, "New task comment", data.content[:200], NotificationType.TASK_UPDATED,
        exclude_ids={current_user.id},
    )
    record_audit(db, actor_id=current_user.id, action="comment_added", entity_type="task",
                 entity_id=task.id, project_id=task.project_id,
                 details={"comment_id": comment.id})
    db.commit()
    db.refresh(comment)
    return comment

@router.get("/{task_id}/reviews", response_model=List[TaskReviewOut])
def get_task_reviews(task_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if is_worker(current_user):
        raise HTTPException(status_code=403, detail="Workers cannot access Consultant review history")
    _get_task_or_403(task_id, db, current_user)
    return db.query(TaskReview).filter(TaskReview.task_id == task_id).order_by(TaskReview.created_at.desc()).all()


@router.get("/{task_id}/activity")
def get_task_activity(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _get_task_or_403(task_id, db, current_user)
    related_issue_ids = db.query(Issue.id).filter(Issue.task_id == task.id)
    logs = db.query(AuditLog).filter(
        AuditLog.project_id == task.project_id,
        or_(
            and_(AuditLog.entity_type == "task", AuditLog.entity_id == task.id),
            and_(AuditLog.entity_type == "issue", AuditLog.entity_id.in_(related_issue_ids)),
        ),
    ).order_by(AuditLog.created_at.desc()).limit(100).all()
    return [{
        "id": str(log.id),
        "action": log.action,
        "actorId": str(log.actor_id) if log.actor_id else None,
        "actorName": log.actor.full_name if log.actor else "System",
        "timestamp": log.created_at,
        "details": json.loads(log.details) if log.details else None,
    } for log in logs]
