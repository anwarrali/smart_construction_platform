"""Who may provision an account, and what may never be provisioned.

  * **Who** — anybody holding `platform.manage_users`, a permission the office
    administers. It used to be "the retired enum says ADMIN", which no grant an
    office could make would ever satisfy.
  * **What** — never an account under an archived role, such as the field-staff
    role retired worker accounts sit on. That is an invariant in
    `create_provisioned_user`, not a permission: an office cannot grant its way
    to it.
  * **How** — always under an office role, assigned before the account is
    written; `users.org_role_id` is NOT NULL, so there is no other way.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.users import create_user
from app.db.database import SessionLocal
from app.models.enums import UserStatus
from app.models.permission import UserPermissionOverride
from app.models.rbac import Discipline, Role
from app.models.user import User
from app.schemas.user import EngineerProfileCreate, UserCreateByAdmin
from app.services import rbac
from app.services.authorization import effective_permissions
from app.services.user_service import create_provisioned_user

PASSWORD = "Str0ngPassw0rd!"


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


def _purge(db, emails: list[str]) -> None:
    """`create_provisioned_user` commits, so a rollback cannot take rows back."""
    db.rollback()
    for statement in (
        "DELETE FROM user_permission_overrides WHERE user_id IN (SELECT id FROM users WHERE email = ANY(:emails))",
        "DELETE FROM user_disciplines WHERE user_id IN (SELECT id FROM users WHERE email = ANY(:emails))",
        "DELETE FROM organization_memberships WHERE user_id IN (SELECT id FROM users WHERE email = ANY(:emails))",
        "DELETE FROM engineer_profiles WHERE user_id IN (SELECT id FROM users WHERE email = ANY(:emails))",
        "DELETE FROM users WHERE email = ANY(:emails)",
    ):
        db.execute(text(statement), {"emails": emails})
    db.commit()


@pytest.fixture()
def office(db):
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    organization = rbac.ensure_tenant_organization(db)
    suffix = uuid4().hex[:8]

    def person(label, role_code):
        row = User(
            full_name=label, email=f"{label.lower()}-{suffix}@example.com",
            hashed_password="x", status=UserStatus.ACTIVE,
            company_id=organization.id, org_role_id=roles[role_code].id,
            is_internal=True,
        )
        db.add(row)
        return row

    admin = person("UcaAdmin", "org_admin")
    # An ordinary office engineer: holds no provisioning authority by default,
    # and is the account the grant is later given to.
    engineer = person("UcaEngineer", "engineer")
    db.add_all([admin, engineer])
    db.flush()

    disciplines = {
        row.code: row for row in
        db.query(Discipline).filter(Discipline.organization_id.is_(None)).all()
    }
    created: list[str] = [admin.email, engineer.email]
    world = {"roles": roles, "organization": organization, "admin": admin,
             "engineer": engineer, "disciplines": disciplines,
             "db": db, "created": created}
    try:
        yield world
    finally:
        _purge(db, created)


def _new_email(world, tag="new"):
    email = f"{tag}-{uuid4().hex[:10]}@example.com"
    world["created"].append(email)
    return email


def _grant_manage_users(db, user):
    db.add(UserPermissionOverride(
        user_id=user.id, permission_code="platform.manage_users",
        allowed=True, project_id=None,
    ))
    db.flush()


# --- who may provision -------------------------------------------------------

def test_an_administrator_can_create_an_account(office):
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "adminmade"),
        full_name="Admin Made", org_role=office["roles"]["engineer"],
        password=PASSWORD, send_email=False,
    )
    assert user.org_role_id == office["roles"]["engineer"].id


def test_someone_without_the_permission_is_refused(office):
    """An office engineer holds no provisioning authority."""
    db = office["db"]
    with pytest.raises(HTTPException) as refusal:
        create_provisioned_user(
            db, creator=office["engineer"], email=_new_email(office, "denied"),
            full_name="Denied", org_role=office["roles"]["engineer"],
            password=PASSWORD, send_email=False,
        )
    assert refusal.value.status_code == 403


def test_a_non_administrator_granted_the_permission_can_create(office):
    """The configurability the redesign exists to provide."""
    db = office["db"]
    engineer = office["engineer"]
    _grant_manage_users(db, engineer)

    user, _ = create_provisioned_user(
        db, creator=engineer, email=_new_email(office, "grantedcreate"),
        full_name="Made By Grant", org_role=office["roles"]["engineer"],
        password=PASSWORD, send_email=False,
    )
    assert user.email.startswith("grantedcreate")


def test_the_endpoint_answers_to_the_same_permission(office):
    """`POST /users` is gated on `platform.manage_users`, granted or not."""
    db = office["db"]
    engineer = office["engineer"]
    _grant_manage_users(db, engineer)
    created = create_user(
        user_data=UserCreateByAdmin(
            email=_new_email(office, "endpoint"), full_name="Endpoint Path",
            password=PASSWORD, org_role_id=office["roles"]["engineer"].id,
        ),
        db=db, current_user=engineer,
    )
    assert created.email.startswith("endpoint")


def test_the_endpoint_requires_an_office_role():
    """There is no request shape that creates an account without one."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        UserCreateByAdmin(email="norole@example.com", full_name="No Role", password=PASSWORD)


