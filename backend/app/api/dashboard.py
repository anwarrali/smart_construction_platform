from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import date
import uuid

from app.db.database import get_db
from app.models.user import User
from app.models.project import Project, ProjectMember
from app.models.issue import Issue
from app.models.task import Task
from app.models.milestone import Milestone
from app.models.design_change import DesignChange
from app.models.site_report import SiteReport
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.task import TaskReview
from app.core.deps import get_current_user, user_has_project_access
from app.core.deps import is_main_contractor_engineer
from app.models.enums import ProjectStatus, IssueStatus, IssueSeverity, TaskStatus, UserStatus, UserRole, DesignChangeStatus
from app.services.notification_service import sync_overdue_task_notifications, sync_upcoming_task_notifications
from app.core.schedule_dates import inclusive_duration_days
import json

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _engineer_task_summary(task: Task, project: Project, today: date, latest_review=None) -> dict:
    remaining = (task.planned_end_date - today).days if task.planned_end_date else None
    return {
        "id": str(task.id),
        "taskCode": task.task_code,
        "name": task.name,
        "description": task.description,
        "projectId": str(task.project_id),
        "projectName": project.name,
        "discipline": task.discipline,
        "status": task.status.value,
        "priority": task.priority.value,
        "progressPercentage": float(task.progress_percentage or 0),
        "plannedStartDate": task.planned_start_date,
        "plannedEndDate": task.planned_end_date,
        "daysRemaining": remaining if remaining is not None and remaining >= 0 else None,
        "daysOverdue": abs(remaining) if remaining is not None and remaining < 0 and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED} else 0,
        "isCriticalPath": task.is_critical_path,
        "dependencyIds": [str(edge.depends_on_task_id) for edge in task.dependencies],
        "reviewStatus": task.review_status,
        "reviewComment": latest_review.comments if latest_review else task.consultant_comments,
        "rejectionReason": latest_review.rejection_reason if latest_review else task.rejection_reason,
        "reviewedAt": latest_review.updated_at if latest_review and latest_review.reviewed_by_id else task.reviewed_at,
        "reviewerName": latest_review.reviewed_by.full_name if latest_review and latest_review.reviewed_by else None,
    }


@router.get("/engineer/projects/{project_id}")
def get_engineer_project_dashboard(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from fastapi import HTTPException

    if not is_main_contractor_engineer(current_user):
        raise HTTPException(status_code=403, detail="Active Main Contractor Engineer access required")
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
        ProjectMember.is_active == True,
        ProjectMember.role_on_project == UserRole.ENGINEER,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sync_overdue_task_notifications(db, [project_id])
    sync_upcoming_task_notifications(db, [project_id])

    today = date.today()
    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignees.any(User.id == current_user.id),
    ).order_by(Task.planned_end_date.asc().nullslast(), Task.task_code).all()
    task_ids = [task.id for task in tasks]
    latest_reviews = {}
    if task_ids:
        for review in db.query(TaskReview).filter(TaskReview.task_id.in_(task_ids)).order_by(
            TaskReview.task_id, TaskReview.created_at.desc()
        ).all():
            latest_reviews.setdefault(review.task_id, review)

    summaries = [
        _engineer_task_summary(task, project, today, latest_reviews.get(task.id))
        for task in tasks
    ]
    active_statuses = {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.REWORK_REQUIRED}
    today_tasks = [summary for task, summary in zip(tasks, summaries) if (
        task.status in active_statuses
        and task.planned_start_date is not None
        and task.planned_end_date is not None
        and task.planned_start_date <= today <= task.planned_end_date
    )]
    overdue = [summary for task, summary in zip(tasks, summaries) if (
        task.planned_end_date is not None
        and task.planned_end_date < today
        and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
    )]
    upcoming = [summary for task, summary in zip(tasks, summaries) if (
        task.planned_end_date is not None
        and today <= task.planned_end_date <= date.fromordinal(today.toordinal() + 7)
        and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
    )]
    pending_review = [summary for task, summary in zip(tasks, summaries) if task.status == TaskStatus.UNDER_REVIEW]
    rework = [summary for task, summary in zip(tasks, summaries) if task.status == TaskStatus.REWORK_REQUIRED]

    issue_query = db.query(Issue).filter(
        Issue.project_id == project_id,
        Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
    )
    if task_ids:
        issue_query = issue_query.filter(or_(
            Issue.task_id.in_(task_ids),
            Issue.raised_by_id == current_user.id,
            Issue.assigned_to_id == current_user.id,
        ))
    else:
        issue_query = issue_query.filter(or_(
            Issue.raised_by_id == current_user.id,
            Issue.assigned_to_id == current_user.id,
        ))
    open_issues = issue_query.count()

    activity_query = db.query(AuditLog).filter(AuditLog.project_id == project_id)
    if task_ids:
        activity_query = activity_query.filter(or_(
            AuditLog.actor_id == current_user.id,
            (AuditLog.entity_type == "task") & AuditLog.entity_id.in_(task_ids),
        ))
    else:
        activity_query = activity_query.filter(AuditLog.actor_id == current_user.id)
    activities = activity_query.order_by(AuditLog.created_at.desc()).limit(12).all()
    notifications = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.project_id == project_id,
    ).order_by(Notification.created_at.desc()).limit(8).all()

    return {
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status.value,
            "specialization": current_user.engineer_profile.discipline.value if current_user.engineer_profile else None,
            "organizationSide": "main_contractor",
            "assignmentTitle": membership.assignment_title,
            "isSiteEngineer": membership.is_site_engineer,
        },
        "stats": {
            "totalTasks": len(tasks),
            "tasksToday": len(today_tasks),
            "inProgress": sum(task.status == TaskStatus.IN_PROGRESS for task in tasks),
            "overdue": len(overdue),
            "underReview": len(pending_review),
            "reworkRequired": len(rework),
            "completed": sum(task.status == TaskStatus.DONE for task in tasks),
            "blocked": sum(task.status == TaskStatus.BLOCKED for task in tasks),
            "openIssues": open_issues,
        },
        "tasksToday": today_tasks,
        "upcomingDeadlines": upcoming,
        "overdueTasks": overdue,
        "pendingReview": pending_review,
        "reworkRequired": rework,
        "recentActivity": [{
            "id": str(log.id),
            "action": log.action,
            "entityType": log.entity_type,
            "entityId": str(log.entity_id) if log.entity_id else None,
            "actorName": log.actor.full_name if log.actor else "System",
            "timestamp": log.created_at,
            "details": json.loads(log.details) if log.details else None,
        } for log in activities],
        "notifications": [{
            "id": str(item.id),
            "title": item.title,
            "message": item.message,
            "type": item.type.value,
            "isRead": item.is_read,
            "taskId": str(item.task_id) if item.task_id else None,
            "createdAt": item.created_at,
        } for item in notifications],
    }

