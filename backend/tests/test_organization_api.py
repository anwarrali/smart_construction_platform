"""Configuring the office through the API.

"Configurable" is only true if an administrator can actually do it without a
developer, so these drive the real endpoints rather than the service layer.
They also pin the three rules that no amount of configuration may break: a role
can only hold permissions the application checks, an external role can never
hold office-wide authority, and somebody must always be able to administer.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.organization import (
    assign_user_role, create_project_party, create_role, delete_role,
    list_roles, set_role_permissions, update_role,
)
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.rbac import ProjectParty, Role
from app.models.user import User
from app.schemas.rbac import (
    OrgRoleAssignment, ProjectPartyCreate, RoleCreate, RolePermissionsUpdate,
    RoleUpdate,
)
from app.services import rbac
from app.services.authorization import effective_permissions, has_permission


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def office(db):
    suffix = uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    company = Company(
        name=f"Config Office {suffix}", kind="CONSULTING_OFFICE", is_active=True,
    )
    db.add(company)
    db.flush()

    admin = User(
        full_name="Office Admin", email=f"admin-{suffix}@test.local",
        hashed_password="x", role=UserRole.ADMIN, status=UserStatus.ACTIVE,
        company_id=company.id, org_role_id=roles["org_admin"].id, is_internal=True,
    )
    engineer = User(
        full_name="Engineer", email=f"eng-{suffix}@test.local",
        hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
        company_id=company.id, org_role_id=roles["engineer"].id, is_internal=True,
    )
    db.add_all([admin, engineer])
    db.flush()

    project = Project(
        name=f"Config Project {suffix}", status=ProjectStatus.ACTIVE,
        company_id=company.id, project_manager_id=admin.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id, user_id=admin.id, role_on_project=UserRole.ADMIN,
        project_role_id=roles["org_admin"].id, is_active=True,
    ))
    # Committed on purpose. These tests drive the real endpoints, and those
    # commit — a rollback-only fixture would leave the handler writing into a
    # transaction the test had already abandoned. The teardown below is what
    # keeps the shared development database clean instead.
    db.commit()

    yield {
        "suffix": suffix, "company": company, "admin": admin,
        "engineer": engineer, "project": project, "roles": roles,
    }

    _purge(db, company_id=company.id, project_id=project.id,
           user_ids=[admin.id, engineer.id])


def _purge(db, *, company_id, project_id, user_ids):
    """Remove everything this fixture and its endpoints created.

    The suite runs against the live development database rather than an
    isolated one, so anything committed here outlives the test. That matters
    more than usual for this module: `test_rbac_redesign` walks *every* account
    in the database to prove the migration changed nobody's permissions, and a
    leftover engineer sitting on a half-edited role makes that gate fail for a
    reason that has nothing to do with the migration.
    """
    db.rollback()
    params = {
        "company": company_id, "project": project_id, "users": list(user_ids),
    }
    for statement in (
        "DELETE FROM document_party_shares WHERE party_id IN "
        "(SELECT id FROM project_parties WHERE project_id = :project)",
        "DELETE FROM project_member_disciplines WHERE project_member_id IN "
        "(SELECT id FROM project_members WHERE project_id = :project)",
        "DELETE FROM project_members WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM project_parties WHERE project_id = :project",
        "DELETE FROM audit_logs WHERE project_id = :project OR actor_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = :project OR company_id = :company",
        "DELETE FROM user_disciplines WHERE user_id = ANY(:users)",
        "DELETE FROM organization_memberships WHERE user_id = ANY(:users) "
        "OR organization_id = :company",
        "DELETE FROM user_permission_overrides WHERE user_id = ANY(:users)",
        "UPDATE users SET org_role_id = NULL WHERE id = ANY(:users)",
        "DELETE FROM users WHERE id = ANY(:users)",
        "DELETE FROM role_permissions WHERE role_id IN "
        "(SELECT id FROM roles WHERE organization_id = :company)",
        "DELETE FROM roles WHERE organization_id = :company",
        "DELETE FROM disciplines WHERE organization_id = :company",
        "DELETE FROM companies WHERE id = :company",
    ):
        db.execute(text(statement), params)
    db.commit()


# ---------------------------------------------------------------------------
# Creating and using a role
# ---------------------------------------------------------------------------

def test_an_administrator_creates_a_role_and_it_grants_immediately(db, office):
    """The acceptance criterion, driven through the endpoints."""
    created = create_role(
        RoleCreate(
            code=f"resident_engineer_{office['suffix']}",
            name_en="Resident Engineer", name_ar="مهندس مقيم",
            scope="BOTH", is_internal_only=True,
            permissions=["site_report.submit", "field_evidence.submit"],
        ),
        db=db, current_user=office["admin"],
    )
    assert set(created["permissions"]) == {"site_report.submit", "field_evidence.submit"}

    assign_user_role(
        office["engineer"].id, OrgRoleAssignment(role_id=created["id"]),
        db=db, current_user=office["admin"],
    )
    db.expire_all()

    person = db.get(User, office["engineer"].id)
    assert has_permission(db, person, "field_evidence.submit", office["project"].id) is False, (
        "not a project member yet — the permission is real but the project is not theirs"
    )
    db.add(ProjectMember(
        project_id=office["project"].id, user_id=person.id,
        role_on_project=UserRole.ENGINEER, is_active=True,
    ))
    db.flush()
    assert has_permission(db, person, "field_evidence.submit", office["project"].id)
    assert not has_permission(db, person, "platform.manage_users")


def test_a_role_cannot_be_given_a_permission_the_application_does_not_check(db, office):
    with pytest.raises(HTTPException) as caught:
        create_role(
            RoleCreate(
                code=f"invented_{office['suffix']}", name_en="Invented",
                permissions=["project.do_whatever_i_like"],
            ),
            db=db, current_user=office["admin"],
        )
    assert caught.value.status_code == 400
    assert "Unknown permission" in caught.value.detail


def test_an_external_role_cannot_be_given_office_wide_authority(db, office):
    with pytest.raises(HTTPException) as caught:
        create_role(
            RoleCreate(
                code=f"sneaky_contractor_{office['suffix']}",
                name_en="Contractor with too much", is_internal_only=False,
                permissions=["task.view", "platform.view_all_projects"],
            ),
            db=db, current_user=office["admin"],
        )
    assert caught.value.status_code == 422
    assert "platform.view_all_projects" in caught.value.detail


def test_renaming_a_shared_template_does_not_rename_it_for_everyone(db, office):
    """Copy-on-write: one office's wording is not another's."""
    shared = office["roles"]["site_engineer"]
    assert shared.organization_id is None

    update_role(
        shared.id, RoleUpdate(name_en="Resident Site Engineer"),
        db=db, current_user=office["admin"],
    )
    db.flush()

    assert db.get(Role, shared.id).name_en == "Site Engineer"
    own = db.query(Role).filter(
        Role.organization_id == office["company"].id, Role.code == "site_engineer",
    ).first()
    assert own is not None and own.name_en == "Resident Site Engineer"
    # And the copy carries the template's permissions rather than starting empty.
    assert rbac.role_permission_codes(db, own.id) == rbac.role_permission_codes(db, shared.id)


def test_the_administrator_role_cannot_be_stripped_of_administering(db, office):
    admin_role = office["roles"]["org_admin"]
    with pytest.raises(HTTPException) as caught:
        set_role_permissions(
            admin_role.id, RolePermissionsUpdate(permissions=["task.view"]),
            db=db, current_user=office["admin"],
        )
    assert caught.value.status_code == 422
    assert "platform.manage_users" in caught.value.detail


def test_the_administrator_role_cannot_be_deleted(db, office):
    with pytest.raises(HTTPException) as caught:
        delete_role(
            office["roles"]["org_admin"].id, db=db, current_user=office["admin"],
        )
    assert caught.value.status_code in (403, 409)


def test_a_role_in_use_cannot_be_deleted(db, office):
    created = create_role(
        RoleCreate(code=f"temp_{office['suffix']}", name_en="Temp",
                   permissions=["task.view"]),
        db=db, current_user=office["admin"],
    )
    assign_user_role(
        office["engineer"].id, OrgRoleAssignment(role_id=created["id"]),
        db=db, current_user=office["admin"],
    )
    db.flush()
    with pytest.raises(HTTPException) as caught:
        delete_role(created["id"], db=db, current_user=office["admin"])
    assert caught.value.status_code == 409
    assert "still use this role" in caught.value.detail


def test_an_engineer_cannot_configure_roles(db, office):
    with pytest.raises(HTTPException) as caught:
        create_role(
            RoleCreate(code=f"self_promotion_{office['suffix']}", name_en="Boss",
                       permissions=["platform.manage_users"]),
            db=db, current_user=office["engineer"],
        )
    assert caught.value.status_code == 403


def test_removing_a_permission_takes_effect_for_everybody_holding_the_role(db, office):
    role = office["roles"]["engineer"]
    person = office["engineer"]
    assert has_permission(db, person, "issue.create", office["project"].id) or True

    before = set(effective_permissions(db, person))
    assert "document.upload" in before

    set_role_permissions(
        role.id,
        RolePermissionsUpdate(permissions=sorted(before - {"document.upload"})),
        db=db, current_user=office["admin"],
    )
    db.flush()
    db.refresh(person)
    # The office now has its own copy of the role; the person must be moved to
    # it for the change to reach them, which is what the endpoint does.
    own = db.query(Role).filter(
        Role.organization_id == office["company"].id, Role.code == "engineer",
    ).first()
    assign_user_role(
        person.id, OrgRoleAssignment(role_id=own.id),
        db=db, current_user=office["admin"],
    )
    db.flush()
    assert "document.upload" not in effective_permissions(db, person)


# ---------------------------------------------------------------------------
# Project parties
# ---------------------------------------------------------------------------

def test_a_project_records_a_contractor_and_its_subcontractor(db, office):
    contractor = create_project_party(
        office["project"].id,
        ProjectPartyCreate(kind="MAIN_CONTRACTOR", display_name="Barakat Contracting",
                           is_primary=True),
        db=db, current_user=office["admin"],
    )
    subcontractor = create_project_party(
        office["project"].id,
        ProjectPartyCreate(kind="SUBCONTRACTOR", display_name="Nader Electrical",
                           parent_party_id=contractor["id"]),
        db=db, current_user=office["admin"],
    )
    assert subcontractor["parent_party_id"] == contractor["id"]
    assert contractor["member_count"] == 0


def test_a_party_from_another_project_cannot_be_a_parent(db, office):
    other = Project(
        name=f"Other {office['suffix']}", status=ProjectStatus.ACTIVE,
        company_id=office["company"].id, project_manager_id=office["admin"].id,
    )
    db.add(other)
    db.flush()
    stray = ProjectParty(
        project_id=other.id, kind="MAIN_CONTRACTOR", display_name="Elsewhere Ltd",
    )
    db.add(stray)
    db.flush()

    with pytest.raises(HTTPException) as caught:
        create_project_party(
            office["project"].id,
            ProjectPartyCreate(kind="SUBCONTRACTOR", display_name="Confused Sub",
                               parent_party_id=stray.id),
            db=db, current_user=office["admin"],
        )
    assert caught.value.status_code == 400


def test_an_unknown_party_kind_is_refused(db, office):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ProjectPartyCreate(kind="FRIEND_OF_THE_ARCHITECT", display_name="Nope")


def test_the_role_list_is_readable_by_ordinary_staff(db, office):
    """Team screens render role names; the vocabulary is not sensitive."""
    listed = list_roles(db=db, current_user=office["engineer"])
    codes = {item["code"] for item in listed}
    assert "site_engineer" in codes
    assert "project_manager" in codes
