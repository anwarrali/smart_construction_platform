"""Configuring the office: roles, disciplines and each project's parties.

This is the surface that makes "configurable" true rather than aspirational. An
office administrator creates a role here, decides what it may do, and assigns
people to it — with no deployment and no migration, which is the whole point of
moving roles out of an enum.

Three rules are enforced on every write, and none of them can be configured
away:

  * **Permissions come from the catalogue.** A role may be given any permission
    the application actually checks, and nothing else. Inventing a permission
    would produce a role that grants something no code reads — a promise the
    platform cannot keep.
  * **An external role cannot hold office-wide authority.** Anything not
    project-scoped is refused at grant time, and stripped again at resolution
    time by `app.services.rbac`, so a mistake here cannot become a breach.
  * **Somebody must always be able to administer.** The office administrator
    role cannot be deleted, and its locked permissions cannot be removed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permission_catalogue import BY_CODE
from app.db.database import get_db
from app.models.company import Company
from app.models.enums import UserRole
from app.models.project import Project, ProjectMember
from app.models.rbac import Discipline, ProjectParty, Role, RolePermission
from app.models.user import User
from app.schemas.rbac import (
    DisciplineCreate, DisciplineOut, DisciplineUpdate, OrgRoleAssignment,
    ProjectPartyCreate, ProjectPartyOut, ProjectPartyUpdate,
    RoleCreate, RoleOut, RolePermissionsUpdate, RoleUpdate,
    UserDisciplinesUpdate,
)
from app.services import rbac
from app.services.audit_service import record_audit
from app.services.authorization import manageable_project, require

router = APIRouter(prefix="/organization", tags=["Organization"])

MANAGE_ROLES = "org.manage_roles"
MANAGE_DISCIPLINES = "org.manage_disciplines"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _office(db: Session, user: User) -> Company:
    """The office whose configuration this person is editing."""
    if user.company_id:
        company = db.get(Company, user.company_id)
        if company is not None:
            return company
    return rbac.ensure_tenant_organization(db)


def _visible_roles(db: Session, organization_id: uuid.UUID):
    """The office's own roles, plus the shared templates it has not replaced."""
    own = db.query(Role).filter(Role.organization_id == organization_id).all()
    own_codes = {role.code for role in own}
    shared = [
        role for role in db.query(Role).filter(Role.organization_id.is_(None)).all()
        if role.code not in own_codes
    ]
    return sorted(own + shared, key=lambda role: (role.rank, role.name_en))


def _member_count(db: Session, role_id: uuid.UUID) -> int:
    users = db.query(User).filter(User.org_role_id == role_id).count()
    members = db.query(ProjectMember).filter(
        ProjectMember.project_role_id == role_id, ProjectMember.is_active.is_(True),
    ).count()
    return users + members


def _role_payload(db: Session, role: Role, *, with_permissions: bool = True) -> dict:
    return {
        "id": role.id, "code": role.code, "name_en": role.name_en,
        "name_ar": role.name_ar, "description": role.description,
        "scope": role.scope, "is_internal_only": role.is_internal_only,
        "is_system": role.is_system, "undeletable": role.undeletable,
        "rank": role.rank, "is_active": role.is_active,
        "permissions": sorted(rbac.role_permission_codes(db, role.id)) if with_permissions else [],
        "member_count": _member_count(db, role.id),
    }


def _validated_permissions(codes: list[str], *, is_internal_only: bool) -> set[str]:
    unknown = [code for code in codes if code not in BY_CODE]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown permission(s): {', '.join(sorted(unknown))}",
        )
    chosen = set(codes)
    if not is_internal_only:
        offending = chosen & rbac.NON_PROJECT_SCOPED
        if offending:
            raise HTTPException(
                status_code=422,
                detail=(
                    "A role for people outside the office cannot hold office-wide "
                    f"permissions: {', '.join(sorted(offending))}"
                ),
            )
        # A *role* is inheritance, and inheritance is where a mistake is
        # silent: everybody who ever holds this role gets whatever is in it,
        # including people added long after the decision was made. So the whole
        # `office_only` set is refused here, not just the locked subset.
        #
        # Delegating one of the four delegable codes to an outside firm is
        # still possible — through Access Control, for one named person on one
        # named project, which is a decision somebody makes and signs. That is
        # the difference the two ceilings exist to draw.
        office_work = chosen & rbac.OFFICE_ONLY
        if office_work:
            raise HTTPException(
                status_code=422,
                detail=(
                    "A role for people outside the office cannot carry the office's "
                    f"own authority: {', '.join(sorted(office_work))}. Grant it to a "
                    "specific person on a specific project in Access Control instead."
                ),
            )
    return chosen


