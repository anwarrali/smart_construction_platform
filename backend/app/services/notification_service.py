from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.models.enums import NotificationType, TaskStatus
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task

def create_once(db: Session, *, user_id, title: str, message: str, notification_type: NotificationType,
                project_id=None, task_id=None) -> bool:
    query = db.query(Notification).filter(Notification.user_id == user_id, Notification.type == notification_type)
    if task_id:
        query = query.filter(Notification.task_id == task_id, Notification.title == title)
    elif project_id:
        query = query.filter(Notification.project_id == project_id, Notification.title == title)
    if query.first():
        return False
    db.add(Notification(user_id=user_id, title=title, message=message, type=notification_type,
                        project_id=project_id, task_id=task_id))
    return True

def sync_overdue_task_notifications(db: Session, project_ids: list) -> int:
    if not project_ids:
        return 0
    tasks = db.query(Task).filter(
        Task.project_id.in_(project_ids), Task.planned_end_date < date.today(),
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).all()
    created = 0
    for task in tasks:
        project = db.get(Project, task.project_id)
        recipients = set(task.assignee_ids) | ({project.project_manager_id} if project and project.project_manager_id else set())
        delay_days = (date.today() - task.planned_end_date).days
        for user_id in recipients:
            created += int(create_once(db, user_id=user_id, title="Task overdue",
                message=f"{task.name} is overdue by {delay_days} day(s).", notification_type=NotificationType.TASK_OVERDUE,
                project_id=task.project_id, task_id=task.id))
    if created:
        db.commit()
    return created


def sync_upcoming_task_notifications(db: Session, project_ids: list) -> int:
    if not project_ids:
        return 0
    today = date.today()
    due_limit = today + timedelta(days=3)
    tasks = db.query(Task).filter(
        Task.project_id.in_(project_ids),
        Task.planned_end_date >= today,
        Task.planned_end_date <= due_limit,
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).all()
    created = 0
    for task in tasks:
        days = (task.planned_end_date - today).days
        for user_id in task.assignee_ids:
            created += int(create_once(
                db,
                user_id=user_id,
                title="Task due soon",
                message=f"{task.name} is due {'today' if days == 0 else f'in {days} day(s)' }.",
                notification_type=NotificationType.TASK_UPDATED,
                project_id=task.project_id,
                task_id=task.id,
            ))
    if created:
        db.commit()
    return created