@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == UserRole.ENGINEER:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Engineer dashboard requires an active project context")
    projects_query = db.query(Project)
    if current_user.role == UserRole.PROJECT_MANAGER:
        projects_query = projects_query.filter(Project.project_manager_id == current_user.id)
    elif current_user.role != UserRole.ADMIN:
        member_ids = db.query(ProjectMember.project_id).filter(
            ProjectMember.user_id == current_user.id, ProjectMember.is_active == True
        )
        projects_query = projects_query.filter(or_(
            Project.id.in_(member_ids), Project.owner_id == current_user.id,
            Project.project_manager_id == current_user.id,
        ))
    project_ids = [row.id for row in projects_query.all()]
    scheduled_ranges = db.query(Task.planned_start_date, Task.planned_end_date).filter(
        Task.project_id.in_(project_ids),
        Task.planned_start_date.isnot(None),
        Task.planned_end_date.isnot(None),
    ).all() if project_ids else []
    scheduled_task_days = sum(
        inclusive_duration_days(start_date, end_date)
        for start_date, end_date in scheduled_ranges
    )
    sync_overdue_task_notifications(db, project_ids)
    active_projects_count = projects_query.filter(Project.status == ProjectStatus.ACTIVE).count()
    active_projects_sub = f"{active_projects_count} on schedule" if active_projects_count > 0 else "0 on schedule"
    
    # 2. Open Issues
    open_issues_count = db.query(Issue).filter(Issue.project_id.in_(project_ids), Issue.status == IssueStatus.OPEN).count()
    critical_issues_count = db.query(Issue).filter(
        Issue.project_id.in_(project_ids), Issue.status == IssueStatus.OPEN,
        Issue.severity == IssueSeverity.CRITICAL
    ).count()
    open_issues_sub = f"{critical_issues_count} critical"
    
    # 3. Tasks Due Today
    today = date.today()
    tasks_due_today_count = db.query(Task).filter(
        Task.project_id.in_(project_ids), Task.planned_end_date == today,
        Task.status != TaskStatus.DONE
    ).count()
    overdue_tasks_count = db.query(Task).filter(
        Task.project_id.in_(project_ids), Task.planned_end_date < today,
        Task.status != TaskStatus.DONE
    ).count()
    critical_tasks_count = db.query(Task).filter(Task.project_id.in_(project_ids),
        Task.is_critical_path == True, Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).count()
    unresolved_changes_count = db.query(DesignChange).filter(DesignChange.project_id.in_(project_ids),
        DesignChange.status.in_([DesignChangeStatus.PROPOSED, DesignChangeStatus.UNDER_REVIEW])).count()
    tasks_due_today_sub = f"{overdue_tasks_count} overdue"
    
    # 4. Team Members
    # Count unique user IDs in ProjectMember
    team_members_count = db.query(ProjectMember.user_id).filter(
        ProjectMember.project_id.in_(project_ids), ProjectMember.is_active == True
    ).distinct().count()
    team_members_sub = f"Active today: {team_members_count}"
    
    # 5. Task Completion (for each project)
    projects = projects_query.all()
    task_completion = []
    for project in projects:
        total_tasks = db.query(Task).filter(Task.project_id == project.id).count()
        done_tasks = db.query(Task).filter(Task.project_id == project.id, Task.status == TaskStatus.DONE).count()
        task_completion.append({
            "name": project.name,
            "done": done_tasks,
            "total": total_tasks if total_tasks > 0 else 0
        })
        
    recent_logs = db.query(AuditLog).filter(AuditLog.project_id.in_(project_ids)).order_by(
        AuditLog.created_at.desc()).limit(10).all() if project_ids else []
    milestone_query = db.query(Milestone).filter(Milestone.project_id.in_(project_ids))
    milestones = milestone_query.all()
    completed_milestones = sum(1 for milestone in milestones if milestone.actual_date or (
        milestone.tasks and all(task.status == TaskStatus.DONE for task in milestone.tasks)
    ))
    return {
        "totalAssignedProjects": len(projects),
        "activeProjects": active_projects_count,
        "activeProjectsSub": active_projects_sub,
        "openIssues": open_issues_count,
        "openIssuesSub": open_issues_sub,
        "tasksDueToday": tasks_due_today_count,
        "tasksDueTodaySub": tasks_due_today_sub,
        "delayedTasks": overdue_tasks_count,
        "criticalTasks": critical_tasks_count,
        "scheduledTaskDays": scheduled_task_days,
        "unresolvedDesignChanges": unresolved_changes_count,
        "milestoneTotal": len(milestones),
        "milestoneCompleted": completed_milestones,
        "milestonePending": len(milestones) - completed_milestones,
        "teamMembers": team_members_count,
        "teamMembersSub": team_members_sub,
        "taskCompletion": task_completion,
        "recentActivity": [{"id": str(log.id), "projectId": str(log.project_id) if log.project_id else None,
            "action": log.action, "entityType": log.entity_type,
            "timestamp": log.created_at.isoformat()} for log in recent_logs],
    }


