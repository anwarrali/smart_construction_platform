"""Administrator-facing access control.

Every endpoint here is itself gated on `platform.manage_permissions`, which only
an administrator holds and which cannot be revoked from an administrator, so the
access-control surface cannot be used to lock the platform out of itself.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permission_catalogue import BY_CODE, CATALOGUE
from app.db.database import get_db
from app.models.enums import UserStatus
from app.models.permission import ConsultantEngineerScope, UserPermissionOverride
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember
from app.models.rbac import Role
from app.models.user import User
from app.schemas.permission import (
    ConsultantScopeOut, ConsultantScopeUpdate, PermissionOut, UserPermissionSummary,
    UserPermissionUpdate,
)
from app.services import rbac
from app.services.audit_service import record_audit
from app.services.step_up_service import require_step_up
from app.services.authorization import effective_permissions, has_permission, require

router = APIRouter(prefix="/access-control", tags=["Access Control"])

MANAGE = "platform.manage_permissions"


def _gate(db: Session, user: User) -> None:
    require(db, user, MANAGE)


def _permission(code: str):
    item = BY_CODE.get(code)
    if not item:
        raise HTTPException(status_code=400, detail="Unknown permission")
    return item


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The catalogue itself, so the administrator sees real capabilities."""
    _gate(db, current_user)
    return [{
        "code": item.code, "group": item.group, "label": item.label,
        "description": item.description,
        "project_scoped": item.project_scoped, "admin_locked": item.admin_locked,
        "office_only": item.office_only, "never_external": item.never_external,
    } for item in CATALOGUE]


# `GET` / `PUT /access-control/roles` stood here: a matrix of the retired
# six-value enum against the catalogue, stored in `role_permission_overrides`.
# What a role may do is now edited on the role itself —
# `PUT /organization/roles/{id}/permissions` — and that table is gone.


@router.get("/users/{user_id}", response_model=UserPermissionSummary)
def user_permissions(user_id: uuid.UUID, project_id: uuid.UUID | None = Query(default=None),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """What one person can actually do, optionally within one project."""
    _gate(db, current_user)
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    overrides = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user_id).all()
    return {
        "user_id": target.id, "full_name": target.full_name, "email": target.email,
        "role_code": target.org_role.code if target.org_role else None,
        "role_name": target.org_role.name_en if target.org_role else None,
        "status": target.status.value, "project_id": project_id,
        "effective_permissions": sorted(effective_permissions(db, target, project_id)),
        "overrides": overrides,
    }


@router.put("/users/{user_id}", response_model=UserPermissionSummary)
def set_user_permission(user_id: uuid.UUID, payload: UserPermissionUpdate,
                        db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _gate(db, current_user)
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    item = _permission(payload.permission_code)

    if payload.project_id is not None:
        if not item.project_scoped:
            raise HTTPException(status_code=400, detail="This permission is not project-scoped")
        if not db.get(Project, payload.project_id):
            raise HTTPException(status_code=404, detail="Project not found")

    # The wall, enforced where the mistake would be made rather than only where
    # it would take effect. `effective_permissions` strips these again at
    # resolution, so refusing here is a second line — but it is the line that
    # tells the administrator *why*, instead of silently accepting a grant that
    # will never do anything.
    if (
        payload.allowed
        and item.never_external
        and rbac.is_external_participant(db, target, payload.project_id)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{item.label}' is the consulting office's own authority and cannot "
                "be granted to somebody taking part for an outside party. Office work "
                "such as raising tasks or maintaining the programme can be delegated; "
                "approving work, verifying reports and granting access cannot."
            ),
        )

    # The office administrator is whoever holds the undeletable office role —
    # the same test `effective_permissions` uses to restore these codes, so
    # refusing here only tells the administrator what would happen anyway.
    if item.admin_locked and payload.allowed is False and rbac.holds_office_admin_role(db, target):
        raise HTTPException(
            status_code=409,
            detail="This permission keeps the platform administrable and cannot be removed from an administrator",
        )

    # See `set_role_permission`: validate first, challenge second.
    require_step_up(db, current_user, "admin.change_permissions")

    row = db.query(UserPermissionOverride).filter(
        UserPermissionOverride.user_id == user_id,
        UserPermissionOverride.permission_code == item.code,
        UserPermissionOverride.project_id.is_(None) if payload.project_id is None
        else UserPermissionOverride.project_id == payload.project_id,
    ).first()

    if payload.allowed is None:
        if row:
            db.delete(row)
    elif row:
        row.allowed = payload.allowed
        row.reason = payload.reason
        row.updated_by_id = current_user.id
    else:
        db.add(UserPermissionOverride(
            user_id=user_id, project_id=payload.project_id, permission_code=item.code,
            allowed=payload.allowed, reason=payload.reason, updated_by_id=current_user.id,
        ))

    record_audit(db, actor_id=current_user.id, action="user_permission_changed",
                 entity_type="user_permission", entity_id=user_id, project_id=payload.project_id,
                 details={"permission": item.code, "allowed": payload.allowed,
                          "projectId": str(payload.project_id) if payload.project_id else None})
    db.commit()
    db.refresh(target)
    return user_permissions(user_id, payload.project_id, db, current_user)


