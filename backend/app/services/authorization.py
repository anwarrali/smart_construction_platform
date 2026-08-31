"""The one place that answers "is this person allowed to do this?".

Resolution order, most specific last:

  1. the office role's permissions, unioned with the project role's
     — configurable rows in `roles` / `role_permissions`, resolved by
     `app.services.rbac`; the retired six-value enum is only a fallback for an
     account the RBAC backfill has not reached
  2. an administrator's override for that whole role
  3. an administrator's override for that person, everywhere
  4. an administrator's override for that person on this project

Every step can grant or revoke, so an administrator can both widen and narrow
access without the code needing a special case for either direction.

Three rules are enforced regardless of configuration:

  * a deactivated or suspended account has no permissions at all;
  * a project-scoped permission additionally requires access to that project,
    so granting a permission never smuggles in access to a project the person
    is not a member of;
  * an external participant — somebody on a project for a contractor,
    subcontractor or the client — never holds a permission that is not
    project-scoped, and never holds the office's own authority (reviewing,
    approving, verifying, running the team), whatever role or override says
    otherwise.

This module is the only authorization path. Voice, the AI tool layer, the
agents, document retrieval and the IFC workspace all arrive here; none of them
keeps its own role table any more.
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
from app.services import rbac


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


def legacy_effective_permissions(
    db: Session, user: User, project_id: uuid.UUID | None = None
) -> set[str]:
    """The retired resolution, preserved verbatim.

    Nothing in the application calls this. It exists so
    `app.db.rbac_equivalence` can compare the configurable model's answer
    against the one the platform used to give, for every real account, and
    prove the migration changed nobody's access except where a behaviour change
    was declared on purpose. Deleting it before that gate has run in production
    would remove the only evidence that the redesign was safe.
    """
    if user.status != UserStatus.ACTIVE:
        return set()

    granted = role_defaults(user.role)

    for code, allowed in _role_overrides(db, user.role).items():
        if code not in BY_CODE:
            continue
        granted.add(code) if allowed else granted.discard(code)

    granted = _apply_user_overrides(db, user, project_id, granted)

    if user.role == UserRole.ADMIN:
        granted |= {item.code for item in CATALOGUE if item.admin_locked}

    return granted


def _apply_user_overrides(
    db: Session, user: User, project_id: uuid.UUID | None, granted: set[str]
) -> set[str]:
    """Administrator decisions about one person, narrowest last."""
    overrides = _user_overrides(db, user.id)
    # Global rows first, then project rows, so the narrower decision wins.
    for row in sorted(overrides, key=lambda item: item.project_id is not None):
        if row.permission_code not in BY_CODE:
            continue
        if row.project_id is not None and row.project_id != project_id:
            continue
        granted.add(row.permission_code) if row.allowed else granted.discard(row.permission_code)
    return granted


def effective_permissions(
    db: Session, user: User, project_id: uuid.UUID | None = None
) -> set[str]:
    """Every permission code this person holds, in this context.

    The one authoritative calculation. Resolution order is unchanged from the
    enum-based model — only the first step now reads configurable roles
    instead of a hardcoded table:

      1. the office role's permissions, unioned with the project role's
         (`app.services.rbac.resolved_permissions`)
      2. an administrator's override for that whole role, on the pre-backfill
         fallback path only — once a user has a database role, those decisions
         live in `role_permissions` and re-applying them would double-count
      3. an administrator's override for that person, everywhere
      4. an administrator's override for that person on this project

    Then the ceilings. A deactivated account holds nothing. An external
    participant never holds a permission that is not project-scoped. And an
    external participant never holds the office's **certification or access
    governance** — `rbac.NEVER_EXTERNAL` — re-applied here, after overrides, so
    a mistake in Access Control cannot become a breach.

    ## Why the strip here is narrower than the one in `resolved_permissions`

    `resolved_permissions` removes the whole `office_only` set from an external
    participant, because that step is about what a *role* confers, and role
    inheritance is where a mistake is silent — the seeded contractor template
    inherits an Engineer's permissions, so an office re-permissioning a role
    could otherwise hand a contractor authority nobody decided to give.

    This step is about what an administrator **deliberately typed into Access
    Control for one named person**, and that is a different act. An office that
    wants its main contractor to maintain the construction programme, or to
    raise and close tasks on their own scope, is describing a real arrangement;
    refusing it would be the platform overruling the office about its own
    project. So four codes — `task.create`, `task.edit`, `schedule.edit`,
    `issue.resolve` — are office work by default and delegable by decision.

    What is never delegable is certification (approving work, verifying a
    report, approving a design change, certifying a payment claim, confirming
    evidence, acting on the office's review material) and access governance
    (membership, parties, external invitations, document shares, project
    settings). A contractor signing off their own work is the failure the whole
    arrangement exists to prevent, and a contractor who can grant access can
    grant themselves everything else.
    """
    if user.status != UserStatus.ACTIVE:
        return set()

    granted = rbac.resolved_permissions(db, user, project_id)

    if user.org_role_id is None:
        # Fallback path: this account predates the backfill, so the role-level
        # overrides have not been folded into a role row for it yet.
        for code, allowed in _role_overrides(db, user.role).items():
            if code not in BY_CODE:
                continue
            granted.add(code) if allowed else granted.discard(code)

    granted = _apply_user_overrides(db, user, project_id, granted)

    # Admin-locked codes are restored *after* the overrides, on both paths.
    #
    # `resolved_permissions` also adds them for an undeletable role, but that
    # happens before this line, so a per-person override could strip one back
    # off — and `platform.manage_users` being revocable from the office
    # administrator is precisely the lockout the flag exists to prevent. The
    # legacy branch below always re-applied them here; the migrated branch did
    # not, and the asymmetry was invisible until every account had a role.
    # The office administrator role is the undeletable one, which is how the
    # platform names "somebody must always be able to administer". A branch
    # here also recognised an unmigrated ADMIN account; there are none.
    if bool(getattr(rbac.get_role(db, user.org_role_id), "undeletable", False)):
        granted |= {item.code for item in CATALOGUE if item.admin_locked}

    if rbac.is_external_participant(db, user, project_id):
        granted -= rbac.NON_PROJECT_SCOPED
        granted -= rbac.NEVER_EXTERNAL

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


def can_view_all_projects_effective(db: Session, user: User) -> bool:
    """Whether this person may read any project without being a member of it.

    Resolves the catalogue's `platform.view_all_projects`. This used to be a
    hardcoded `role == UserRole.ADMIN` check (`can_view_all_projects` in
    `app.core.permissions`, since removed as dead code once nothing called
    it) that toggling the permission in Access Control had no effect on.
    `app.core.deps.user_has_project_access` / `accessible_project_ids` and
    `app.api.projects._scoped_projects_query` now call this as the sole gate
    for "sees everything" — not `can_view_all_projects_effective(...) or
    <the old hardcoded check>`, because an unconditional static OR would make
    a revoke impossible no matter what an administrator configures (it would
    always win first). The default is unaffected: `platform.view_all_projects`
    defaults to {ADMIN} in the catalogue, so an unconfigured Administrator
    resolves to the exact same answer the hardcoded check used to give.

    Why this cannot recurse: `has_permission` only calls back into
    `user_has_project_access` for a *project-scoped* permission, and only when
    given a `project_id`. `platform.view_all_projects` is declared
    `project_scoped=False` in the catalogue (see
    test_platform_view_all_projects.py::test_platform_view_all_projects_is_not_project_scoped),
    and this function never passes a `project_id` regardless — so the
    recursive branch in `has_permission` is structurally unreachable from here
    even if that flag were ever changed by mistake.

    Cached on the `User` instance for the request's lifetime: `deps.py` calls
    this from `user_has_project_access`, which is itself called several times
    per request in some handlers, and `get_current_user` is cached per-request
    by FastAPI's dependency injection, so the same `User` object is safe to
    stash the answer on without leaking across requests or users.
    """
    cached = getattr(user, "_view_all_projects_effective", None)
    if cached is not None:
        return cached[0]
    result = has_permission(db, user, "platform.view_all_projects")
    user._view_all_projects_effective = (result,)
    return result


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

    Two conditions, and neither is a role name:

      * the person holds `code` on this project — `require` re-checks project
        access for every project-scoped permission, so a grant can never reach
        a project somebody is not on;
      * the project exists.

    ## What was removed here, and why

    This used to additionally refuse when `user.role == UserRole.PROJECT_MANAGER
    and project.project_manager_id != user.id` — "a project manager may only act
    on the project they are assigned to". That rule belonged to the six-value
    enum, and under configurable roles it does two wrong things at once.

    It reads a job title as a confinement. An office that creates a role called
    "Project Manager" has said what that role may *do*; it has not said "and
    only on one project". Meanwhile somebody in an identically-permissioned role
    the office called "Senior Engineer" was never confined at all, so the same
    permissions produced different reach depending on which of six retired words
    the account happened to carry.

    And it was redundant where it was right. `require` already demands project
    access, and `user_has_project_access` already resolves that from ownership,
    management and active membership. Somebody who is not on a project cannot
    act on it whatever their role says; somebody who *is* on it, and whom the
    office has given `project.manage_members`, is precisely who the office meant
    to let manage it.

    Declared as `project_manager_scope_from_membership` in
    `app.db.rbac_equivalence`.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
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
