"""Accounts are created under the office's own roles, not a fixed enum.

The redesign's claim is that an office can describe its own staff — General
Manager, Senior Structural Engineer, Surveyor, Site Engineer, or whatever it
decided to call them — without a code change. That claim is only worth
something if *provisioning* speaks the same vocabulary, which is what this
suite checks:

  * an account is created under a configured role, and holds that role's
    permissions from its first request;
  * disciplines are many-to-many, so an office that combines Mechanical and
    Electrical is representable;
  * the role decides internal vs external, and the office-authority ceiling
    still holds for an account created as external;
  * a role the office invented provisions an account holding exactly that
    role's permissions — nothing borrowed from a retired role;
  * no account can be provisioned under an archived role, and none can exist
    without an office role at all.

Everything runs in one transaction against the real database and is rolled
back. `create_provisioned_user` commits internally, so the two tests that call
it clean up the row they created explicitly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.role_templates import BY_CODE_TEMPLATE, OFFICE_ADMINISTRATION, TEMPLATES
from app.db.database import SessionLocal
from app.models.enums import UserStatus
from app.models.rbac import Discipline, Role, RolePermission
from app.models.user import User
from app.services import rbac
from app.services.authorization import effective_permissions
from app.services.user_service import create_provisioned_user


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
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    organization = rbac.ensure_tenant_organization(db)
    admin = User(
        full_name="ProvAdmin", email=f"provadmin-{uuid4().hex[:8]}@example.com",
        hashed_password="x", status=UserStatus.ACTIVE,
        company_id=organization.id, org_role_id=roles["org_admin"].id, is_internal=True,
    )
    db.add(admin)
    db.flush()
    disciplines = {
        row.code: row for row in
        db.query(Discipline).filter(Discipline.organization_id.is_(None)).all()
    }
    yield {"roles": roles, "organization": organization, "admin": admin,
           "disciplines": disciplines}
    # `create_provisioned_user` commits, which commits this fixture's own admin
    # along with it — so the rollback in the `db` fixture cannot take it back.
    # Removing it explicitly is what keeps the shared development database at
    # the same row count a run started with.
    _purge(db, admin.email)


def _purge(db, email: str) -> None:
    """Remove a row `create_provisioned_user` committed out from under the fixture."""
    db.rollback()
    for statement in (
        "DELETE FROM user_disciplines WHERE user_id IN (SELECT id FROM users WHERE email = :email)",
        "DELETE FROM organization_memberships WHERE user_id IN (SELECT id FROM users WHERE email = :email)",
        "DELETE FROM engineer_profiles WHERE user_id IN (SELECT id FROM users WHERE email = :email)",
        "DELETE FROM users WHERE email = :email",
    ):
        db.execute(text(statement), {"email": email})
    db.commit()


# --- the templates -----------------------------------------------------------

def test_only_the_archive_template_is_archived():
    """One template refuses provisioning, and it is the right one."""
    archived = {template.code for template in TEMPLATES if template.is_archived}
    assert archived == {"archived_field_staff"}


def test_technical_director_withholds_administration_explicitly():
    """It starts from office administration and declines account and permission
    administration, and project deletion, by naming them — not by being written
    as some other kind of account."""
    template = BY_CODE_TEMPLATE["technical_director"]
    assert template.base is OFFICE_ADMINISTRATION
    granted = template.permissions()
    for code in ("platform.manage_users", "platform.manage_permissions", "project.delete"):
        assert code not in granted, code


# --- creating under a configured role ---------------------------------------

def test_an_account_is_created_under_a_configured_role(db, office):
    """The role is the input; everything the retired fields carried follows."""
    email = f"surveyor-{uuid4().hex[:8]}@example.com"
    try:
        person, _ = create_provisioned_user(
            db, creator=office["admin"], email=email, full_name="Configured Surveyor",
            org_role=office["roles"]["surveyor"],
            discipline_ids=[
                office["disciplines"]["mechanical"].id,
                office["disciplines"]["electrical"].id,
            ],
            password="Str0ngPassw0rd!",
            send_email=False,
        )

        assert person.org_role_id == office["roles"]["surveyor"].id
        assert person.is_internal is True
        # One engineer, two disciplines — the case `EngineerProfile.discipline`
        # could not express and the brief names explicitly.
        assert {item.code for item in person.disciplines} == {"mechanical", "electrical"}

        granted = effective_permissions(db, person)
        assert "field_evidence.submit" in granted, "a surveyor records site evidence"
        assert "task.review" not in granted, "the template withholds review authority"
        assert "platform.manage_users" not in granted

        # The office role is the whole of the account's authority: there is no
        # retired role column left to write.
        assert "role" not in User.__table__.columns
        assert "engineer_affiliation" not in User.__table__.columns
    finally:
        _purge(db, email)


def test_an_external_role_creates_an_external_account(db, office):
    """A contractor's representative is not office staff, and cannot become it."""
    email = f"contractor-{uuid4().hex[:8]}@example.com"
    try:
        person, _ = create_provisioned_user(
            db, creator=office["admin"], email=email, full_name="Contractor Rep",
            org_role=office["roles"]["contractor_representative"],
            organization="Some Contracting Co",
            password="Str0ngPassw0rd!", send_email=False,
        )
        assert person.is_internal is False
        assert rbac.is_external_participant(db, person, None) is True

        granted = effective_permissions(db, person)
        # The office-authority ceiling, applied at resolution rather than at
        # the endpoint, so no role configuration can lift it.
        for code in ("task.review", "design_change.approve", "field_evidence.verify",
                     "project.manage_members", "platform.manage_users"):
            assert code not in granted, f"{code} is the office's own authority"
    finally:
        _purge(db, email)


