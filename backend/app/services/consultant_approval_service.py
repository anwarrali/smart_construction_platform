"""Project-scoped Consultant review authorization.

Controllers should ask this service for review authority instead of comparing a
Consultant Engineer's account specialty with a task discipline.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.deps import is_consultant_engineer
from app.models.enums import ConsultantApprovalMode, UserRole
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.authorization import consultant_covers_engineers
from app.services.consultant_approval_policy import (
    ReviewerAssignment,
    assignment_allows_review,
    normalize_discipline,
)


def _active_consultant_member(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    return db.query(ProjectMember.id).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.role_on_project == UserRole.CONSULTANT,
        ProjectMember.is_active == True,
    ).first() is not None


def can_consultant_review_task(db: Session, user: User, task: Task) -> bool:
    if not is_consultant_engineer(user):
        return False
    if not _active_consultant_member(db, user.id, task.project_id):
        return False
    project = db.get(Project, task.project_id)
    if not project:
        return False
    assignments = db.query(ProjectConsultantReviewer).filter(
        ProjectConsultantReviewer.project_id == task.project_id,
        ProjectConsultantReviewer.user_id == user.id,
    ).all()
    if not assignment_allows_review(
        project.consultant_approval_mode.value,
        [
            ReviewerAssignment(str(item.project_id), str(item.user_id), item.discipline)
            for item in assignments
        ],
        project_id=str(task.project_id),
        user_id=str(user.id),
        task_discipline=task.discipline,
    ):
        return False
    # Some organisations divide review work by person rather than by
    # discipline. When an administrator has named the engineers this consultant
    # covers, work belonging to anyone else is out of their remit. Projects that
    # never configure this are unaffected.
    return consultant_covers_engineers(
        db, task.project_id, user.id, {assignee.id for assignee in task.assignees},
    )


def authorized_consultant_ids(
    db: Session, project_id: uuid.UUID, discipline: str | None
) -> set[uuid.UUID]:
    project = db.get(Project, project_id)
    if not project:
        return set()
    query = db.query(ProjectConsultantReviewer.user_id).join(
        ProjectMember,
        (ProjectMember.project_id == ProjectConsultantReviewer.project_id)
        & (ProjectMember.user_id == ProjectConsultantReviewer.user_id),
    ).join(User, User.id == ProjectConsultantReviewer.user_id).filter(
        ProjectConsultantReviewer.project_id == project_id,
        ProjectMember.role_on_project == UserRole.CONSULTANT,
        ProjectMember.is_active == True,
        User.role == UserRole.ENGINEER,
        User.engineer_affiliation == "external_consultant",
    )
    if project.consultant_approval_mode == ConsultantApprovalMode.CENTRALIZED_REVIEW:
        query = query.filter(ProjectConsultantReviewer.discipline.is_(None))
    else:
        normalized = normalize_discipline(discipline)
        if not normalized:
            return set()
        query = query.filter(ProjectConsultantReviewer.discipline == normalized)
    return {row[0] for row in query.all()}
