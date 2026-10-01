"""Who may be given a task on a project.

One rule, used by the tasks API and by the voice assistant, so that an
assignment the assistant proposes is never one the API then refuses.

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
