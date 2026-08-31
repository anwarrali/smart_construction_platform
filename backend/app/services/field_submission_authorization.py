"""Who may file, confirm and read field evidence.

Every decision resolves through `has_permission`. The retired versions of these
functions asked whether somebody *was* a worker or *was* a main-contractor
engineer; they now ask whether somebody holds `field_evidence.submit` or
`field_evidence.verify` on the project in question, which is the same question
an office can answer differently for itself.

The names changed with the roles — `can_worker_submit_evidence` became
`can_submit_field_evidence` — because the old names described a job title that
no longer exists, and a function called `can_worker_...` invoked for a Site
Engineer is a comment that lies.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.models.enums import FieldSubmissionStatus, UserStatus
from app.models.field_submission import FieldSubmission
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.authorization import has_permission
from app.services.field_submission_policy import (
    evidence_review_allowed,
    evidence_submission_allowed,
)
from app.services.photo_archive_policy import category_management_allowed


def _membership(db: Session, user: User, project_id) -> ProjectMember | None:
    return db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
    ).first()


def can_submit_field_evidence(db: Session, user: User, task: Task) -> bool:
    """Whether this person may record evidence against this task."""
    membership = _membership(db, user, task.project_id)
    return evidence_submission_allowed(
        holds_permission=has_permission(
            db, user, "field_evidence.submit", task.project_id
        ),
        active=user.status == UserStatus.ACTIVE,
        member_active=bool(membership and membership.is_active),
        member_project_id=str(membership.project_id) if membership else None,
        task_project_id=str(task.project_id),
        assigned_to_task=any(assignee.id == user.id for assignee in task.assignees),
        manages_work=has_permission(db, user, "task.edit", task.project_id),
    )


def can_review_field_submission(
    db: Session, user: User, submission: FieldSubmission
) -> bool:
    """Whether this person may confirm or reject somebody else's evidence."""
    membership = _membership(db, user, submission.project_id)
    return evidence_review_allowed(
        holds_permission=has_permission(
            db, user, "field_evidence.verify", submission.project_id
        ),
        active=user.status == UserStatus.ACTIVE,
        member_active=bool(membership and membership.is_active),
        member_project_id=str(membership.project_id) if membership else None,
        submission_project_id=str(submission.project_id),
        assigned_to_task=any(
            assignee.id == user.id for assignee in submission.task.assignees
        ),
        reviews_work=has_permission(db, user, "task.review", submission.project_id),
        reviewer_id=str(user.id),
        submitted_by_id=str(submission.submitted_by_id),
    )


def verification_required(db: Session, project_id) -> bool:
    """Whether this project asks for a second person to confirm evidence."""
    project = db.get(Project, project_id)
    return bool(project is None or project.field_evidence_verification_required)


def can_view_field_submission(
    db: Session, user: User, submission: FieldSubmission
) -> bool:
    """Whether this person may read one evidence package.

    Ordered from the narrowest claim to the widest: your own submission, then
    the authority to review it, then the authority to see the project's work.
    An external participant who is neither the author nor a reviewer sees a
    verified package only, which is what the consultant-side rule used to say
    and is now said about anybody outside the office.
    """
    if not user_has_project_access(db, user, submission.project_id):
        return False
    if submission.submitted_by_id == user.id:
        return True
    if can_review_field_submission(db, user, submission):
        return True

    project = db.get(Project, submission.project_id)
    if project and project.project_manager_id == user.id:
        return True
    if project and project.owner_id == user.id:
        # The client sees confirmed work, not work in progress — the same rule
        # their document access follows.
        return submission.status == FieldSubmissionStatus.VERIFIED
    if has_permission(db, user, "task.view", submission.project_id) and user.is_internal:
        return True
    return submission.status == FieldSubmissionStatus.VERIFIED


def authorized_reviewer_ids(db: Session, task: Task) -> set:
    """People to notify when evidence lands on this task.

    The assignees who may actually confirm it. Notifying anybody else would
    ask for an action they cannot take.
    """
    return {
        user.id
        for user in task.assignees
        if has_permission(db, user, "field_evidence.verify", task.project_id)
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
    """Tagging a photo follows the evidence it belongs to.

    The author may tag their own package while it is still open; a reviewer may
    tag one they are entitled to review. Nobody else, because a category is a
    claim about the work and this is the audit trail for it.
    """
    if submission.submitted_by_id == user.id:
        return (
            submission.status == FieldSubmissionStatus.SUBMITTED
            and can_submit_field_evidence(db, user, submission.task)
        )
    return can_review_field_submission(db, user, submission)


def can_view_project_photo_archive(db: Session, user: User, project_id) -> bool:
    return user_has_project_access(db, user, project_id)
