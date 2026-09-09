"""FastAPI dependencies for authentication and authorization."""

import uuid
from typing import Callable, Iterable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.permissions import is_admin
from app.core.security import decode_token
from app.db.database import get_db
from app.models.enums import UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.models.revoked_token import RevokedToken
from app.core.security import hash_token

MAIN_CONTRACTOR_AFFILIATION = "main_contractor"
CONSULTANT_AFFILIATION = "external_consultant"

# --- Moved here from app.api.auth to break the circular import ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if db.query(RevokedToken).filter(RevokedToken.token_hash == hash_token(token)).first():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_uuid).first()
    if user is None:
        raise credentials_exception

    if user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated or suspended",
        )

    if user.must_change_password:
        path = request.url.path.rstrip("/")
        method = request.method.upper()
        allowed_requests = (
            ("GET", "/auth/me"),
            ("GET", "/users/profile"),
            ("PUT", "/users/change-password"),
            ("POST", "/auth/logout"),
        )
        if not any(
            method == allowed_method and path.endswith(allowed_path)
            for allowed_method, allowed_path in allowed_requests
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="PASSWORD_CHANGE_REQUIRED",
            )

    return user


# `require_roles(*allowed_roles)` stood here and is gone: a dependency that
# admits a fixed list of role names is the shape this redesign removes, and it
# had no callers. Endpoints use `require_permission(code)` / `require(...)`.


# `require_admin` stood here and is gone. Its only callers were the two
# `/company/settings` endpoints, which now depend on
# `require_permission("org.manage_settings")` — the catalogue code that already
# described that surface. It became unused as a result of that swap rather than
# having been dead beforehand, and is removed here so the last role-derived
# dependency in this module does not sit waiting for a new caller.


def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Contact your administrator.",
        )
    return current_user


# `is_main_contractor_engineer`, `require_main_contractor_engineer`,
# `is_consultant_engineer` and `require_consultant_engineer` stood here and are
# gone. All four asked the same retired question — which side of the
# owner/contractor/consultant triangle somebody was on — from `User.role` plus
# the `engineer_affiliation` string. `app.services.work_scope` replaced what
# they were reaching for (what work you see, which disciplines narrow it, what
# responsibility you carry), and `rbac.is_external_participant` replaced the
# internal/external axis. Nothing had called any of them since; two were still
# imported by `app.api.projects`, which never used them.


# `require_can_create_user` stood here and is gone, for the same reason as the
# four above it: it asked `can_create_team_role(current_user.role, target_role)`
# — a decision made from the retired enum on both sides — and nothing used it.
# `app.api.users` imported the name without ever declaring it as a dependency,
# so the account-creation rule it appeared to enforce was never actually
# reached through this path. Creating a user is gated at the endpoint by
# `platform.manage_users`, which is the permission an office can administer.


def user_has_project_access(
    db: Session,
    user: User,
    project_id: uuid.UUID,
    *,
    require_management: bool = False,
) -> bool:
    # `can_view_all_projects_effective` resolves `platform.view_all_projects`
    # through the same role-default-then-override chain as every other
    # catalogue permission, so an unconfigured Administrator gets exactly the
    # old hardcoded `role == ADMIN` answer (it is the role's default) — but,
    # unlike the old hardcoded check this replaced, an explicit revoke now
    # actually restricts an administrator, and an explicit grant actually
    # widens a non-administrator. A plain `if can_view_all_projects(user.role):
    # return True` guard here would have made a revoke impossible no matter
    # what Access Control says, by always winning first.
    #
    # Deferred import: this module is imported by app.services.authorization
    # for `user_has_project_access` itself, so importing at module load time
    # here would be a circular import; by call time both modules are loaded.
    from app.services.authorization import can_view_all_projects_effective
    if can_view_all_projects_effective(db, user):
        return True

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    # There was an early return here for `role == UserRole.PROJECT_MANAGER`
    # that answered `project.project_manager_id == user.id` and **skipped the
    # membership check below**. It is gone, deliberately.
    #
    # It meant a project manager saw only the projects they managed: their
    # `ProjectMember` rows were ignored, so somebody added to another office
    # project as a discipline reviewer was locked out of it. That was coherent
    # while "Project Manager" was one of six fixed identities. It is not
    # coherent when the office defines its own roles — the job title carries no
    # such meaning, and an office that calls somebody a Project Manager has not
    # thereby said "and nothing else, anywhere".
    #
    # Everyone now falls through to the same union: owner, assigned manager, or
    # active member. Declared as `project_manager_membership_honoured` in
    # `app.db.rbac_equivalence`.
    if user.id == project.owner_id:
        return True

    if user.id == project.project_manager_id:
        return True

    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
            ProjectMember.is_active == True,
        )
        .first()
    )
    if membership:
        if require_management:
            # "May this member *run* the project", not "is their account one of
            # two enum values". `project.manage_members` is the capability the
            # office configures for exactly this, and the assigned manager
            # keeps it by virtue of the assignment.
            from app.services.authorization import has_permission
            return (
                user.id == project.project_manager_id
                or has_permission(db, user, "project.manage_members", project_id)
            )
        return True

    return False

def accessible_project_ids(db: Session, user: User) -> list[uuid.UUID] | None:
    """Return every project visible to the user, including direct owner/PM assignments.

    `None` means unrestricted. See `user_has_project_access` for why the
    `platform.view_all_projects` check below (a) is safe from recursion and
    (b) is the sole gate rather than an `or can_view_all_projects(role)` —
    the effective-permission check already reproduces the hardcoded
    role-only default, and an unconditional static OR would make a revoke
    impossible.
    """
    from app.services.authorization import can_view_all_projects_effective
    if can_view_all_projects_effective(db, user):
        return None
    # The same early return `user_has_project_access` carried, removed for the
    # same reason: it replaced the membership union with "projects I manage",
    # so a project manager's own memberships never counted. The union below is
    # now everyone's answer.
    member_ids = db.query(ProjectMember.project_id).filter(
        ProjectMember.user_id == user.id, ProjectMember.is_active == True
    )
    return [project_id for (project_id,) in db.query(Project.id).filter(or_(
        Project.id.in_(member_ids), Project.owner_id == user.id, Project.project_manager_id == user.id,
    )).all()]


def get_project_or_403(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project")
    return project


def get_manageable_project_or_403(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if is_admin(current_user.role):
        return project

    # The id comparison already implies the role: `project_manager_id` is
    # validated to be an active PROJECT_MANAGER wherever it is written.
    if current_user.id == project.project_manager_id:
        return project

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the assigned project manager or company administrator can manage this project",
    )


# `require_project_creation` and `require_project_member_management` stood here
# and are gone. Both resolved from `User.role`, and neither was ever declared as
# a dependency: `app.api.projects` imported the first without using it, and the
# second had no reference anywhere at all.
#
# The second is worth recording, because it was not merely unused — it was
# *wrong*. `can_manage_project_members(role)` answers True for any project
# manager on every project in the platform, while the permission that replaced
# it, `project.manage_members`, is project-scoped. Measured across the accounts
# in this database, the two disagreed on 21 (user, project) pairs, every one of
# them a project manager who would have been admitted to a project they have no
# part in. Nothing called it, so nothing was exposed; it is deleted rather than
# migrated so that the discrepancy cannot be reintroduced by a future caller
# reaching for a conveniently-named helper.
#
# Project creation is gated by `platform.create_project`, and membership
# management by `project.manage_members`, both through `require(...)`.
