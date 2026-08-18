"""FastAPI dependencies for authentication and authorization."""

import uuid
from typing import Callable, Iterable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.permissions import (
    can_create_project,
    can_create_team_role,
    can_manage_all_users,
    can_manage_project_members,
    is_admin,
)
from app.core.security import decode_token
from app.db.database import get_db
from app.models.enums import UserRole, UserStatus
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


def require_roles(*allowed_roles: UserRole) -> Callable:
    """Require the current user to have one of the given roles."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return current_user

    return dependency


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not can_manage_all_users(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company administrator access required",
        )
    return current_user


def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Contact your administrator.",
        )
    return current_user


def is_main_contractor_engineer(user: User) -> bool:
    """Return whether a user is an active execution-side Engineer."""
    return (
        user.role == UserRole.ENGINEER
        and user.engineer_affiliation == MAIN_CONTRACTOR_AFFILIATION
        and user.status == UserStatus.ACTIVE
    )


def require_main_contractor_engineer(
    current_user: User = Depends(get_current_user),
) -> User:
    if not is_main_contractor_engineer(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active Main Contractor Engineer access required",
        )
    return current_user


def is_consultant_engineer(user: User) -> bool:
    """Return whether a user is an active supervision-side Engineer."""
    return (
        user.role == UserRole.ENGINEER
        and user.engineer_affiliation == CONSULTANT_AFFILIATION
        and user.status == UserStatus.ACTIVE
    )


def is_worker(user: User) -> bool:
    return user.role == UserRole.WORKER and user.status == UserStatus.ACTIVE


def require_consultant_engineer(
    current_user: User = Depends(get_current_user),
) -> User:
    if not is_consultant_engineer(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active Consultant Engineer access required",
        )
    return current_user


def require_can_create_user(
    target_role: UserRole,
    current_user: User = Depends(get_current_user),
) -> User:
    if not can_create_team_role(current_user.role, target_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are not authorized to create users with role '{target_role.value}'",
        )
    return current_user


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

    if user.role == UserRole.PROJECT_MANAGER:
        return project.project_manager_id == user.id

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
            return user.role in {UserRole.ADMIN, UserRole.PROJECT_MANAGER} or user.id == project.project_manager_id
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
    if user.role == UserRole.PROJECT_MANAGER:
        return [project_id for (project_id,) in db.query(Project.id).filter(
            Project.project_manager_id == user.id).all()]
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

    if current_user.role == UserRole.PROJECT_MANAGER and current_user.id == project.project_manager_id:
        return project

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the assigned project manager or company administrator can manage this project",
    )


def require_project_creation(current_user: User = Depends(get_current_user)) -> User:
    if not can_create_project(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to create projects",
        )
    return current_user


def require_project_member_management(current_user: User = Depends(get_current_user)) -> User:
    if not can_manage_project_members(current_user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage project members",
        )
    return current_user
