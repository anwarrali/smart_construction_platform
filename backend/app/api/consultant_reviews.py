"""Project-scoped Consultant Engineer review workspace.

The task endpoints own state transitions.  This router provides read models for
the supervision dashboard and review workspace without duplicating task state.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.api.tasks import _can_consult_task, _normalized_discipline
from app.core.deps import get_current_user, is_consultant_engineer
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import TaskPriority, TaskStatus, UserRole
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.task import Task, TaskComment, TaskDependency, TaskReview
from app.models.user import User


router = APIRouter(prefix="/consultant", tags=["Consultant Engineer"])
ACTIVE_REVIEW_STATUSES = {"pending", "in_review", "clarification_requested"}
HISTORY_REVIEW_STATUSES = {"approved", "rejected"}


def _membership_or_403(db: Session, user: User, project_id: uuid.UUID) -> tuple[Project, ProjectMember]:
    if not is_consultant_engineer(user):
        raise HTTPException(status_code=403, detail="An active Consultant Engineer account is required")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.role_on_project == UserRole.CONSULTANT,
        ProjectMember.is_active == True,
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="You are not assigned to this project")
    return project, membership


def _discipline(user: User) -> str:
    return _normalized_discipline(
        user.engineer_profile.discipline.value if user.engineer_profile else None
    ) or "unassigned"


def _review_query(db: Session, project_id: uuid.UUID, user: User):
    return db.query(TaskReview).join(Task, Task.id == TaskReview.task_id).filter(
        Task.project_id == project_id,
        Task.review_required == True,
    )


def _blocked_dependents_count(db: Session, task: Task) -> int:
    return db.query(TaskDependency).join(Task, Task.id == TaskDependency.task_id).filter(
        TaskDependency.depends_on_task_id == task.id,
        Task.status.notin_([TaskStatus.DONE, TaskStatus.CANCELLED]),
    ).count()


def _evidence(review: TaskReview) -> list[dict]:
    try:
        value = json.loads(review.evidence_snapshot or "[]")
        return value if isinstance(value, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _person(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": str(user.id),
        "fullName": user.full_name,
        "role": user.role.value,
        "specialization": user.engineer_profile.discipline.value if user.engineer_profile else None,
        "organizationSide": user.engineer_affiliation,
    }


def _review_summary(db: Session, review: TaskReview) -> dict:
    task = review.task
    project = task.project
    previous_rejections = db.query(TaskReview).filter(
        TaskReview.task_id == task.id,
        TaskReview.submission_number < review.submission_number,
        TaskReview.status == "rejected",
    ).count()
    dependents_blocked = _blocked_dependents_count(db, task)
    return {
        "id": str(review.id),
        "taskId": str(task.id),
        "taskCode": task.task_code,
        "taskTitle": task.name,
        "description": task.description,
        "projectId": str(task.project_id),
        "projectName": project.name,
        "discipline": task.discipline,
        "priority": task.priority.value,
        "taskStatus": task.status.value,
        "reviewStatus": review.status,
        "submissionNumber": review.submission_number,
        "isResubmission": review.submission_number > 1,
        "submittedBy": _person(review.submitted_by),
        "submittedAt": (review.submitted_at or review.created_at).isoformat(),
        "reviewDueDate": task.review_due_date.isoformat() if task.review_due_date else None,
        "isOverdue": bool(task.review_due_date and task.review_due_date < date.today()
                          and review.status in ACTIVE_REVIEW_STATUSES),
        "isCritical": task.is_critical_path or task.priority == TaskPriority.CRITICAL,
        "dependentTasksBlocked": dependents_blocked,
        "blocksDependentWork": dependents_blocked > 0,
        "evidenceCount": len(_evidence(review)),
        "previousRejectionCount": previous_rejections,
        "completionNote": review.completion_note,
        "clarificationQuestion": review.clarification_question,
        "clarificationResponse": review.clarification_response,
        "reviewer": _person(review.reviewed_by),
        "reviewedAt": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "comments": review.comments,
        "rejectionReason": review.rejection_reason,
        "requiredCorrections": review.required_corrections,
    }


@router.get("/projects/{project_id}/dashboard")
def consultant_dashboard(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, _ = _membership_or_403(db, current_user, project_id)
    reviews = _review_query(db, project_id, current_user).order_by(TaskReview.created_at.desc()).all()
    active = [review for review in reviews if review.status in ACTIVE_REVIEW_STATUSES]
    week_start = datetime.combine(date.today() - timedelta(days=date.today().weekday()), time.min, timezone.utc)
    today = date.today()
    project_tasks = db.query(Task).filter(Task.project_id == project_id).all()
    discipline_reviews = [review for review in reviews if _can_consult_task(db, current_user, review.task)]
    active = [review for review in active if _can_consult_task(db, current_user, review.task)]
    recent_audit = db.query(AuditLog).filter(
        AuditLog.project_id == project_id,
        AuditLog.action.in_([
            "submitted_for_review", "resubmitted_for_review", "review_started", "approved",
            "rework_requested", "clarification_requested", "clarification_responded",
        ]),
    ).order_by(AuditLog.created_at.desc()).limit(10).all()
    open_reviews = [_review_summary(db, review) for review in active]
    open_reviews.sort(key=lambda item: (
        not item["isCritical"], item["reviewDueDate"] or "9999-12-31", item["submittedAt"]
    ))
    status_counts = {status.value: 0 for status in TaskStatus}
    for task in project_tasks:
        status_counts[task.status.value] = status_counts.get(task.status.value, 0) + 1
    milestones = [
        {
            "id": str(item.id), "name": item.name, "plannedDate": item.planned_date.isoformat(),
            "completed": item.actual_date is not None,
        }
        for item in sorted(project.milestones, key=lambda item: item.planned_date)
        if not item.actual_date and item.planned_date >= today
    ][:5]
    return {
        "project": {
            "id": str(project.id), "name": project.name, "status": project.status.value,
            "completionPercentage": float(project.completion_percentage or 0),
        },
        "specialization": _discipline(current_user),
        "stats": {
            "pendingReviews": len(active),
            "reviewsDueToday": sum(1 for review in active if review.task.review_due_date == today),
            "overdueReviews": sum(1 for review in active if review.task.review_due_date and review.task.review_due_date < today),
            "criticalReviews": sum(1 for item in open_reviews if item["isCritical"]),
            "approvalGatedTasks": sum(1 for item in open_reviews if item["blocksDependentWork"]),
            "approvedThisWeek": sum(1 for review in discipline_reviews if review.status == "approved"
                                     and review.reviewed_at and review.reviewed_at >= week_start),
            "rejectedThisWeek": sum(1 for review in discipline_reviews if review.status == "rejected"
                                     and review.reviewed_at and review.reviewed_at >= week_start),
            "reworkAwaitingResubmission": sum(
                1 for task in project_tasks
                if _can_consult_task(db, current_user, task)
                and task.review_required and task.status == TaskStatus.REWORK_REQUIRED
            ),
        },
        "pendingReviews": open_reviews[:8],
        "criticalReviews": [item for item in open_reviews if item["isCritical"]][:6],
        "reworkAwaitingResubmission": [
            {
                "taskId": str(task.id), "taskCode": task.task_code, "taskTitle": task.name,
                "rejectionReason": task.rejection_reason, "requiredCorrections": next((
                    review.required_corrections for review in sorted(
                        [value for value in discipline_reviews if value.task_id == task.id],
                        key=lambda value: value.submission_number, reverse=True,
                    ) if review.status == "rejected"
                ), None),
            }
            for task in project_tasks
            if _can_consult_task(db, current_user, task)
            and task.review_required and task.status == TaskStatus.REWORK_REQUIRED
        ][:6],
        "recentActivity": [
            {
                "id": str(item.id), "action": item.action, "entityType": item.entity_type,
                "entityId": str(item.entity_id) if item.entity_id else None,
                "actor": _person(item.actor), "timestamp": item.created_at.isoformat(),
            }
            for item in recent_audit
        ],
        "projectSummary": {
            "taskCounts": status_counts,
            "totalTasks": len(project_tasks),
            "delayedTasks": sum(1 for task in project_tasks if task.planned_end_date and task.planned_end_date < today
                                and task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}),
            "criticalTasks": sum(1 for task in project_tasks if task.is_critical_path),
            "upcomingMilestones": milestones,
        },
    }


@router.get("/projects/{project_id}/reviews")
def pending_reviews(
    project_id: uuid.UUID,
    status: str | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    critical_only: bool = False,
    overdue_only: bool = False,
    resubmissions_only: bool = False,
    blocking_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _membership_or_403(db, current_user, project_id)
    query = _review_query(db, project_id, current_user)
    if status:
        if status == "active":
            query = query.filter(TaskReview.status.in_(ACTIVE_REVIEW_STATUSES))
        else:
            query = query.filter(TaskReview.status == status)
    else:
        query = query.filter(TaskReview.status.in_(ACTIVE_REVIEW_STATUSES))
    if priority:
        query = query.filter(Task.priority == priority)
    if search:
        term = f"%{search.strip()}%"
        query = query.outerjoin(User, User.id == TaskReview.submitted_by_id).filter(or_(
            Task.name.ilike(term), Task.task_code.ilike(term), Task.description.ilike(term),
            User.full_name.ilike(term),
        ))
    if critical_only:
        query = query.filter(or_(Task.is_critical_path == True, Task.priority == TaskPriority.CRITICAL))
    if overdue_only:
        query = query.filter(Task.review_due_date < date.today())
    if resubmissions_only:
        query = query.filter(TaskReview.submission_number > 1)
    reviews = query.order_by(Task.review_due_date.asc().nullslast(), TaskReview.submitted_at.asc()).all()
    values = [_review_summary(db, review) for review in reviews if _can_consult_task(db, current_user, review.task)]
    if blocking_only:
        values = [item for item in values if item["blocksDependentWork"]]
    return values


@router.get("/projects/{project_id}/history")
def review_history(
    project_id: uuid.UUID,
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _membership_or_403(db, current_user, project_id)
    query = _review_query(db, project_id, current_user)
    query = query.filter(TaskReview.status.in_(HISTORY_REVIEW_STATUSES if not status else {status}))
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Task.name.ilike(term), Task.task_code.ilike(term), Task.description.ilike(term)))
    reviews = query.order_by(TaskReview.reviewed_at.desc().nullslast(), TaskReview.created_at.desc()).all()
    return [_review_summary(db, review) for review in reviews if _can_consult_task(db, current_user, review.task)]


@router.get("/projects/{project_id}/reviews/{review_id}")
def review_detail(
    project_id: uuid.UUID,
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project, _ = _membership_or_403(db, current_user, project_id)
    review = _review_query(db, project_id, current_user).filter(TaskReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review submission not found")
    task = review.task
    if not _can_consult_task(db, current_user, task):
        raise HTTPException(status_code=403, detail="You cannot review this discipline")
    dependencies = db.query(TaskDependency).filter(TaskDependency.task_id == task.id).all()
    dependents = db.query(TaskDependency).filter(TaskDependency.depends_on_task_id == task.id).all()
    dependency_tasks = {str(item.id): item for item in db.query(Task).filter(Task.id.in_(
        [item.depends_on_task_id for item in dependencies] + [item.task_id for item in dependents]
    )).all()}
    history = db.query(TaskReview).filter(TaskReview.task_id == task.id).order_by(
        TaskReview.submission_number.asc()
    ).all()
    comments = db.query(TaskComment).filter(TaskComment.task_id == task.id).order_by(TaskComment.created_at.asc()).all()
    documents = db.query(Document).filter(
        Document.project_id == project_id,
        or_(Document.task_id == task.id, Document.task_id.is_(None)),
    ).order_by(Document.created_at.desc()).limit(30).all()
    reports = db.query(SiteReport).filter(
        SiteReport.project_id == project_id,
        or_(SiteReport.task_id == task.id, SiteReport.task_id.is_(None)),
    ).order_by(SiteReport.report_date.desc()).limit(20).all()
    issues = db.query(Issue).filter(Issue.project_id == project_id, Issue.task_id == task.id).order_by(
        Issue.created_at.desc()
    ).all()
    live_evidence = db.query(Attachment).filter(
        Attachment.project_id == project_id,
        Attachment.entity_type == "TASK",
        Attachment.entity_id == task.id,
    ).order_by(Attachment.created_at.asc()).all()
    return {
        "review": _review_summary(db, review),
        "task": {
            "id": str(task.id), "taskCode": task.task_code, "title": task.name,
            "description": task.description, "projectId": str(project.id), "projectName": project.name,
            "discipline": task.discipline, "priority": task.priority.value, "status": task.status.value,
            "progressPercentage": float(task.progress_percentage or 0),
            "plannedStartDate": task.planned_start_date.isoformat() if task.planned_start_date else None,
            "plannedEndDate": task.planned_end_date.isoformat() if task.planned_end_date else None,
            "actualStartDate": task.actual_start_date.isoformat() if task.actual_start_date else None,
            "isCritical": task.is_critical_path, "milestone": ({
                "id": str(task.milestone.id), "name": task.milestone.name,
            } if task.milestone else None),
            "assignees": [_person(user) for user in task.assignees],
            "createdBy": _person(task.created_by), "projectManager": _person(project.project_manager),
        },
        "submissionEvidence": _evidence(review),
        "currentTaskEvidence": [
            {
                "id": str(item.id), "filename": item.original_filename, "fileUrl": item.file_url,
                "mimeType": item.mime_type, "fileSizeBytes": item.file_size_bytes,
                "uploadedBy": _person(item.uploaded_by), "uploadedAt": item.created_at.isoformat(),
            }
            for item in live_evidence
        ],
        "dependencies": [
            {
                "id": str(item.id), "taskId": str(item.depends_on_task_id),
                "taskCode": dependency_tasks[str(item.depends_on_task_id)].task_code,
                "title": dependency_tasks[str(item.depends_on_task_id)].name,
                "status": dependency_tasks[str(item.depends_on_task_id)].status.value,
            }
            for item in dependencies if str(item.depends_on_task_id) in dependency_tasks
        ],
        "dependents": [
            {
                "id": str(item.id), "taskId": str(item.task_id),
                "taskCode": dependency_tasks[str(item.task_id)].task_code,
                "title": dependency_tasks[str(item.task_id)].name,
                "status": dependency_tasks[str(item.task_id)].status.value,
                "blockedByApproval": dependency_tasks[str(item.task_id)].status not in {TaskStatus.DONE, TaskStatus.CANCELLED},
            }
            for item in dependents if str(item.task_id) in dependency_tasks
        ],
        "history": [_review_summary(db, item) for item in history],
        "comments": [
            {
                "id": str(item.id), "content": item.content, "author": _person(item.author),
                "createdAt": item.created_at.isoformat(),
            }
            for item in comments
        ],
        "documents": [
            {
                "id": str(item.id), "title": item.title, "type": item.document_type.value,
                "fileUrl": item.file_url, "version": item.version, "notes": item.notes,
            }
            for item in documents
        ],
        "siteReports": [
            {
                "id": str(item.id), "reportDate": item.report_date.isoformat(),
                "summary": item.summary_text, "status": item.review_status,
                "submittedBy": _person(item.submitted_by),
            }
            for item in reports
        ],
        "issues": [
            {
                "id": str(item.id), "title": item.title, "category": item.category,
                "severity": item.severity.value, "status": item.status.value,
            }
            for item in issues
        ],
    }