def _project_reviewer_ids(db: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    """The office's reviewers on this project: active members holding `task.review`.

    Was `role_on_project == CONSULTANT`. Reviewing work is a permission the
    office's own roles hold, so the question is asked of the permission.
    """
    members = db.query(ProjectMember).join(User, User.id == ProjectMember.user_id).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True,  # noqa: E712
    ).order_by(User.full_name).all()
    return [
        member.user_id for member in members
        if has_permission(db, member.user, "task.review", project_id)
    ]


@router.get("/projects/{project_id}/consultants", response_model=list[ConsultantScopeOut])
def project_consultants(project_id: uuid.UUID, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Each consultant on the project with their discipline and engineer scope.

    A project may legitimately have several consultants with different remits;
    nothing here assumes there is only one.
    """
    _gate(db, current_user)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    consultant_ids = _project_reviewer_ids(db, project_id)
    assignments = db.query(ProjectConsultantReviewer).filter(
        ProjectConsultantReviewer.project_id == project_id).all()
    scopes = db.query(ConsultantEngineerScope).filter(
        ConsultantEngineerScope.project_id == project_id).all()
    users = {row.id: row for row in db.query(User).filter(User.id.in_(consultant_ids)).all()} if consultant_ids else {}

    return [{
        "project_id": project_id,
        "consultant_user_id": consultant_id,
        "consultant_name": users[consultant_id].full_name if consultant_id in users else "",
        "approval_mode": project.consultant_approval_mode.value,
        "disciplines": [item.discipline for item in assignments if item.user_id == consultant_id],
        "engineer_user_ids": [item.engineer_user_id for item in scopes if item.consultant_user_id == consultant_id],
    } for consultant_id in consultant_ids]


@router.put("/projects/{project_id}/consultants", response_model=ConsultantScopeOut)
def set_consultant_engineer_scope(project_id: uuid.UUID, payload: ConsultantScopeUpdate,
                                  db: Session = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Replace the set of engineers a consultant reviews on this project."""
    _gate(db, current_user)
    if payload.project_id != project_id:
        raise HTTPException(status_code=400, detail="Project mismatch")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.consultant_user_id not in _project_reviewer_ids(db, project_id):
        raise HTTPException(status_code=400, detail="That person is not an active consultant on this project")

    member_ids = {
        row.user_id for row in db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.is_active == True,  # noqa: E712
        ).all()
    }
    wanted = set(payload.engineer_user_ids)
    if not wanted.issubset(member_ids):
        raise HTTPException(status_code=400, detail="Every engineer must be an active member of this project")

    db.query(ConsultantEngineerScope).filter(
        ConsultantEngineerScope.project_id == project_id,
        ConsultantEngineerScope.consultant_user_id == payload.consultant_user_id,
    ).delete(synchronize_session=False)
    for engineer_id in wanted:
        db.add(ConsultantEngineerScope(
            project_id=project_id, consultant_user_id=payload.consultant_user_id,
            engineer_user_id=engineer_id, assigned_by_id=current_user.id,
        ))

    record_audit(db, actor_id=current_user.id, action="consultant_scope_changed",
                 entity_type="consultant_scope", entity_id=payload.consultant_user_id,
                 project_id=project_id, details={"engineerIds": [str(x) for x in wanted]})
    db.commit()

    assignments = db.query(ProjectConsultantReviewer).filter(
        ProjectConsultantReviewer.project_id == project_id,
        ProjectConsultantReviewer.user_id == payload.consultant_user_id).all()
    consultant = db.get(User, payload.consultant_user_id)
    return {
        "project_id": project_id, "consultant_user_id": payload.consultant_user_id,
        "consultant_name": consultant.full_name if consultant else "",
        "approval_mode": project.consultant_approval_mode.value,
        "disciplines": [item.discipline for item in assignments],
        "engineer_user_ids": sorted(wanted),
    }


@router.get("/me", response_model=list[str])
def my_permissions(project_id: uuid.UUID | None = Query(default=None),
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """What the caller can do. Used by the UI to hide what it should not offer.

    This is a convenience for presentation only — every protected operation is
    checked again on the server when it is actually attempted.
    """
    return sorted(effective_permissions(db, current_user, project_id))