def _editable_role(db: Session, role_id: uuid.UUID, organization_id: uuid.UUID) -> Role:
    """A role this office may change.

    A shared template is copied into the office on first edit rather than
    modified in place, so one office renaming "Site Engineer" cannot rename it
    for another. The copy keeps the code, which is what everything else refers
    to it by.
    """
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.organization_id == organization_id:
        return role
    if role.organization_id is not None:
        raise HTTPException(status_code=403, detail="This role belongs to another office")

    copy = Role(
        organization_id=organization_id, code=role.code, name_en=role.name_en,
        name_ar=role.name_ar, description=role.description, scope=role.scope,
        is_internal_only=role.is_internal_only, is_system=role.is_system,
        undeletable=role.undeletable, rank=role.rank,
        # Carried over, not re-derived: an office copying "Site Engineer" must
        # keep provisioning the same kind of account it did before the copy.
        legacy_role=role.legacy_role, legacy_affiliation=role.legacy_affiliation,
    )
    db.add(copy)
    db.flush()
    for code in rbac.role_permission_codes(db, role.id):
        db.add(RolePermission(role_id=copy.id, permission_code=code, allowed=True))
    db.flush()
    return copy


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Every role this office can assign.

    Readable by anyone signed in: the frontend renders role names on team
    screens and needs the vocabulary, which is not sensitive. Editing is gated.
    """
    office = _office(db, current_user)
    return [_role_payload(db, role) for role in _visible_roles(db, office.id)]


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, MANAGE_ROLES)
    office = _office(db, current_user)

    clash = db.query(Role).filter(
        Role.organization_id == office.id, Role.code == data.code
    ).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail="A role with this code already exists")

    permissions = _validated_permissions(
        data.permissions, is_internal_only=data.is_internal_only
    )
    role = Role(
        organization_id=office.id, code=data.code, name_en=data.name_en,
        name_ar=data.name_ar, description=data.description, scope=data.scope,
        is_internal_only=data.is_internal_only, rank=data.rank, is_system=False,
        # A role the office invented has no legacy ancestor, so accounts
        # created under it are written as ENGINEER — the least-privileged
        # legacy value that still resolves. It is a placeholder for a column
        # the contract migration deletes, and it grants nothing: what the role
        # may actually do is `permissions` above.
        legacy_role=UserRole.ENGINEER.name,
    )
    db.add(role)
    db.flush()
    for code in permissions:
        db.add(RolePermission(role_id=role.id, permission_code=code, allowed=True))
    record_audit(
        db, actor_id=current_user.id, action="role_created", entity_type="role",
        entity_id=role.id,
        details={"code": role.code, "permissions": sorted(permissions)},
    )
    db.commit()
    db.refresh(role)
    return _role_payload(db, role)


@router.patch("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: uuid.UUID,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, MANAGE_ROLES)
    office = _office(db, current_user)
    role = _editable_role(db, role_id, office.id)

    if data.is_internal_only is False and role.is_internal_only:
        # Turning an internal role into an external one can only be safe if it
        # is not carrying office-wide authority.
        _validated_permissions(
            sorted(rbac.role_permission_codes(db, role.id)), is_internal_only=False
        )
    for field in ("name_en", "name_ar", "description", "scope", "is_internal_only",
                  "rank", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(role, field, value)
    record_audit(
        db, actor_id=current_user.id, action="role_updated", entity_type="role",
        entity_id=role.id, details={"code": role.code},
    )
    db.commit()
    db.refresh(role)
    return _role_payload(db, role)


@router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def set_role_permissions(
    role_id: uuid.UUID,
    data: RolePermissionsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, MANAGE_ROLES)
    office = _office(db, current_user)
    role = _editable_role(db, role_id, office.id)

    chosen = _validated_permissions(
        data.permissions, is_internal_only=role.is_internal_only
    )
    if role.undeletable:
        # The administrator role keeps what makes it an administrator. Resolution
        # re-adds these anyway; refusing here means the UI shows the truth
        # rather than accepting a change that silently does not take.
        missing = rbac.ADMIN_LOCKED - chosen
        if missing:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The office administrator role must keep: "
                    + ", ".join(sorted(missing))
                ),
            )

    before = rbac.role_permission_codes(db, role.id)
    for code in before - chosen:
        rbac.set_role_permission(db, role=role, code=code, allowed=None)
    for code in chosen - before:
        rbac.set_role_permission(db, role=role, code=code, allowed=True)
    record_audit(
        db, actor_id=current_user.id, action="role_permissions_changed",
        entity_type="role", entity_id=role.id,
        details={
            "code": role.code,
            "granted": sorted(chosen - before),
            "revoked": sorted(before - chosen),
        },
    )
    db.commit()
    db.refresh(role)
    return _role_payload(db, role)


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, MANAGE_ROLES)
    office = _office(db, current_user)
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.organization_id != office.id:
        raise HTTPException(
            status_code=403,
            detail="Shared role templates cannot be deleted. Deactivate it instead.",
        )
    if role.undeletable:
        raise HTTPException(
            status_code=409,
            detail="The office administrator role cannot be deleted",
        )
    held = _member_count(db, role.id)
    if held:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{held} assignment(s) still use this role. Move those people to "
                "another role first."
            ),
        )
    record_audit(
        db, actor_id=current_user.id, action="role_deleted", entity_type="role",
        entity_id=role.id, details={"code": role.code},
    )
    db.delete(role)
    db.commit()
    return {"message": "Role deleted"}


@router.put("/users/{user_id}/role", response_model=RoleOut)
def assign_user_role(
    user_id: uuid.UUID,
    data: OrgRoleAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, "platform.manage_users")
    office = _office(db, current_user)
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="User not found")
    role = db.get(Role, data.role_id)
    if role is None or (role.organization_id not in (None, office.id)):
        raise HTTPException(status_code=404, detail="Role not found")
    if role.scope == "PROJECT":
        raise HTTPException(
            status_code=422,
            detail="This role can only be given to somebody on a project",
        )
    rbac.assign_org_role(
        db, user=person, role=role, organization_id=person.company_id or office.id,
        job_title=data.job_title,
    )
    record_audit(
        db, actor_id=current_user.id, action="user_role_assigned", entity_type="user",
        entity_id=person.id, details={"role": role.code},
    )
    db.commit()
    db.refresh(role)
    return _role_payload(db, role)


@router.put("/users/{user_id}/disciplines")
def set_user_disciplines(
    user_id: uuid.UUID,
    data: UserDisciplinesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, "platform.manage_users")
    person = db.get(User, user_id)
    if person is None:
        raise HTTPException(status_code=404, detail="User not found")
    known = {
        row.id for row in db.query(Discipline).filter(
            Discipline.id.in_(data.discipline_ids)
        ).all()
    } if data.discipline_ids else set()
    if known != set(data.discipline_ids):
        raise HTTPException(status_code=400, detail="Unknown discipline")
    rbac.set_user_disciplines(
        db, user=person, discipline_ids=list(data.discipline_ids),
        primary_id=data.primary_discipline_id,
    )
    db.commit()
    return {
        "disciplines": [
            item.code for item in rbac.disciplines_for_user(db, person.id)
        ]
    }


# ---------------------------------------------------------------------------
# Disciplines
# ---------------------------------------------------------------------------

@router.get("/disciplines", response_model=list[DisciplineOut])
def list_disciplines(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    office = _office(db, current_user)
    own = db.query(Discipline).filter(Discipline.organization_id == office.id).all()
    own_codes = {item.code for item in own}
    shared = [
        item for item in db.query(Discipline).filter(
            Discipline.organization_id.is_(None)
        ).all()
        if item.code not in own_codes
    ]
    return sorted(own + shared, key=lambda item: (item.rank, item.name_en))


@router.post("/disciplines", response_model=DisciplineOut, status_code=201)
def create_discipline(
    data: DisciplineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, MANAGE_DISCIPLINES)
    office = _office(db, current_user)
    clash = db.query(Discipline).filter(
        Discipline.organization_id == office.id, Discipline.code == data.code
    ).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail="A discipline with this code already exists")
    discipline = Discipline(
        organization_id=office.id, code=data.code, name_en=data.name_en,
        name_ar=data.name_ar,
        ifc_disciplines=[value.upper() for value in data.ifc_disciplines],
        rank=data.rank,
    )
    db.add(discipline)
    db.commit()
    db.refresh(discipline)
    return discipline


@router.patch("/disciplines/{discipline_id}", response_model=DisciplineOut)
def update_discipline(
    discipline_id: uuid.UUID,
    data: DisciplineUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require(db, current_user, MANAGE_DISCIPLINES)
    office = _office(db, current_user)
    discipline = db.get(Discipline, discipline_id)
    if discipline is None:
        raise HTTPException(status_code=404, detail="Discipline not found")
    if discipline.organization_id not in (None, office.id):
        raise HTTPException(status_code=403, detail="This discipline belongs to another office")
    if discipline.organization_id is None:
        # Same copy-on-write rule as roles: renaming a shared discipline must
        # not rename it for every office.
        discipline = Discipline(
            organization_id=office.id, code=discipline.code,
            name_en=discipline.name_en, name_ar=discipline.name_ar,
            ifc_disciplines=list(discipline.ifc_disciplines or []),
            legacy_code=discipline.legacy_code, rank=discipline.rank,
        )
        db.add(discipline)
        db.flush()
    for field in ("name_en", "name_ar", "rank", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(discipline, field, value)
    if data.ifc_disciplines is not None:
        discipline.ifc_disciplines = [value.upper() for value in data.ifc_disciplines]
    db.commit()
    db.refresh(discipline)
    return discipline


# ---------------------------------------------------------------------------
# Project parties
# ---------------------------------------------------------------------------

parties_router = APIRouter(prefix="/projects", tags=["Project parties"])


def _party_payload(db: Session, party: ProjectParty) -> dict:
    return {
        "id": party.id, "project_id": party.project_id, "kind": party.kind,
        "display_name": party.display_name, "parent_party_id": party.parent_party_id,
        "is_primary": party.is_primary, "contact_name": party.contact_name,
        "contact_email": party.contact_email, "contact_phone": party.contact_phone,
        "notes": party.notes, "is_active": party.is_active,
        "member_count": db.query(ProjectMember).filter(
            ProjectMember.party_id == party.id, ProjectMember.is_active.is_(True),
        ).count(),
    }


@router.get("/party-kinds")
def list_party_kinds():
    """The relationships a project can record. Small and closed on purpose."""
    from app.core.role_templates import PARTY_KINDS
    return {"kinds": list(PARTY_KINDS)}


@parties_router.get("/{project_id}/parties", response_model=list[ProjectPartyOut])
def list_project_parties(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.deps import user_has_project_access

    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    parties = db.query(ProjectParty).filter(
        ProjectParty.project_id == project_id
    ).order_by(ProjectParty.kind, ProjectParty.display_name).all()
    return [_party_payload(db, party) for party in parties]


@parties_router.post("/{project_id}/parties", response_model=ProjectPartyOut, status_code=201)
def create_project_party(
    project_id: uuid.UUID,
    data: ProjectPartyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manageable_project(db, current_user, project_id, "project.manage_parties")
    if data.parent_party_id is not None:
        parent = db.get(ProjectParty, data.parent_party_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(status_code=400, detail="The parent party is not on this project")
    clash = db.query(ProjectParty).filter(
        ProjectParty.project_id == project_id,
        ProjectParty.kind == data.kind,
        ProjectParty.display_name == data.display_name,
    ).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail="This party is already recorded")

    party = ProjectParty(
        project_id=project_id, kind=data.kind, display_name=data.display_name,
        parent_party_id=data.parent_party_id, is_primary=data.is_primary,
        contact_name=data.contact_name, contact_email=data.contact_email,
        contact_phone=data.contact_phone, notes=data.notes,
        created_by_id=current_user.id,
    )
    db.add(party)
    record_audit(
        db, actor_id=current_user.id, action="project_party_added",
        entity_type="project_party", entity_id=party.id, project_id=project_id,
        details={"kind": party.kind, "name": party.display_name},
    )
    db.commit()
    db.refresh(party)
    return _party_payload(db, party)


@parties_router.patch("/{project_id}/parties/{party_id}", response_model=ProjectPartyOut)
def update_project_party(
    project_id: uuid.UUID,
    party_id: uuid.UUID,
    data: ProjectPartyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manageable_project(db, current_user, project_id, "project.manage_parties")
    party = db.get(ProjectParty, party_id)
    if party is None or party.project_id != project_id:
        raise HTTPException(status_code=404, detail="Party not found on this project")
    if data.parent_party_id is not None:
        if data.parent_party_id == party.id:
            raise HTTPException(status_code=400, detail="A party cannot report to itself")
        parent = db.get(ProjectParty, data.parent_party_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(status_code=400, detail="The parent party is not on this project")
    for field in ("display_name", "parent_party_id", "is_primary", "contact_name",
                  "contact_email", "contact_phone", "notes", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(party, field, value)
    db.commit()
    db.refresh(party)
    return _party_payload(db, party)


@parties_router.delete("/{project_id}/parties/{party_id}")
def delete_project_party(
    project_id: uuid.UUID,
    party_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manageable_project(db, current_user, project_id, "project.manage_parties")
    party = db.get(ProjectParty, party_id)
    if party is None or party.project_id != project_id:
        raise HTTPException(status_code=404, detail="Party not found on this project")
    attached = db.query(ProjectMember).filter(
        ProjectMember.party_id == party.id, ProjectMember.is_active.is_(True),
    ).count()
    if attached:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{attached} person(s) are on this project for {party.display_name}. "
                "Remove them from the project first."
            ),
        )
    record_audit(
        db, actor_id=current_user.id, action="project_party_removed",
        entity_type="project_party", entity_id=party.id, project_id=project_id,
        details={"kind": party.kind, "name": party.display_name},
    )
    db.delete(party)
    db.commit()
    return {"message": "Party removed"}
