from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.deps import is_main_contractor_engineer, user_has_project_access
from app.models.enums import NotificationType, TaskStatus, UserRole
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task, TaskComment, TaskDependency
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.domain_event_dispatcher import emit_domain_event


def update_task_progress(*, db: Session, current_user: User, task_id: UUID,
                         progress_percentage: float, note: str | None = None,
                         source: str = "manual", audit_metadata: dict | None = None,
                         commit: bool = True) -> Task:
    task = db.query(Task).filter(Task.id == task_id).with_for_update().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not user_has_project_access(db, current_user, task.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this task")
    is_pm = _is_project_manager(db, current_user, task.project_id)
    is_assignee = _is_task_engineer(task, current_user)
    validate_progress_change(
        task=task,
        progress=float(progress_percentage),
        is_project_manager=is_pm,
        is_assignee=is_assignee,
        dependencies_complete=_dependencies_complete(db, task),
    )
    previous_progress = float(task.progress_percentage or 0)
    previous_status = task.status
    task.progress_percentage = float(progress_percentage)
    if task.progress_percentage > 0 and task.status in {
        TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.REWORK_REQUIRED,
    }:
        task.status = TaskStatus.IN_PROGRESS
        task.actual_start_date = task.actual_start_date or date.today()

    _refresh_project_progress(db, task.project_id)
    clean_note = note.strip() if note else None
    if clean_note:
        db.add(TaskComment(task_id=task.id, author_id=current_user.id,
                           content=f"Work update: {clean_note}"))
    _notify_progress_change(db, task, current_user, previous_progress)
    details = {
        "previous_progress": previous_progress,
        "progress": float(progress_percentage),
        "previous_status": previous_status.value,
        "status": task.status.value,
        "note": clean_note,
        "source": source,
    }
    if audit_metadata:
        details["metadata"] = audit_metadata
    record_audit(db, actor_id=current_user.id, action="progress_updated", entity_type="task",
                 entity_id=task.id, project_id=task.project_id, details=details)
    emit_domain_event(
        db,
        project_id=task.project_id,
        event_type="TASK_PROGRESS_CHANGED",
        entity_type="TASK",
        entity_id=task.id,
        actor_user_id=current_user.id,
        payload=details,
        correlation_id=str((audit_metadata or {}).get("analysis_id") or f"task:{task.id}"),
        idempotency_key=(
            f"TASK_PROGRESS_CHANGED:{task.id}:{(audit_metadata or {}).get('analysis_id')}"
            if (audit_metadata or {}).get("analysis_id")
            else None
        ),
    )
    if commit:
        db.commit()
        db.refresh(task)
    else:
        db.flush()
    return task


def validate_progress_change(*, task: Task, progress: float, is_project_manager: bool,
                             is_assignee: bool, dependencies_complete: bool) -> None:
    if not 0 <= progress <= 100:
        raise HTTPException(status_code=400, detail="Progress must be between 0 and 100")
    if not is_project_manager and not is_assignee:
        raise HTTPException(status_code=403, detail="Only the assigned PM or task engineer can update progress")
    if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE}:
        raise HTTPException(status_code=400, detail="Progress cannot change while work is under review or completed")
    previous = float(task.progress_percentage or 0)
    if is_assignee and task.status not in {TaskStatus.IN_PROGRESS, TaskStatus.REWORK_REQUIRED}:
        raise HTTPException(status_code=400, detail="Start the task before updating progress")
    if is_assignee and progress < previous and task.status != TaskStatus.REWORK_REQUIRED and task.review_status != "rejected":
        raise HTTPException(status_code=400, detail="Progress cannot decrease unless the task was returned for rework")
    if progress > 0 and not dependencies_complete:
        raise HTTPException(status_code=400, detail="Task cannot start until all dependencies are Done")


def _is_project_manager(db: Session, user: User, project_id: UUID) -> bool:
    project = db.get(Project, project_id)
    return bool(user.role == UserRole.PROJECT_MANAGER and project and project.project_manager_id == user.id)


def _is_task_engineer(task: Task, user: User) -> bool:
    return is_main_contractor_engineer(user) and any(assignee.id == user.id for assignee in task.assignees)


def _dependencies_complete(db: Session, task: Task) -> bool:
    return db.query(TaskDependency).join(Task, Task.id == TaskDependency.depends_on_task_id).filter(
        TaskDependency.task_id == task.id, Task.status != TaskStatus.DONE,
    ).first() is None


def _refresh_project_progress(db: Session, project_id: UUID) -> None:
    db.flush()
    project = db.get(Project, project_id)
    if project:
        values = [float(value or 0) for (value,) in db.query(Task.progress_percentage).filter(
            Task.project_id == project_id).all()]
        project.completion_percentage = round(sum(values) / len(values), 2) if values else 0


def _notify_progress_change(db: Session, task: Task, actor: User, previous: float) -> None:
    project = db.get(Project, task.project_id)
    recipients = {assignee.id for assignee in task.assignees if assignee.id != actor.id}
    if project and project.project_manager_id != actor.id:
        recipients.add(project.project_manager_id)
    for user_id in recipients:
        db.add(Notification(
            user_id=user_id,
            title="Task progress updated",
            message=f"{actor.full_name} updated {task.task_code} from {previous:g}% to {float(task.progress_percentage):g}%.",
            type=NotificationType.TASK_UPDATED,
            project_id=task.project_id,
            task_id=task.id,
            related_entity_type="TASK",
            related_entity_id=task.id,
        ))