def test_the_endpoint_refuses_a_caller_without_the_permission(office):
    db = office["db"]
    with pytest.raises(HTTPException) as refusal:
        create_user(
            user_data=UserCreateByAdmin(
                email=_new_email(office, "nope"), full_name="No Permission",
                password=PASSWORD, org_role_id=office["roles"]["engineer"].id,
            ),
            db=db, current_user=office["engineer"],
        )
    assert refusal.value.status_code == 403


# --- what may never be provisioned -------------------------------------------

def test_no_account_can_be_created_under_the_archived_role_even_with_the_permission(office):
    """The invariant, not a permission: holding `platform.manage_users` does not reach it."""
    db = office["db"]
    engineer = office["engineer"]
    _grant_manage_users(db, engineer)
    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=engineer, email=_new_email(office, "worker"),
            full_name="Should Not Exist", org_role=office["roles"]["archived_field_staff"],
            password=PASSWORD, send_email=False,
        )


def test_an_administrator_cannot_create_one_either(office):
    db = office["db"]
    archived = office["roles"]["archived_field_staff"]
    assert archived.is_archived is True
    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=office["admin"], email=_new_email(office, "archived"),
            full_name="Never", org_role=archived, password=PASSWORD, send_email=False,
        )


def test_an_office_role_marked_archived_is_refused_too(office):
    """The refusal is about the flag, so it covers a role an office archives itself."""
    db = office["db"]
    role = Role(
        organization_id=office["organization"].id,
        code=f"archived_office_role_{uuid4().hex[:6]}",
        name_en="Archived Office Role", scope="ORG", is_internal_only=True,
        is_system=False, rank=901, is_archived=True,
    )
    db.add(role)
    db.flush()
    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=office["admin"], email=_new_email(office, "archtrans"),
            full_name="Never", org_role=role, password=PASSWORD, send_email=False,
        )
    db.rollback()


# --- behaviour that must survive ---------------------------------------------

def test_creation_under_a_normal_org_role_works(office):
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "normal"),
        full_name="Normal Role", org_role=office["roles"]["senior_engineer"],
        password=PASSWORD, send_email=False,
    )
    assert user.org_role_id == office["roles"]["senior_engineer"].id
    assert user.is_internal is True


def test_a_bare_user_row_is_refused_by_the_database(office):
    """What writing an account outside the creation paths now produces.

    `user_role_backstop` used to fill `org_role_id` during the flush for any
    `User` written without one. It is gone, and `users.org_role_id` is NOT
    NULL: a row that skips the creation paths never reaches the table.
    """
    from sqlalchemy.exc import IntegrityError
    db = office["db"]
    row = User(
        full_name="Bare Row", email=_new_email(office, "bare"), hashed_password="x", status=UserStatus.ACTIVE,
    )
    db.add(row)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# --- every creation path assigns the role itself -----------------------------

def test_an_external_role_is_written_external(office):
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "external"),
        full_name="External Path", org_role=office["roles"]["contractor_representative"],
        password=PASSWORD, send_email=False,
    )
    assert user.org_role_id == office["roles"]["contractor_representative"].id
    assert user.is_internal is False, "a contractor must not be written as internal"


def test_the_configured_role_path_assigns_its_role_before_writing(office):
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "configuredrole"),
        full_name="Configured Role", org_role=office["roles"]["surveyor"],
        password=PASSWORD, send_email=False,
    )
    assert user.org_role_id == office["roles"]["surveyor"].id
    assert user.is_internal is True


def test_the_demo_seed_assigns_its_role_before_writing(office):
    from app.db.seed_demo import _ensure_user

    db = office["db"]
    user = _ensure_user(
        db, key=f"seedpath-{uuid4().hex[:10]}", email=_new_email(office, "seed"),
        full_name="Seeded Owner", role_code="client_representative",
        company=office["organization"], password=PASSWORD,
    )
    db.flush()
    assert user.org_role_id == office["roles"]["client_representative"].id
    assert user.is_internal is False


# --- staffability ------------------------------------------------------------

def test_an_account_on_an_archived_role_is_not_staffable(office):
    db = office["db"]
    parked = User(
        full_name="Parked", email=_new_email(office, "parked"), hashed_password="x", status=UserStatus.ACTIVE,
        company_id=office["organization"].id,
        org_role_id=office["roles"]["archived_field_staff"].id, is_internal=True,
    )
    db.add(parked)
    db.flush()

    assert rbac.is_staffable(db, parked) is False
    staffable_ids = {
        row.id for row in db.query(User).filter(rbac.staffable_filter(db)).all()
    }
    assert parked.id not in staffable_ids


def test_an_account_on_an_active_role_remains_staffable(office):
    db = office["db"]
    engineer = office["engineer"]
    assert rbac.is_staffable(db, engineer) is True
    staffable_ids = {
        row.id for row in db.query(User).filter(rbac.staffable_filter(db)).all()
    }
    assert engineer.id in staffable_ids


def test_staffability_did_not_widen(office):
    """The two forms agree, and an inactive account is still excluded.

    `staffable_filter` and `is_staffable` are the SQL and row-level spellings of
    one rule; they moved to `is_archived` together and must not have drifted.
    """
    db = office["db"]
    engineer = office["engineer"]
    engineer.status = UserStatus.INACTIVE
    db.flush()

    assert rbac.is_staffable(db, engineer) is False
    staffable_ids = {
        row.id for row in db.query(User).filter(rbac.staffable_filter(db)).all()
    }
    assert engineer.id not in staffable_ids
    db.rollback()
