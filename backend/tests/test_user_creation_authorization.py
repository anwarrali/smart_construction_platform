"""Who may provision an account, and what may never be provisioned.

`can_create_team_role(creator_role, target_role)` did two unrelated jobs in one
predicate, and only one of them was an authorization question:

  * **who** — it returned True only for `UserRole.ADMIN`, so an office that
    granted `platform.manage_users` to a role of its own still could not create
    accounts through the legacy path. That is the configurability the redesign
    exists to provide, and it is now `platform.manage_users` on both branches of
    `POST /users`.
  * **what** — it refused `UserRole.WORKER` by leaving it out of a set. That is
    not a permission and must never become one: an office must not be able to
    make worker accounts provisionable by granting something. It is an invariant
    in `create_provisioned_user`.

Separately, the rule "no account may be created under an archived role" used to
fall out of `legacy_role_for` failing to translate a role whose `legacy_role` was
NULL. It is now `Role.is_archived`, checked before translation is attempted.

These tests exercise the endpoint and the service. The RBAC equivalence gate
cannot see any of this — it compares permission *resolution* for existing
accounts and never invokes a creation path — so it is not evidence for this
change and is not treated as such here.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.users import create_user
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.permission import UserPermissionOverride
from app.models.rbac import Discipline, Role
from app.models.user import User
from app.schemas.user import EngineerProfileCreate, UserCreateByAdmin
from app.services import rbac
from app.services.user_service import create_provisioned_user, legacy_role_for

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

    def person(label, role_code, legacy):
        row = User(
            full_name=label, email=f"{label.lower()}-{suffix}@example.com",
            hashed_password="x", role=legacy, status=UserStatus.ACTIVE,
            company_id=organization.id, org_role_id=roles[role_code].id,
            is_internal=True,
        )
        db.add(row)
        return row

    admin = person("UcaAdmin", "org_admin", UserRole.ADMIN)
    # An ordinary office engineer: holds no provisioning authority by default,
    # and is the account the grant is later given to.
    engineer = person("UcaEngineer", "engineer", UserRole.ENGINEER)
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

def test_an_administrator_can_create_through_the_legacy_role_path(office):
    """The behaviour the retired check allowed, preserved."""
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "legacyadmin"),
        full_name="Legacy Admin Made", role=UserRole.ENGINEER,
        engineer_affiliation="internal_engineer", password=PASSWORD, send_email=False,
    )
    assert user.role == UserRole.ENGINEER
    assert user.org_role_id is not None


def test_someone_without_the_permission_is_refused(office):
    """An office engineer holds no provisioning authority."""
    db = office["db"]
    with pytest.raises(HTTPException) as refusal:
        create_provisioned_user(
            db, creator=office["engineer"], email=_new_email(office, "denied"),
            full_name="Denied", role=UserRole.ENGINEER,
            engineer_affiliation="internal_engineer", password=PASSWORD, send_email=False,
        )
    assert refusal.value.status_code == 403


def test_a_non_administrator_granted_the_permission_can_create(office):
    """The intended widening, and the whole point of the change.

    Under `can_create_team_role` this was impossible: the check asked whether
    the creator's retired enum was ADMIN, so no grant an office could make would
    ever admit this person.
    """
    db = office["db"]
    engineer = office["engineer"]
    _grant_manage_users(db, engineer)

    user, _ = create_provisioned_user(
        db, creator=engineer, email=_new_email(office, "grantedcreate"),
        full_name="Made By Grant", role=UserRole.ENGINEER,
        engineer_affiliation="internal_engineer", password=PASSWORD, send_email=False,
    )
    assert user.email.startswith("grantedcreate")


def test_both_endpoint_branches_answer_to_the_same_permission(office):
    """`POST /users` used to gate its two branches on two different authorities."""
    db = office["db"]
    engineer = office["engineer"]
    _grant_manage_users(db, engineer)

    # Modern branch: org_role_id.
    modern = create_user(
        user_data=UserCreateByAdmin(
            email=_new_email(office, "modern"), full_name="Modern Path",
            password=PASSWORD, org_role_id=office["roles"]["engineer"].id,
        ),
        db=db, current_user=engineer,
    )
    assert modern.email.startswith("modern")

    # Legacy branch: bare role enum.
    legacy = create_user(
        user_data=UserCreateByAdmin(
            email=_new_email(office, "legacy"), full_name="Legacy Path",
            password=PASSWORD, role=UserRole.ENGINEER,
            engineer_profile=EngineerProfileCreate(
                discipline=office["disciplines"]["civil"].code
                if "civil" in office["disciplines"] else "civil",
            ),
        ),
        db=db, current_user=engineer,
    )
    assert legacy.email.startswith("legacy")


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

def test_a_worker_account_cannot_be_created_even_with_the_permission(office):
    """The invariant, not a permission.

    `can_create_team_role` refused WORKER by omitting it from a set. Holding
    `platform.manage_users` must not make it reachable — an office cannot grant
    its way to a worker account.
    """
    db = office["db"]
    engineer = office["engineer"]
    _grant_manage_users(db, engineer)

    with pytest.raises(ValueError, match="Worker accounts can no longer be created"):
        create_provisioned_user(
            db, creator=engineer, email=_new_email(office, "worker"),
            full_name="Should Not Exist", role=UserRole.WORKER,
            password=PASSWORD, send_email=False,
        )


def test_an_administrator_cannot_create_a_worker_either(office):
    db = office["db"]
    with pytest.raises(ValueError, match="Worker accounts can no longer be created"):
        create_provisioned_user(
            db, creator=office["admin"], email=_new_email(office, "adminworker"),
            full_name="Should Not Exist", role=UserRole.WORKER,
            password=PASSWORD, send_email=False,
        )


def test_no_account_can_be_created_under_an_archived_role(office):
    """Now refused for being archived, not for being untranslatable."""
    db = office["db"]
    archived = office["roles"]["archived_field_staff"]
    assert archived.is_archived is True

    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=office["admin"], email=_new_email(office, "archived"),
            full_name="Never", org_role=archived, password=PASSWORD, send_email=False,
        )


def test_the_archived_refusal_does_not_depend_on_legacy_role(office):
    """The separation this change exists to make.

    A role that is archived *and* translatable must still be refused. Under the
    old rule it would have been created, because the refusal came from
    `legacy_role_for` failing rather than from any statement about the role.
    """
    db = office["db"]
    role = Role(
        organization_id=office["organization"].id,
        code=f"archived_but_translatable_{uuid4().hex[:6]}",
        name_en="Archived But Translatable", scope="ORG", is_internal_only=True,
        is_system=False, rank=901, legacy_role=UserRole.ENGINEER.name,
        is_archived=True,
    )
    db.add(role)
    db.flush()

    # It translates fine — so nothing about `legacy_role` would stop this.
    assert legacy_role_for(role) == UserRole.ENGINEER

    with pytest.raises(ValueError, match="cannot be used to create accounts"):
        create_provisioned_user(
            db, creator=office["admin"], email=_new_email(office, "archtrans"),
            full_name="Never", org_role=role, password=PASSWORD, send_email=False,
        )
    db.rollback()


# --- behaviour that must survive ---------------------------------------------

def test_creation_under_a_normal_org_role_still_works(office):
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "normal"),
        full_name="Normal Role", org_role=office["roles"]["senior_engineer"],
        password=PASSWORD, send_email=False,
    )
    assert user.org_role_id == office["roles"]["senior_engineer"].id
    assert user.role == UserRole.ENGINEER


def test_the_consultant_compatibility_rewrite_is_unchanged(office):
    """A legacy CONSULTANT request still persists as an external-consultant Engineer."""
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "consultant"),
        full_name="Consultant Compat", role=UserRole.CONSULTANT,
        organization="Outside Firm", password=PASSWORD, send_email=False,
    )
    assert user.role == UserRole.ENGINEER
    assert user.engineer_affiliation == "external_consultant"


def test_every_created_account_still_gets_a_database_role(office):
    """`user_role_backstop`'s precondition, unchanged by this task.

    Regression cover only: the backstop itself was not touched.
    """
    db = office["db"]
    user, _ = create_provisioned_user(
        db, creator=office["admin"], email=_new_email(office, "hasrole"),
        full_name="Has Role", role=UserRole.ENGINEER,
        engineer_affiliation="internal_engineer", password=PASSWORD, send_email=False,
    )
    assert user.org_role_id is not None
    assert user.is_internal is True


def test_a_bare_user_row_still_gets_a_role_from_the_backstop(office):
    """The listener fills `org_role_id` for a row written without one."""
    db = office["db"]
    email = _new_email(office, "bare")
    row = User(
        full_name="Bare Row", email=email, hashed_password="x",
        role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
        engineer_affiliation="internal_engineer",
    )
    db.add(row)
    db.flush()
    assert row.org_role_id is not None, "the backstop did not assign a role"


# --- staffability ------------------------------------------------------------

def test_an_account_on_an_archived_role_is_not_staffable(office):
    db = office["db"]
    parked = User(
        full_name="Parked", email=_new_email(office, "parked"), hashed_password="x",
        role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
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
