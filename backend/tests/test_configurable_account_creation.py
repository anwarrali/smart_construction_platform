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
  * no account can be provisioned as a Worker through either path.

Everything runs in one transaction against the real database and is rolled
back. `create_provisioned_user` commits internally, so the two tests that call
it clean up the row they created explicitly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.role_templates import (
    BY_CODE_TEMPLATE,
    PROVISIONING_LEGACY_AFFILIATION,
    PROVISIONING_LEGACY_ROLE,
    TEMPLATES,
)
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.rbac import Discipline, Role
from app.models.user import User
from app.services import rbac
from app.services.authorization import effective_permissions
from app.services.user_service import create_provisioned_user, legacy_role_for


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
        hashed_password="x", role=UserRole.ADMIN, status=UserStatus.ACTIVE,
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


# --- the provisioning table cannot drift from the migration ------------------

def test_provisioning_legacy_roles_match_the_migration():
    """The migration copies the table; a test is what keeps the copy honest.

    A migration must keep describing the schema of its own moment, so it cannot
    import `role_templates` — the module will move on and the migration must
    not. The price of that is a duplicated dict, and this is what stops the two
    diverging while both still exist.
    """
    import ast
    import pathlib

    source = pathlib.Path(
        "alembic/versions/e48c1b6d3f27_role_legacy_role_for_provisioning.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    tables = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in {"TEMPLATE_LEGACY_ROLE", "TEMPLATE_AFFILIATION"}
    }
    assert tables["TEMPLATE_LEGACY_ROLE"] == PROVISIONING_LEGACY_ROLE
    assert tables["TEMPLATE_AFFILIATION"] == PROVISIONING_LEGACY_AFFILIATION


def test_every_template_except_the_archive_can_provision():
    """One template is unprovisionable, and it is the right one."""
    unprovisionable = {
        template.code for template in TEMPLATES if template.legacy_role is None
    }
    assert unprovisionable == {"archived_field_staff"}


def test_a_provisioning_value_is_never_inferred_from_inherited_permissions():
    """Technical Director is the case that proves the two are different questions.

    Its permissions inherit from ADMIN; its accounts are written as
    PROJECT_MANAGER, because a surviving `role == UserRole.ADMIN` check must
    not treat it as a full administrator. If somebody ever "simplifies" this to
    `inherits.name`, this fails.
    """
    template = BY_CODE_TEMPLATE["technical_director"]
    assert template.inherits is UserRole.ADMIN
    assert template.legacy_role == UserRole.PROJECT_MANAGER.name


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

        # The retired columns are still written, from the role rather than from
        # anything the caller supplied.
        assert person.role == UserRole.ENGINEER
        assert person.engineer_affiliation == "internal_engineer"
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


# --- Worker stays unreachable ------------------------------------------------

def test_no_account_can_be_provisioned_under_the_archived_role(db, office):
    """The one template with no legacy value refuses, loudly."""
    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        legacy_role_for(office["roles"]["archived_field_staff"])

    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=office["admin"],
            email=f"never-{uuid4().hex[:8]}@example.com", full_name="Never",
            org_role=office["roles"]["archived_field_staff"],
            password="Str0ngPassw0rd!", send_email=False,
        )


def test_no_configured_role_provisions_a_worker():
    """Not one role in the office's vocabulary writes the retired WORKER value."""
    assert UserRole.WORKER.name not in set(PROVISIONING_LEGACY_ROLE.values())


def test_no_template_provisions_an_external_consultant_affiliation():
    """A consultant-side reviewer is office staff, per the confirmed direction.

    `external_consultant` survives only on accounts created before the
    redesign, where the pre-backfill bridges still read it. Nothing creates a
    new one.
    """
    assert "external_consultant" not in set(PROVISIONING_LEGACY_AFFILIATION.values())


# --- an office role the office invented --------------------------------------

def test_a_role_the_office_invented_can_provision(db, office):
    """The point of the whole exercise: a role that is not in any template."""
    role = Role(
        organization_id=office["organization"].id, code=f"resident_engineer_{uuid4().hex[:6]}",
        name_en="Resident Engineer", scope="BOTH", is_internal_only=True,
        is_system=False, rank=75, legacy_role=UserRole.ENGINEER.name,
    )
    db.add(role)
    db.flush()
    assert legacy_role_for(role) == UserRole.ENGINEER


# --- every creation path leaves an account the platform can resolve ----------

def test_the_legacy_creation_path_still_assigns_a_database_role(db, office):
    """The precondition `RBAC_REQUIRE_DB_ROLES` actually depends on.

    The flag turns "no `org_role_id`" from a fallback into an error. That is
    only safe if nothing *creates* such an account — and the legacy enum path
    did exactly that until it was taught to resolve the seeded role its enum
    maps to. Without this, switching the flag on would have made every account
    created through the old form immediately unusable.
    """
    email = f"legacy-{uuid4().hex[:8]}@example.com"
    try:
        person, _ = create_provisioned_user(
            db, creator=office["admin"], email=email, full_name="Legacy Path",
            role=UserRole.PROJECT_MANAGER,
            password="Str0ngPassw0rd!", send_email=False,
        )
        assert person.org_role_id is not None, "an unmigrated account must not be creatable"
        assert person.org_role.code == "project_manager"
        assert effective_permissions(db, person), "and it must resolve to something"
    finally:
        _purge(db, email)


def test_no_active_account_is_left_without_a_database_role(db, office):
    """The other half: nothing already in the database is unmigrated either."""
    assert rbac.active_users_missing_roles(db) == 0
