"""Who may be given a task on a project, and who may review work on it.

One rule each, used by every path that assigns — the tasks API, project
setup, the voice assistant and the pickers that feed them — so that a
candidate offered anywhere is never one an endpoint then refuses.

It used to be a set of retired enum values — Engineer, Consultant, and the
project's own Project Manager — checked against both the membership's
`role_on_project` and the account's `users.role`. Neither column could say
anything about a role an office had created. The rule now asks what the
assignment actually requires: somebody on this project who may record
progress on work, which is `task.update_progress`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.enums import UserStatus
from app.models.project import ProjectMember
from app.models.user import User
from app.services.authorization import has_permission

NOT_A_MEMBER = "Every assignee must be an active member of this project"
CANNOT_EXECUTE = "This person cannot be assigned execution work on this project"
NOT_A_REVIEWER = "Every reviewer must be an active office member of this project who may review work"


def assignee_refusal(
    db: Session, project_id: uuid.UUID, membership: ProjectMember | None, user: User | None
) -> str | None:
    """Why this person cannot hold a task here, or None if they can."""
    if (
        membership is None
        or not membership.is_active
        or user is None
        or user.status != UserStatus.ACTIVE
    ):
        return NOT_A_MEMBER
    if not has_permission(db, user, "task.update_progress", project_id):
        return CANNOT_EXECUTE
    return None


def reviewer_refusal(
    db: Session, project_id: uuid.UUID, membership: ProjectMember | None, user: User | None
) -> str | None:
    """Why this person cannot be named a reviewer here, or None if they can.

    Office staff only — naming a reviewer is naming who carries the office's
    review authority on this project — and they must hold `task.review` on it.
    """
    if (
        membership is None
        or not membership.is_active
        or user is None
        or user.status != UserStatus.ACTIVE
        or not user.is_internal
        or membership.party_id is not None
    ):
        return NOT_A_REVIEWER
    if not has_permission(db, user, "task.review", project_id):
        return NOT_A_REVIEWER
    return None
