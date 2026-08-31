from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import uuid
from datetime import date, datetime, time, timezone

from app.db.database import get_db
from app.services.authorization import has_permission, require
from app.models.user import User
from app.models.issue import Issue
from app.schemas.issue import IssueOut, IssueCreate, IssueUpdate
from app.core.deps import (
    get_current_user,
    user_has_project_access,
    accessible_project_ids,
)
from app.services import work_scope
from app.models.enums import IssueStatus, IssueSeverity, UserRole
from app.models.project import Project, ProjectMember
from app.models.notification import Notification
from app.services.realtime import EventType, publish_event
from app.services.notification_service import (
    CATEGORY_WORKFLOW, PRIORITY_IMPORTANT, PRIORITY_NORMAL, notify, notify_users,
)
from app.models.enums import NotificationType
from app.services.audit_service import record_audit
from app.models.attachment import Attachment
from app.models.task import Task

router = APIRouter(prefix="/issues", tags=["Issues"])

@router.get("", response_model=List[IssueOut])
def list_issues(
    project_id: Optional[uuid.UUID] = None,
    status: Optional[IssueStatus] = None,
    discipline: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    raised_by_id: Optional[uuid.UUID] = None,
    has_attachments: Optional[bool] = None,
    task_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # See the note in `app.api.site_reports.list_site_reports`: the retired
    # organization-side refusal blocked the office's own engineers.
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(Issue)
    # "Sees every project" is `platform.view_all_projects`, which
    # `accessible_project_ids` already answers by returning None. Reading the
    # role instead meant two things went wrong: an administrator whose
    # permission had been explicitly revoked still bypassed the filter, and a
    # non-administrator who had been *granted* it got `None or []` — an empty
    # list, so they saw nothing at all.
    accessible_ids = accessible_project_ids(db, current_user)
    if accessible_ids is not None:
        query = query.filter(Issue.project_id.in_(accessible_ids))
    if project_id:
        query = query.filter(Issue.project_id == project_id)
    if status:
        query = query.filter(Issue.status == status)
    if discipline:
        # An explicitly requested filter, from the caller.
        discipline_task_ids = db.query(Task.id).filter(
            Task.project_id == project_id, Task.discipline == discipline,
        ) if project_id else db.query(Task.id).filter(Task.discipline == discipline)
        query = query.filter((Issue.task_id.is_(None)) | Issue.task_id.in_(discipline_task_ids))
    if project_id:
        # The caller's own scope, which they cannot widen by asking.
        query = work_scope.narrow_to_disciplines(
            query, Issue.task_id, db, current_user, project_id,
        )
    if date_from:
        query = query.filter(Issue.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.filter(Issue.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if raised_by_id:
        query = query.filter(Issue.raised_by_id == raised_by_id)
    if task_id:
        query = query.filter(Issue.task_id == task_id)
    attachment_exists = db.query(Attachment.id).filter(Attachment.entity_type == "ISSUE", Attachment.entity_id == Issue.id).exists()
    if has_attachments is not None:
        query = query.filter(attachment_exists if has_attachments else ~attachment_exists)
    items = query.order_by(Issue.created_at.desc()).all()
    counts = dict(db.query(Attachment.entity_id, func.count(Attachment.id)).filter(
        Attachment.entity_type == "ISSUE", Attachment.entity_id.in_([item.id for item in items])
    ).group_by(Attachment.entity_id).all()) if items else {}
    for item in items:
        item.attachment_count = counts.get(item.id, 0)
    return items

@router.get("/project/{project_id}", response_model=List[IssueOut])
def get_issues_by_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = work_scope.narrow_to_disciplines(
        db.query(Issue).filter(Issue.project_id == project_id),
        Issue.task_id, db, current_user, project_id,
    )
    return query.all()

@router.get("/{issue_id}", response_model=IssueOut)
def get_issue_by_id(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not user_has_project_access(db, current_user, issue.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this issue")
    if issue.task_id and not work_scope.task_is_in_scope(
        db, current_user, issue.project_id, db.get(Task, issue.task_id)
    ):
        raise HTTPException(status_code=403, detail="This issue is outside your discipline")
    issue.attachment_count = db.query(Attachment).filter(Attachment.entity_type == "ISSUE", Attachment.entity_id == issue.id).count()
    return issue

@router.post("", response_model=IssueOut)
def create_issue(
    issue_data: IssueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require(db, current_user, "issue.create", issue_data.project_id)
    if not user_has_project_access(db, current_user, issue_data.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    if issue_data.task_id:
        task = db.query(Task).filter(
            Task.id == issue_data.task_id,
            Task.project_id == issue_data.project_id,
        ).first()
        if not task:
            raise HTTPException(status_code=400, detail="taskId must belong to the selected project")
        # You may raise an issue against work you can actually see: your own
        # assignments, or work you review. Both halves of the retired check
        # said that in role terms; `can_see_task` says it in terms of the
        # assignments themselves, and `task_is_in_scope` keeps the discipline
        # boundary for a narrowed reviewer.
        if not work_scope.can_see_task(db, current_user, task):
            raise HTTPException(
                status_code=403,
                detail="You can only raise task issues for work assigned to you or under your review",
            )
        if not work_scope.task_is_in_scope(db, current_user, issue_data.project_id, task):
            raise HTTPException(
                status_code=403,
                detail="You cannot create observations for another discipline",
            )
    # Choosing who resolves an issue is `issue.resolve`. Raising one is
    # `issue.create`, which is wider — so somebody who may only raise issues
    # may not also decide who fixes them.
    if issue_data.assigned_to_id and not has_permission(
        db, current_user, "issue.resolve", issue_data.project_id
    ):
        raise HTTPException(status_code=403, detail="You cannot assign issue resolvers")
    new_issue = Issue(
        project_id=issue_data.project_id,
        task_id=issue_data.task_id,
        title=issue_data.title,
        description=issue_data.description,
        category=issue_data.category,
        due_date=issue_data.due_date,
        affects_schedule=issue_data.affects_schedule,
        severity=issue_data.severity,
        assigned_to_id=issue_data.assigned_to_id,
        raised_by_id=current_user.id,
        status=IssueStatus.OPEN
    )
    db.add(new_issue)
    db.flush()
    project = db.get(Project, issue_data.project_id)
    recipients = {project.project_manager_id if project else None, issue_data.assigned_to_id} - {None}
    if project and issue_data.severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL}:
        recipients.add(project.owner_id)
    if issue_data.category:
        for member in db.query(ProjectMember).filter(ProjectMember.project_id == issue_data.project_id,
                ProjectMember.is_active == True).all():
            profile = member.user.engineer_profile
            if (profile and profile.discipline.value == issue_data.category) or member.is_site_engineer:
                recipients.add(member.user_id)
    # Through the service (rather than one hand-built row each) so the issue
    # also reaches these people's phones, and so the duplicate-recipient case
    # — a project manager who is also the discipline engineer — is collapsed
    # in one place instead of relying on `recipients` being a set here.
    notify_users(
        db,
        user_ids=recipients,
        title="New Project Issue",
        message=f"A new {issue_data.severity.value}-priority issue was reported in {project.name if project else 'the project'}: {issue_data.title}",
        notification_type=NotificationType.TASK_UPDATED,
        project_id=issue_data.project_id,
        entity_type="ISSUE",
        entity_id=new_issue.id,
    )
    record_audit(db, actor_id=current_user.id, action="created", entity_type="issue", entity_id=new_issue.id, project_id=new_issue.project_id)
    # Project-scoped: an issue list shows every issue in the project, so
    # anyone viewing one needs the hint. Ids only — the refetch supplies the
    # detail, through the same endpoint that already filters by role.
    publish_event(
        db, event_type=EventType.ISSUE_CREATED, project_id=new_issue.project_id,
        entity_type="ISSUE", entity_id=new_issue.id,
    )
    db.commit()
    db.refresh(new_issue)
    return new_issue

@router.put("/{issue_id}", response_model=IssueOut)
def update_issue(
    issue_id: uuid.UUID,
    issue_data: IssueUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not user_has_project_access(db, current_user, issue.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this issue")
    project = db.get(Project, issue.project_id)
    # `project_manager_id` is validated at both write paths to be an active
    # PROJECT_MANAGER, so the role half was always implied by the id test.
    can_manage = bool(project and project.project_manager_id == current_user.id)
    if not can_manage and current_user.id not in {issue.raised_by_id, issue.assigned_to_id}:
        raise HTTPException(status_code=403, detail="You cannot update this issue")
    # Reassigning an issue and closing one are both `issue.resolve`, which is
    # `office_only` — so an external participant never reaches either, however
    # their project role is configured.
    if not has_permission(db, current_user, "issue.resolve", issue.project_id):
        if issue_data.assigned_to_id is not None:
            raise HTTPException(status_code=403, detail="You cannot reassign issue ownership")
        if issue_data.status in {IssueStatus.RESOLVED, IssueStatus.CLOSED}:
            raise HTTPException(status_code=403, detail="You cannot resolve or close site issues")
    if (
        issue.category
        and issue.category.startswith("blocker:")
        and issue_data.status in {IssueStatus.RESOLVED, IssueStatus.CLOSED}
        and not can_manage
    ):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can resolve task blockers")
    if issue_data.status in {IssueStatus.RESOLVED, IssueStatus.CLOSED} and not (
        (issue_data.resolution_notes and issue_data.resolution_notes.strip())
        or (issue.resolution_notes and issue.resolution_notes.strip())
    ):
        raise HTTPException(status_code=400, detail="A resolution note is required")
    if issue_data.title is not None:
        issue.title = issue_data.title
    if issue_data.description is not None:
        issue.description = issue_data.description
    if issue_data.category is not None:
        issue.category = issue_data.category
    if issue_data.due_date is not None:
        issue.due_date = issue_data.due_date
    if issue_data.affects_schedule is not None:
        issue.affects_schedule = issue_data.affects_schedule
    if issue_data.severity is not None:
        issue.severity = issue_data.severity
    if issue_data.status is not None:
        issue.status = issue_data.status
        if issue_data.status in {IssueStatus.RESOLVED, IssueStatus.CLOSED}:
            issue.resolved_at = datetime.now(timezone.utc)
    newly_assigned_to = None
    if issue_data.assigned_to_id is not None:
        # Captured before the write: after the assignment there is no longer
        # any way to tell a new assignee from a resave of the same one.
        if issue_data.assigned_to_id != issue.assigned_to_id:
            newly_assigned_to = issue_data.assigned_to_id
        issue.assigned_to_id = issue_data.assigned_to_id
    if issue_data.resolution_notes is not None:
        issue.resolution_notes = issue_data.resolution_notes
    if issue.raised_by_id != current_user.id and (
        issue_data.status is not None or issue_data.resolution_notes is not None
    ):
        notify(
            db,
            user_id=issue.raised_by_id,
            title="Task Blocker Updated" if issue.category and issue.category.startswith("blocker:") else "Project Issue Updated",
            message=(
                f'{issue.title} is now {issue.status.value.replace("_", " ")}.'
                + (f" {issue.resolution_notes}" if issue.resolution_notes else "")
            ),
            notification_type=NotificationType.TASK_UPDATED,
            project_id=issue.project_id,
            task_id=issue.task_id,
            entity_type="ISSUE",
            entity_id=issue.id,
        )

    # The assignee was never told. `assigned_to_id` has been settable since the
    # issue workflow migration, but the only notification on this path went to
    # whoever *raised* the issue — so the person expected to act on it learned
    # about it by noticing it in a list. Fired only when the assignee actually
    # changes, so repeated saves of an unrelated field stay silent.
    if newly_assigned_to and newly_assigned_to != current_user.id:
        notify(
            db,
            user_id=newly_assigned_to,
            title="Issue assigned to you",
            message=f'You were assigned to the issue "{issue.title}".',
            notification_type=NotificationType.TASK_ASSIGNED,
            category=CATEGORY_WORKFLOW,
            priority=PRIORITY_IMPORTANT if issue.severity == IssueSeverity.CRITICAL else PRIORITY_NORMAL,
            requires_action=True,
            project_id=issue.project_id,
            task_id=issue.task_id,
            entity_type="ISSUE",
            entity_id=issue.id,
            # One notification per assignment, not per subsequent edit.
            dedupe_key=f"issue-assigned:{issue.id}:{newly_assigned_to}",
            message_key="issue.assigned",
            message_params={"title": issue.title},
        )

        
    record_audit(db, actor_id=current_user.id, action="updated", entity_type="issue", entity_id=issue.id, project_id=issue.project_id)
    publish_event(
        db, event_type=EventType.ISSUE_UPDATED, project_id=issue.project_id,
        entity_type="ISSUE", entity_id=issue.id,
    )
    db.commit()
    db.refresh(issue)
    return issue

@router.delete("/{issue_id}")
def delete_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    project = db.get(Project, issue.project_id)
    require(db, current_user, "issue.resolve", issue.project_id)
    # `require` above already demanded `issue.resolve` *on this project*, and
    # a project-scoped permission carries project access with it, so being on
    # the project is settled. The extra refusal this replaces asked whether the
    # account was a PROJECT_MANAGER running a different project — a confinement
    # on one job title that never applied to an identically-permissioned role
    # the office had created itself.
    db.delete(issue)
    db.commit()
    return {"message": "Issue deleted successfully"}
