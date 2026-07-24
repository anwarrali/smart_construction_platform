import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user, get_manageable_project_or_403, user_has_project_access
from app.db.database import get_db
from app.models.enums import NotificationType, TaskStatus
from app.models.milestone import Milestone
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.milestone import MilestoneCreate, MilestoneOut, MilestoneUpdate
from app.services.audit_service import record_audit


router = APIRouter(prefix="/milestones", tags=["Milestones"])


def _get_milestone_or_404(db: Session, milestone_id: uuid.UUID) -> Milestone:
    milestone = db.query(Milestone).options(selectinload(Milestone.tasks)).filter(Milestone.id == milestone_id).first()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone


def _validate_tasks(db: Session, project_id: uuid.UUID, task_ids: list[uuid.UUID]) -> list[Task]:
    tasks = db.query(Task).filter(Task.id.in_(task_ids)).all() if task_ids else []
    if len(tasks) != len(task_ids):
        raise HTTPException(status_code=404, detail="One or more milestone tasks do not exist")
    if any(task.project_id != project_id for task in tasks):
        raise HTTPException(status_code=400, detail="Milestone tasks must belong to the same project")
    return tasks


def _next_code(db: Session, project_id: uuid.UUID) -> str:
    project = db.query(Project).filter(Project.id == project_id).with_for_update().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.milestone_code_counter = int(project.milestone_code_counter or 0) + 1
    db.flush()
    return f"MLS-{project.milestone_code_counter:03d}"


def _out(milestone: Milestone) -> dict:
    tasks = milestone.tasks
    completed = sum(1 for task in tasks if task.status == TaskStatus.DONE)
    progress = round(sum(float(task.progress_percentage or 0) for task in tasks) / len(tasks), 2) if tasks else 0.0
    if milestone.actual_date or (tasks and completed == len(tasks)):
        status = "completed"
        progress = 100.0
    elif milestone.planned_date < date.today():
        status = "delayed"
    else:
        status = "pending"
    return {
        "id": milestone.id,
        "project_id": milestone.project_id,
        "milestone_code": milestone.milestone_code,
        "name": milestone.name,
        "description": milestone.description,
        "planned_date": milestone.planned_date,
        "actual_date": milestone.actual_date,
        "status": status,
        "progress_percentage": progress,
        "task_count": len(tasks),
        "completed_task_count": completed,
        "task_ids": [task.id for task in tasks],
        "created_by_id": milestone.created_by_id,
        "created_at": milestone.created_at,
        "updated_at": milestone.updated_at,
    }


@router.get("", response_model=List[MilestoneOut])
def list_milestones(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    milestones = db.query(Milestone).options(selectinload(Milestone.tasks)).filter(
        Milestone.project_id == project_id
    ).order_by(Milestone.planned_date, Milestone.milestone_code).all()
    return [_out(milestone) for milestone in milestones]


@router.get("/{milestone_id}", response_model=MilestoneOut)
def get_milestone(
    milestone_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = _get_milestone_or_404(db, milestone_id)
    if not user_has_project_access(db, current_user, milestone.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this milestone")
    return _out(milestone)


@router.post("", response_model=MilestoneOut)
def create_milestone(
    data: MilestoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_manageable_project_or_403(data.project_id, db, current_user)
    tasks = _validate_tasks(db, data.project_id, data.task_ids)
    milestone = Milestone(
        project_id=data.project_id,
        milestone_code=_next_code(db, data.project_id),
        name=data.name.strip(),
        description=data.description.strip() if data.description else None,
        planned_date=data.planned_date,
        created_by_id=current_user.id,
        tasks=tasks,
    )
    db.add(milestone)
    db.flush()
    recipients = {assignee.id for task in tasks for assignee in task.assignees if assignee.id != current_user.id}
    for user_id in recipients:
        db.add(Notification(
            user_id=user_id, project_id=data.project_id, title="Project milestone assigned",
            message=f'{milestone.milestone_code} — "{milestone.name}" includes assigned work.',
            type=NotificationType.SYSTEM, related_entity_type="MILESTONE", related_entity_id=milestone.id,
        ))
    record_audit(db, actor_id=current_user.id, action="created", entity_type="milestone",
                 entity_id=milestone.id, project_id=data.project_id,
                 details={"milestone_code": milestone.milestone_code, "task_ids": [str(value) for value in data.task_ids]})
    db.commit()
    db.refresh(milestone)
    return _out(milestone)


@router.put("/{milestone_id}", response_model=MilestoneOut)
def update_milestone(
    milestone_id: uuid.UUID,
    data: MilestoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = _get_milestone_or_404(db, milestone_id)
    get_manageable_project_or_403(milestone.project_id, db, current_user)
    if data.name is not None:
        milestone.name = data.name.strip()
    if "description" in data.model_fields_set:
        milestone.description = data.description.strip() if data.description else None
    if data.planned_date is not None:
        milestone.planned_date = data.planned_date
    if "actual_date" in data.model_fields_set:
        milestone.actual_date = data.actual_date
    if data.task_ids is not None:
        milestone.tasks = _validate_tasks(db, milestone.project_id, data.task_ids)
    record_audit(db, actor_id=current_user.id, action="updated", entity_type="milestone",
                 entity_id=milestone.id, project_id=milestone.project_id,
                 details={"fields": sorted(data.model_fields_set)})
    db.commit()
    db.refresh(milestone)
    return _out(milestone)


@router.delete("/{milestone_id}")
def delete_milestone(
    milestone_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    milestone = _get_milestone_or_404(db, milestone_id)
    get_manageable_project_or_403(milestone.project_id, db, current_user)
    project_id = milestone.project_id
    db.query(Task).filter(Task.milestone_id == milestone.id).update({Task.milestone_id: None}, synchronize_session=False)
    record_audit(db, actor_id=current_user.id, action="deleted", entity_type="milestone",
                 entity_id=milestone.id, project_id=project_id)
    db.delete(milestone)
    db.commit()
    return {"message": "Milestone deleted; linked tasks were preserved"}
