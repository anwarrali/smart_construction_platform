"""The one place that answers "is this person allowed to do this?".

Resolution order, most specific last:

  1. the office role's permissions, unioned with the project role's
     — configurable rows in `roles` / `role_permissions`, resolved by
     `app.services.rbac` (a role is changed by editing those rows)
  2. an administrator's override for that person, everywhere
  3. an administrator's override for that person on this project

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

from app.core.deps import get_current_user, user_can_see_project_record, user_has_project_access
from app.core.permission_catalogue import BY_CODE, CATALOGUE
from app.db.database import get_db
from app.models.enums import UserStatus
from app.models.permission import ConsultantEngineerScope, UserPermissionOverride
from app.models.project import Project
from app.models.user import User
from app.services import rbac


def _user_overrides(db: Session, user_id: uuid.UUID) -> list[UserPermissionOverride]:
    return db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user_id
    ).all()


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

    The one authoritative calculation:

      1. the office role's permissions, unioned with the project role's
         (`app.services.rbac.resolved_permissions`)
      2. an administrator's override for that person, everywhere
      3. an administrator's override for that person on this project

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
    project. So five codes — `task.create`, `task.edit`, `schedule.edit`,
    `issue.resolve`, `message.broadcast` — are office work by default and
    delegable by decision.

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

    # Raises `UnmigratedUser` for an account with no office role: there is no
    # fallback to the retired enum, so such an account holds nothing.
    granted = rbac.resolved_permissions(db, user, project_id)

    granted = _apply_user_overrides(db, user, project_id, granted)

    # Admin-locked codes are restored *after* the overrides.
    #
    # `resolved_permissions` also adds them for an undeletable role, but that
    # happens before this line, so a per-person override could strip one back
    # off — and `platform.manage_users` being revocable from the office
    # administrator is precisely the lockout the flag exists to prevent. The
    # office administrator role is the undeletable one, which is how the
    # platform names "somebody must always be able to administer".
    if rbac.holds_office_admin_role(db, user):
        granted |= {item.code for item in CATALOGUE if item.admin_locked}

    if rbac.is_external_participant(db, user, project_id):
        granted -= rbac.NON_PROJECT_SCOPED
        granted -= rbac.NEVER_EXTERNAL

    # In one project's context, a project-scoped code means something only
    # where the person can reach the project (`has_permission` re-checks the
    # same). Reporting it anyway told the interface an administrator could
    # open the tasks of a project they only administer (QA-06B).
    if project_id is not None:
        work = user_has_project_access(db, user, project_id)
        record = work or user_can_see_project_record(db, user, project_id)
        def reachable(code: str) -> bool:
            permission = BY_CODE.get(code)
            if permission is None or not permission.project_scoped or work:
                return True
            return record and permission.registry
        granted = {code for code in granted if reachable(code)}

    return granted


#: Why a permission is or is not held — the vocabulary of `explain_permissions`.
GRANTED_BY_ROLE = "granted_by_role"
GRANTED_BY_PROJECT_ROLE = "granted_by_project_role"
GRANTED_TO_USER = "granted_to_user"
GRANTED_ON_PROJECT = "granted_on_project"
ADMIN_LOCKED = "admin_locked"
DENIED_FOR_USER = "denied_for_user"
DENIED_ON_PROJECT = "denied_on_project"
BLOCKED_EXTERNAL = "blocked_external"
BLOCKED_PROJECT_ACCESS = "blocked_project_access"
ACCOUNT_INACTIVE = "account_inactive"
NOT_GRANTED = "not_granted"


def explain_permissions(
    db: Session, user: User, project_id: uuid.UUID | None = None
) -> dict[str, dict]:
    """Why each catalogue permission is or is not held, for the editor.

    `held` is **not** recomputed here: it is membership of
    `effective_permissions`, the one resolver, so the editor can never show a
    permission the server would refuse. Only the *reason* is derived — from
    the same layers, in the same order — and `test_rbac_customization` asserts
    the two agree for every code.

    Returns `{code: {"held", "reason", "role_grants", "override"}}`, where
    `override` is the explicit decision at this scope (True, False or None for
    "inherits") and `role_grants` whether the governing roles confer it.
    """
    effective = effective_permissions(db, user, project_id)
    overrides = _user_overrides(db, user.id)
    global_rows = {row.permission_code: row.allowed for row in overrides if row.project_id is None}
    project_rows = {
        row.permission_code: row.allowed for row in overrides
        if project_id is not None and row.project_id == project_id
    }
    office_role = rbac.role_permission_codes(db, rbac.office_role_id(db, user, user.org_role_id))
    context = rbac.membership_context(db, user.id, project_id)
    project_role = (
        rbac.role_permission_codes(db, rbac.office_role_id(db, user, context.member.project_role_id))
        if context.member is not None and context.member.project_role_id is not None else set()
    )
    external = rbac.is_external_participant(db, user, project_id)
    office_admin = rbac.holds_office_admin_role(db, user)
    active = user.status == UserStatus.ACTIVE

    result: dict[str, dict] = {}
    for item in CATALOGUE:
        code = item.code
        held = code in effective
        at_scope = project_rows.get(code, global_rows.get(code))
        if not active:
            reason = ACCOUNT_INACTIVE
        elif held:
            if project_rows.get(code) is True:
                reason = GRANTED_ON_PROJECT
            elif global_rows.get(code) is True and code not in project_rows:
                reason = GRANTED_TO_USER
            elif code in office_role:
                reason = GRANTED_BY_ROLE
            elif code in project_role:
                reason = GRANTED_BY_PROJECT_ROLE
            elif office_admin and item.admin_locked:
                reason = ADMIN_LOCKED
            else:
                reason = GRANTED_BY_ROLE
        elif project_rows.get(code) is False:
            reason = DENIED_ON_PROJECT
        elif global_rows.get(code) is False and code not in project_rows:
            reason = DENIED_FOR_USER
        elif external and (code in office_role or code in project_role or at_scope):
            reason = BLOCKED_EXTERNAL
        elif project_id is not None and (code in office_role or code in project_role or at_scope):
            reason = BLOCKED_PROJECT_ACCESS
        else:
            reason = NOT_GRANTED
        result[code] = {
            "held": held, "reason": reason,
            "role_grants": code in office_role or code in project_role,
            "override": at_scope,
        }
    return result


def governing_role(db: Session, user: User):
    """The role whose permissions actually apply to this person's office role.

    The office's copy when the account still points at a template the office
    has edited (`rbac.office_role_id`), else the assigned role itself.
    """
    return rbac.get_role(db, rbac.office_role_id(db, user, user.org_role_id))


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
        if permission.registry:
            return user_can_see_project_record(db, user, project_id)
        return user_has_project_access(db, user, project_id)
    return True


def can_run_project(db: Session, user: User) -> bool:
    """Whether this person may be named a project's manager.

    The capability, not a title: somebody who may be staffed onto a project
    and who may run its team. It used to be `role == PROJECT_MANAGER` on one
    of the two write paths, so an office could not nominate somebody in a role
    it had created however it had permissioned them — and `create_project` and
    `update_project` answered the same question two different ways.
    """
    return rbac.is_staffable(db, user) and has_permission(db, user, "project.manage_members")


def can_be_project_client(db: Session, user: User) -> bool:
    """Whether this person may be named a project's client (`Project.owner_id`).

    An active account from outside the office whose role carries the client's
    view of a project. It used to be `role == OWNER`. Both halves matter:
    `client_portal.view` alone is also held by the office administrator, and
    an office member is never the client of a project the office runs; being
    external alone would admit a contractor.
    """
    return (
        user.status == UserStatus.ACTIVE
        and not user.is_internal
        and has_permission(db, user, "client_portal.view")
    )


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


def can_work_in_all_projects_effective(db: Session, user: User) -> bool:
    """Whether this person may work inside any project without being on it.

    Resolves `platform.work_in_all_projects`, split from
    `platform.view_all_projects` by QA-06B: the office administrator keeps the
    registry (see `app.core.deps.user_can_see_project_record`), office
    leadership keeps the work. Same recursion argument and per-request cache as
    `can_view_all_projects_effective`: the code is not project-scoped and no
    `project_id` is ever passed.
    """
    cached = getattr(user, "_work_in_all_projects_effective", None)
    if cached is not None:
        return cached[0]
    result = has_permission(db, user, "platform.work_in_all_projects")
    user._work_in_all_projects_effective = (result,)
    return result


def require(db: Session, user: User, code: str, project_id: uuid.UUID | None = None) -> None:
    """Raise the standard 403 unless the person holds the permission."""
    if not has_permission(db, user, code, project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to {BY_CODE[code].label.lower()}"
            if code in BY_CODE else "Insufficient permissions for this action",
        )


def projects_with_permission(
    db: Session, user: User, code: str, project_ids: list[uuid.UUID] | None
) -> list[uuid.UUID]:
    """Of these projects, the ones where this person holds `code`.

    For cross-project lists. `project_ids` is what `accessible_project_ids`
    returned; `None` there means "every project", and is expanded here rather
    than trusted, because reaching every project is not the same as holding a
    module's view permission in each of them — a per-project override can take
    it away on one job.

    Before 2026-10-23 the lists of site reports, issues, design changes and
    tasks asked only for project access, so revoking `site_report.view` hid the
    page and left the API answering (`docs/PERMISSION_COVERAGE.md`).
    """
    if project_ids is None:
        project_ids = [row for (row,) in db.query(Project.id).all()]
    return [pid for pid in project_ids if has_permission(db, user, code, pid)]


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
