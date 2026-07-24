from sqlalchemy.orm import Session

from app.core.deps import (
    is_main_contractor_engineer,
    is_worker,
    user_has_project_access,
)
from app.models.task import Task
from app.models.user import User
from app.services.field_submission_authorization import can_worker_submit_evidence


def can_create_voice_analysis(
    db: Session, user: User, project_id, task: Task | None
) -> bool:
    if not user_has_project_access(db, user, project_id):
        return False
    if task and task.project_id != project_id:
        return False
    if is_worker(user):
        if task:
            return can_worker_submit_evidence(db, user, task)
        return db.query(Task.id).filter(
            Task.project_id == project_id,
            Task.assignees.any(User.id == user.id),
        ).first() is not None
    if is_main_contractor_engineer(user):
        return task is None or any(assignee.id == user.id for assignee in task.assignees)
    return False


def authorized_voice_tasks(db: Session, user: User, project_id) -> list[Task]:
    if not user_has_project_access(db, user, project_id):
        return []
    query = db.query(Task).filter(Task.project_id == project_id)
    if is_worker(user) or is_main_contractor_engineer(user):
        query = query.filter(Task.assignees.any(User.id == user.id))
    else:
        return []
    return query.order_by(Task.task_code).all()


def can_view_voice_analysis(db: Session, user: User, analysis) -> bool:
    if analysis.user_id == user.id:
        return True
    return False