@router.get("/projects/{project_id}")
def get_project_dashboard(project_id: uuid.UUID, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    from fastapi import HTTPException
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if current_user.role == UserRole.ENGINEER:
        raise HTTPException(status_code=403, detail="Use the Engineer project dashboard for assigned-task metrics")
    if current_user.role == UserRole.PROJECT_MANAGER and project.project_manager_id != current_user.id:
        raise HTTPException(status_code=403, detail="This project is not assigned to the authenticated Project Manager")
    today = date.today()
    tasks = db.query(Task).filter(Task.project_id == project_id)
    scheduled_task_days = sum(
        inclusive_duration_days(task.planned_start_date, task.planned_end_date)
        for task in tasks.all()
        if task.planned_start_date and task.planned_end_date
    )
    issues = db.query(Issue).filter(Issue.project_id == project_id)
    milestones = db.query(Milestone).filter(Milestone.project_id == project_id).all()
    completed_milestones = sum(1 for milestone in milestones if milestone.actual_date or (
        milestone.tasks and all(task.status == TaskStatus.DONE for task in milestone.tasks)
    ))
    return {
        "projectId": project.id, "name": project.name, "status": project.status.value,
        "progress": float(project.completion_percentage),
        "taskTotal": tasks.count(), "taskDone": tasks.filter(Task.status == TaskStatus.DONE).count(),
        "taskInProgress": tasks.filter(Task.status == TaskStatus.IN_PROGRESS).count(),
        "taskBlocked": tasks.filter(Task.status == TaskStatus.BLOCKED).count(),
        "tasksDueToday": tasks.filter(Task.planned_end_date == today,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).count(),
        "taskProgressPercentage": round(sum(float(task.progress_percentage or 0) for task in tasks.all()) / tasks.count(), 2) if tasks.count() else 0,
        "delayedTasks": tasks.filter(Task.planned_end_date < today,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).count(),
        "criticalPathTasks": tasks.filter(Task.is_critical_path == True,
            Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED])).count(),
        "scheduledTaskDays": scheduled_task_days,
        "openIssues": issues.filter(Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS])).count(),
        "urgentIssues": issues.filter(Issue.status.in_([IssueStatus.OPEN, IssueStatus.IN_PROGRESS]),
            Issue.severity.in_([IssueSeverity.HIGH, IssueSeverity.CRITICAL])).count(),
        "unresolvedDesignChanges": db.query(DesignChange).filter(DesignChange.project_id == project_id,
            DesignChange.status.in_([DesignChangeStatus.PROPOSED, DesignChangeStatus.UNDER_REVIEW])).count(),
        "siteReports": db.query(SiteReport).filter(SiteReport.project_id == project_id).count(),
        "teamMembers": db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
            ProjectMember.is_active == True).count(),
        "milestoneTotal": len(milestones),
        "milestoneCompleted": completed_milestones,
        "milestonePending": len(milestones) - completed_milestones,
        "recentActivity": [{"action": log.action, "entityType": log.entity_type,
            "entityId": str(log.entity_id) if log.entity_id else None, "timestamp": log.created_at}
            for log in db.query(AuditLog).filter(AuditLog.project_id == project_id)
                .order_by(AuditLog.created_at.desc()).limit(8).all()],
    }
