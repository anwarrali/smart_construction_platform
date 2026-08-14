"""The one place that answers "is this person allowed to do this?".

Resolution order, most specific last:

  1. the role's catalogue default
  2. an administrator's override for that whole role
  3. an administrator's override for that person, everywhere
  4. an administrator's override for that person on this project

Every step can grant or revoke, so an administrator can both widen and narrow
access without the code needing a special case for either direction.

Two rules are enforced regardless of configuration:

  * a deactivated or suspended account has no permissions at all;
  * a project-scoped permission additionally requires access to that project,
    so granting a permission never smuggles in access to a project the person
    is not a member of.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, user_has_project_access
from app.core.permission_catalogue import BY_CODE, CATALOGUE, role_defaults
from app.db.database import get_db
from app.models.enums import UserRole, UserStatus
from app.models.permission import (
    ConsultantEngineerScope,
    RolePermissionOverride,
    UserPermissionOverride,
)
from app.models.project import Project
from app.models.user import User


def _role_overrides(db: Session, role: UserRole) -> dict[str, bool]:
    return {
        row.permission_code: row.allowed
        for row in db.query(RolePermissionOverride).filter(
            RolePermissionOverride.role == role
        ).all()
    }


def _user_overrides(db: Session, user_id: uuid.UUID) -> list[UserPermissionOverride]:
    return db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user_id
    ).all()


def effective_permissions(
    db: Session, user: User, project_id: uuid.UUID | None = None
) -> set[str]:
    """Every permission code this person holds, in this context."""
    if user.status != UserStatus.ACTIVE:
        return set()

    granted = role_defaults(user.role)

    for code, allowed in _role_overrides(db, user.role).items():
        if code not in BY_CODE:
            continue
        granted.add(code) if allowed else granted.discard(code)

    overrides = _user_overrides(db, user.id)
    # Global rows first, then project rows, so the narrower decision wins.
    for row in sorted(overrides, key=lambda item: item.project_id is not None):
        if row.permission_code not in BY_CODE:
            continue
        if row.project_id is not None and row.project_id != project_id:
            continue
        granted.add(row.permission_code) if row.allowed else granted.discard(row.permission_code)

    # An administrator must never be able to remove their own ability to
    # administer, or the platform becomes unmanageable.
    if user.role == UserRole.ADMIN:
        granted |= {item.code for item in CATALOGUE if item.admin_locked}

    return granted


def has_permission(
    db: Session, user: User, code: str, project_id: uuid.UUID | None = None
) -> bool:
    permission = BY_CODE.get(code)
    if permission is None:
        # An unknown code is a programming error, not an open door.
        return False
    if code not in effective_permissions(db, user, project_id):
        return False
    if permission.project_scoped and project_id is not None:
        return user_has_project_access(db, user, project_id)
    return True


def require(db: Session, user: User, code: str, project_id: uuid.UUID | None = None) -> None:
    """Raise the standard 403 unless the person holds the permission."""
    if not has_permission(db, user, code, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to {BY_CODE[code].label.lower()}"
            if code in BY_CODE else "Insufficient permissions for this action",
        )


def require_permission(code: str):
    """FastAPI dependency for permissions that are not project-scoped.

    Project-scoped endpoints should call `require(...)` inside the handler,
    where the project id is known.
    """

    def dependency(
        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
    ) -> User:
        require(db, current_user, code)
        return current_user

    return dependency


def manageable_project(
    db: Session, user: User, project_id: uuid.UUID, code: str
) -> Project:
    """The project, if this person may perform `code` on it.

    This is the configurable replacement for the hardcoded "administrator or the
    assigned project manager" check. The capability became configurable; the two
    restrictions around it did not:

      * a project manager may only act on the project they are assigned to, even
        if an administrator grants them the permission platform-wide;
      * `require` re-checks project access for every project-scoped permission,
        so a grant can never reach a project the person is not a member of.

    A permission is therefore only ever an additional condition here, never a
    way around membership or ownership.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if user.role == UserRole.PROJECT_MANAGER and project.project_manager_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only manage your assigned project",
        )
    require(db, user, code, project_id)
    return project


# --- Consultant scoping ----------------------------------------------------

def consultant_engineer_scope(
    db: Session, project_id: uuid.UUID, consultant_id: uuid.UUID
) -> set[uuid.UUID]:
    """The engineers a consultant is restricted to on this project.

    An empty set means "not restricted by engineer", which is the state of
    every project that has never used this feature.
    """
    return {
        row.engineer_user_id
        for row in db.query(ConsultantEngineerScope).filter(
            ConsultantEngineerScope.project_id == project_id,
            ConsultantEngineerScope.consultant_user_id == consultant_id,
        ).all()
    }


def consultant_covers_engineers(
    db: Session, project_id: uuid.UUID, consultant_id: uuid.UUID,
    engineer_ids: set[uuid.UUID],
) -> bool:
    """True when an engineer-level restriction does not block this review."""
    scope = consultant_engineer_scope(db, project_id, consultant_id)
    if not scope:
        return True
    # Reviewing is allowed when at least one of the people responsible for the
    # work is inside the consultant's remit.
    return bool(scope & engineer_ids) if engineer_ids else False
