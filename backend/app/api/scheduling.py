import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date, timedelta
from app.models.enums import TaskStatus

from app.db.database import get_db
from app.core.deps import get_current_user, user_has_project_access
from app.models.enums import UserRole
from app.models.project import Project
from app.models.user import User
from app.models.task import Task, TaskDependency, TaskRescheduleLog
from app.models.milestone import Milestone
from app.models.enums import RescheduleReason
from app.schemas.scheduling import GanttDataResponse, ShiftTaskRequest
from app.services.audit_service import record_audit
from app.services.cpm_service import calculate_dependency_cpm
from app.core.schedule_dates import inclusive_duration_days

router = APIRouter(tags=["scheduling"])


def _deny_engineer_portfolio_schedule(current_user: User) -> None:
    if current_user.role == UserRole.ENGINEER:
        raise HTTPException(
            status_code=403,
            detail="Engineers can view scheduling information on their assigned tasks only",
        )

@router.get("/{project_id}/gantt", response_model=GanttDataResponse)
def get_gantt_data(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    _deny_engineer_portfolio_schedule(current_user)
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    tasks = db.execute(select(Task).where(Task.project_id == project_id)).scalars().all()
    
    task_ids = [t.id for t in tasks]
    dependencies = db.execute(
        select(TaskDependency).where(TaskDependency.task_id.in_(task_ids))
    ).scalars().all()

    dep_map = {t_id: [] for t_id in task_ids}
    for dep in dependencies:
        # For gantt-task-react, 'dependencies' means what this task depends ON
        dep_map[dep.task_id].append(str(dep.depends_on_task_id))

    try:
        cpm = calculate_dependency_cpm(tasks, dependencies)
    except ValueError:
        raise HTTPException(status_code=400, detail="Task dependency graph contains a cycle")
    critical_ids = set(cpm["critical_task_ids"])
    float_by_id = {item["task_id"]: item["total_float_days"] for item in cpm["details"]}

    gantt_tasks = []
    for t in tasks:
        gantt_tasks.append({
            "id": t.id,
            "task_code": t.task_code,
            "name": t.name,
            "start": t.planned_start_date,
            "end": t.planned_end_date,
            "progress": float(t.progress_percentage),
            "dependencies": dep_map.get(t.id, []),
            "type": "milestone" if t.is_milestone else "task",
            # Never trust a stale/manual flag for the Schedule view.  The Gantt
            # is coloured from the current dependency network on every read.
            "is_critical": t.id in critical_ids,
            "status": t.status.name
            ,"priority": t.priority.value
            ,"duration_days": inclusive_duration_days(t.planned_start_date, t.planned_end_date)
                if t.planned_start_date and t.planned_end_date else None
            ,"total_float_days": float_by_id.get(t.id)
            ,"is_disabled": False
        })

    milestones = db.query(Milestone).filter(Milestone.project_id == project_id).order_by(
        Milestone.planned_date, Milestone.milestone_code
    ).all()
    for milestone in milestones:
        completed = sum(1 for task in milestone.tasks if task.status == TaskStatus.DONE)
        progress = round(sum(float(task.progress_percentage or 0) for task in milestone.tasks) / len(milestone.tasks), 2) if milestone.tasks else 0.0
        if milestone.actual_date or (milestone.tasks and completed == len(milestone.tasks)):
            progress = 100.0
            status = "done"
        elif milestone.planned_date < date.today():
            status = "delayed"
        else:
            status = "pending"
        gantt_tasks.append({
            "id": milestone.id,
            "task_code": milestone.milestone_code,
            "name": milestone.name,
            "start": milestone.planned_date,
            "end": milestone.planned_date,
            "progress": progress,
            "dependencies": [str(task.id) for task in milestone.tasks],
            "type": "milestone",
            "is_critical": False,
            "status": status,
            "priority": "medium",
            "duration_days": 1,
            "total_float_days": None,
            "is_disabled": True,
        })

    return {"tasks": gantt_tasks}

@router.get("/{project_id}/critical-path")
def calculate_critical_path(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """Calculate a dependency-driven CPM path and persist its task highlights."""
    _deny_engineer_portfolio_schedule(current_user)
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    tasks = db.execute(select(Task).where(Task.project_id == project_id)).scalars().all()
    if not tasks:
        return {"projectDurationDays": 0, "criticalTaskCount": 0, "criticalTaskIds": [],
                "criticalTasks": [], "tasks": [], "dependencyCount": 0,
                "calculationMethod": "CPM_DEPENDENCY_NETWORK",
                "reason": "No tasks exist in this project."}
    by_id = {task.id: task for task in tasks}
    dependencies = db.query(TaskDependency).filter(TaskDependency.task_id.in_(by_id)).all()
    try:
        result = calculate_dependency_cpm(tasks, dependencies)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Task dependency graph contains a cycle")
    detail_by_id = {item["task_id"]: item for item in result["details"]}
    critical_ids = result["critical_task_ids"]
    for task in tasks:
        detail = detail_by_id.get(task.id)
        task.total_float_days = detail["total_float_days"] if detail else None
        task.is_critical_path = task.id in set(critical_ids)

    details = [{
        "taskId": str(item["task_id"]), "taskCode": by_id[item["task_id"]].task_code, "name": item["name"],
        "durationDays": item["duration_days"],
        "earliestStart": item["earliest_start"], "earliestFinish": item["earliest_finish"],
        "latestStart": item["latest_start"], "latestFinish": item["latest_finish"],
        "totalFloatDays": item["total_float_days"], "isCritical": item["is_critical"],
        "predecessorIds": [str(value) for value in item["predecessor_ids"]],
        "drivingPredecessorId": str(item["driving_predecessor_id"]) if item["driving_predecessor_id"] else None,
        "drivingDependencyType": item["driving_dependency_type"],
        "drivingLagDays": item["driving_lag_days"],
    } for item in result["details"]]
    critical = [next(item for item in details if item["taskId"] == str(task_id)) for task_id in critical_ids]
    record_audit(db, actor_id=current_user.id, action="critical_path_calculated", entity_type="project",
                 entity_id=project_id, project_id=project_id,
                 details={"duration_days": result["project_duration_days"],
                          "critical_task_count": len(critical), "dependency_count": result["dependency_count"],
                          "ordered_task_ids": [str(task_id) for task_id in critical_ids]})
    db.commit()
    return {"projectDurationDays": result["project_duration_days"], "criticalTaskCount": len(critical),
            "criticalTaskIds": [str(task_id) for task_id in critical_ids], "criticalTasks": critical,
            "tasks": details, "dependencyCount": result["dependency_count"],
            "calculationMethod": "CPM_DEPENDENCY_NETWORK", "reason": result["reason"]}

@router.get("/{project_id}/delay-analysis")
def get_delay_analysis(project_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _deny_engineer_portfolio_schedule(current_user)
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    overdue = db.query(Task).filter(Task.project_id == project_id, Task.planned_end_date < date.today(),
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).all()
    dependencies = db.query(TaskDependency).join(Task, Task.id == TaskDependency.task_id).filter(Task.project_id == project_id).all()
    downstream = {}
    for dep in dependencies:
        downstream.setdefault(dep.depends_on_task_id, set()).add(dep.task_id)
    impacted = set()
    queue = [task.id for task in overdue]
    while queue:
        source = queue.pop(0)
        for target in downstream.get(source, set()):
            if target not in impacted:
                impacted.add(target); queue.append(target)
    details = [{"taskId": str(task.id), "name": task.name,
                "delayDays": (date.today() - task.planned_end_date).days,
                "critical": task.is_critical_path,
                "assignees": [{"id": str(user.id), "fullName": user.full_name, "role": user.role.value}
                              for user in task.assignees]}
               for task in overdue]
    return {"overdueTasks": details, "overdueCount": len(overdue), "impactedTaskIds": [str(x) for x in impacted],
            "impactedCount": len(impacted), "estimatedProjectDelayDays": max((item["delayDays"] for item in details), default=0)}


@router.post("/{project_id}/shift")
def shift_task_schedule(
    project_id: uuid.UUID,
    payload: ShiftTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Shifts a task by X days, and cascades the delay to all downstream dependent tasks.
    """
    root_task = db.get(Task, payload.task_id)
    if not root_task or root_task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    project = db.get(Project, project_id)
    if current_user.role != UserRole.ADMIN and (not project or project.project_manager_id != current_user.id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can shift schedules")

    if payload.shift_days == 0:
        return {"message": "No shift applied"}

    # Cascade using BFS
    queue = [root_task]
    visited = set([root_task.id])

    shifted_count = 0

    while queue:
        current = queue.pop(0)
        
        # Shift current task
        old_start = current.planned_start_date
        old_end = current.planned_end_date
        
        if current.planned_start_date:
            current.planned_start_date += timedelta(days=payload.shift_days)
        if current.planned_end_date:
            current.planned_end_date += timedelta(days=payload.shift_days)

        # Log the shift
        log = TaskRescheduleLog(
            task_id=current.id,
            triggered_by_task_id=root_task.id if current.id != root_task.id else None,
            triggered_by_user_id=current_user.id,
            reason=RescheduleReason.MANUAL if current.id == root_task.id else RescheduleReason.DEPENDENCY_DELAY,
            notes=payload.notes if current.id == root_task.id else f"Cascaded from {root_task.name}",
            previous_start_date=old_start,
            previous_end_date=old_end,
            new_start_date=current.planned_start_date,
            new_end_date=current.planned_end_date,
            shift_days=payload.shift_days,
            is_automatic=(current.id != root_task.id)
        )
        db.add(log)
        shifted_count += 1

        # Find tasks that depend on this task (downstream)
        dependents = db.execute(
            select(TaskDependency).where(TaskDependency.depends_on_task_id == current.id)
        ).scalars().all()

        for dep in dependents:
            if dep.task_id not in visited:
                visited.add(dep.task_id)
                downstream_task = db.get(Task, dep.task_id)
                if downstream_task:
                    queue.append(downstream_task)

    record_audit(db, actor_id=current_user.id, action="schedule_recalculated", entity_type="project",
                 entity_id=project_id, project_id=project_id,
                 details={"root_task_id": root_task.id, "shift_days": payload.shift_days, "shifted_count": shifted_count})
    db.query(Task).filter(Task.project_id == project_id).update(
        {Task.is_critical_path: False, Task.total_float_days: None}, synchronize_session=False
    )
    db.commit()
    return {"message": f"Shifted {shifted_count} tasks successfully"}