# --- archived roles stay unreachable -------------------------------------------

def test_no_account_can_be_provisioned_under_the_archived_role(db, office):
    """The archive template refuses, loudly."""
    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=office["admin"],
            email=f"never-{uuid4().hex[:8]}@example.com", full_name="Never",
            org_role=office["roles"]["archived_field_staff"],
            password="Str0ngPassw0rd!", send_email=False,
        )


# --- an office role the office invented --------------------------------------

def test_a_role_the_office_invented_provisions_exactly_its_own_permissions(db, office):
    """The point of the whole exercise: a role that is in no template.

    "Resident Engineer" matches no retired role. An account created under it
    holds what the office gave the role — no more, nothing inherited from a
    legacy value — and only that role decides it.
    """
    code = f"resident_engineer_{uuid4().hex[:6]}"
    email = f"resident-{uuid4().hex[:8]}@example.com"
    role = Role(
        organization_id=office["organization"].id, code=code,
        name_en="Resident Engineer", scope="BOTH", is_internal_only=True,
        is_system=False, rank=75,
    )
    db.add(role)
    db.flush()
    granted_to_role = {"task.view", "task.update_progress", "site_report.submit", "field_evidence.submit"}
    for permission in granted_to_role:
        db.add(RolePermission(role_id=role.id, permission_code=permission, allowed=True))
    db.flush()
    role_id = role.id
    try:
        person, _ = create_provisioned_user(
            db, creator=office["admin"], email=email, full_name="Resident",
            org_role=role, password="Str0ngPassw0rd!", send_email=False,
        )
        assert person.org_role_id == role_id
        assert person.is_internal is True
        assert effective_permissions(db, person) == granted_to_role
        # And changing the role changes the account, with nothing else involved.
        rbac.set_role_permission(db, role=db.get(Role, role_id), code="issue.create", allowed=True)
        db.flush()
        assert "issue.create" in effective_permissions(db, person)
    finally:
        _purge(db, email)
        db.execute(text("DELETE FROM role_permissions WHERE role_id = :id"), {"id": role_id})
        db.execute(text("DELETE FROM roles WHERE id = :id"), {"id": role_id})
        db.commit()


# --- no account exists without an office role ---------------------------------

def test_provisioning_requires_an_office_role(db, office):
    with pytest.raises(ValueError, match="office role is required"):
        create_provisioned_user(
            db, creator=office["admin"],
            email=f"nobody-{uuid4().hex[:8]}@example.com", full_name="Nobody",
            org_role=None, password="Str0ngPassw0rd!", send_email=False,
        )


def test_the_database_refuses_an_account_without_an_office_role(db):
    """`users.org_role_id` is NOT NULL: the invariant is the schema's, not a convention."""
    nullable = db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'users' AND column_name = 'org_role_id'"
    )).scalar()
    assert nullable == "NO"
    assert db.execute(text("SELECT count(*) FROM users WHERE org_role_id IS NULL")).scalar() == 0
