"""Central authorization decisions for Worker field evidence."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.deps import (
    is_consultant_engineer,
    is_main_contractor_engineer,
    is_worker,
    user_has_project_access,
)
from app.models.enums import FieldSubmissionStatus, UserRole
from app.models.field_submission import FieldSubmission
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.field_submission_policy import (
    engineer_assignment_allows_review,
    worker_assignment_allows_submission,
)
from app.services.photo_archive_policy import (
    category_management_allowed,
    human_tagging_allowed,
)


def _active_project_role(
    db: Session, user: User, project_id, role: UserRole
) -> bool:
    return db.query(ProjectMember.id).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.role_on_project == role,
        ProjectMember.is_active == True,
    ).first() is not None


def can_worker_submit_evidence(db: Session, user: User, task: Task) -> bool:
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == task.project_id,
        ProjectMember.user_id == user.id,
    ).first()
    return worker_assignment_allows_submission(
        role=user.role.value,
        active=is_worker(user),
        member_role=membership.role_on_project.value if membership else None,
        member_active=bool(membership and membership.is_active),
        member_project_id=str(membership.project_id) if membership else None,
        task_project_id=str(task.project_id),
        assigned_to_task=any(assignee.id == user.id for assignee in task.assignees),
    )


def can_engineer_review_field_submission(
    db: Session, user: User, submission: FieldSubmission
) -> bool:
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == submission.project_id,
        ProjectMember.user_id == user.id,
    ).first()
    return engineer_assignment_allows_review(
        role=user.role.value,
        affiliation=user.engineer_affiliation,
        active=is_main_contractor_engineer(user),
        member_role=membership.role_on_project.value if membership else None,
        member_active=bool(membership and membership.is_active),
        member_project_id=str(membership.project_id) if membership else None,
        submission_project_id=str(submission.project_id),
        assigned_to_task=any(assignee.id == user.id for assignee in submission.task.assignees),
        reviewer_id=str(user.id),
        worker_id=str(submission.worker_id),
    )


def can_view_field_submission(
    db: Session, user: User, submission: FieldSubmission
) -> bool:
    if not user_has_project_access(db, user, submission.project_id):
        return False
    if is_worker(user):
        return user.id == submission.worker_id
    if can_engineer_review_field_submission(db, user, submission):
        return True
    project = db.get(Project, submission.project_id)
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.PROJECT_MANAGER and project and project.project_manager_id == user.id:
        return True
    if user.role == UserRole.OWNER and project and project.owner_id == user.id:
        return True
    return (
        is_consultant_engineer(user)
        and submission.status == FieldSubmissionStatus.VERIFIED
    )


def authorized_engineer_ids(db: Session, task: Task) -> set:
    return {
        user.id
        for user in task.assignees
        if is_main_contractor_engineer(user)
        and _active_project_role(db, user, task.project_id, UserRole.ENGINEER)
    }


def can_manage_project_photo_categories(
    db: Session, user: User, project_id
) -> bool:
    project = db.get(Project, project_id)
    return bool(project) and category_management_allowed(
        user.role.value,
        is_assigned_pm=bool(project and project.project_manager_id == user.id),
    )


def can_categorize_field_photo(
    db: Session, user: User, submission: FieldSubmission
) -> bool:
    worker_allowed = (
        submission.worker_id == user.id
        and submission.status == FieldSubmissionStatus.SUBMITTED
        and can_worker_submit_evidence(db, user, submission.task)
    )
    engineer_allowed = can_engineer_review_field_submission(db, user, submission)
    return human_tagging_allowed(
        user.role.value,
        owns_submission=submission.worker_id == user.id,
        submission_pending=worker_allowed,
        assigned_contractor_engineer=engineer_allowed,
    )


def can_view_project_photo_archive(db: Session, user: User, project_id) -> bool:
    return user_has_project_access(db, user, project_id)
