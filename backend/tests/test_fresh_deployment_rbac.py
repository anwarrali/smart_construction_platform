"""A deployment's RBAC data, from nothing and from the retired model.

**Fresh.** Migrations create schema only. `bootstrap_admin` seeds the role
templates (`rbac.seed_fresh_database`) and gives the first administrator
`org_admin` before writing it, with no manual step in between.

**Legacy.** A database still describing people by the retired `users.role` /
`engineer_affiliation` columns is carried across by `app.db.rbac_backfill`, run
at the last revision that has those columns; the migration that removes them
refuses until every account holds an office role.

These tests run against **genuinely fresh databases**: throwaway databases on
the same server, migrated with Alembic exactly as a deployment is, and dropped
afterwards. The shared development database is never written to.

The databases come from `tests/isolated_databases.py` through the `fresh_db`
and `legacy_db` fixtures in `conftest.py`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.role_templates import BY_CODE_TEMPLATE, DISCIPLINES, LEGACY_CONSULTANT_TEMPLATE, TEMPLATES
from app.db.bootstrap_admin import BootstrapConfig, bootstrap_admin
from app.db.database import SessionLocal
from app.models.enums import UserStatus
from app.models.rbac import Discipline, Role, RolePermission
from app.models.user import User
from app.services import rbac
from app.services.authorization import effective_permissions
from tests.isolated_databases import alembic_upgrade, insert_legacy_account

ADMIN = BootstrapConfig(
    email="first.admin@example.com", password="FreshDeploy!2345", full_name="First Administrator",
)
#: Every role a fresh database should hold: the templates, plus the one kept
#: for pre-redesign CONSULTANT accounts, which `seed_roles` seeds unconditionally.
EXPECTED_ROLE_CODES = {template.code for template in TEMPLATES} | {LEGACY_CONSULTANT_TEMPLATE.code}


def _count(db, model):
    return db.query(model).count()


def _administrator(db):
    return db.query(User).filter(User.email == ADMIN.email).one()


# --- the gap -------------------------------------------------------------------

def test_migrations_alone_leave_a_fresh_database_with_no_roles(fresh_db):
    """The root cause, pinned: no migration seeds the role templates.

    Deliberately so — a migration must not import application constants
    (see `a92d4e1f70b3`) — which is why seeding belongs to the first-account
    path rather than to Alembic.
    """
    assert _count(fresh_db, Role) == 0
    assert _count(fresh_db, User) == 0


# --- bootstrap initializes the deployment -------------------------------------

def test_bootstrap_seeds_every_role_template_before_creating_the_administrator(fresh_db):
    bootstrap_admin(fresh_db, ADMIN)

    roles = {role.code: role for role in fresh_db.query(Role).all()}
    assert set(roles) == EXPECTED_ROLE_CODES
    assert all(role.organization_id is None and role.is_system for role in roles.values())
    for code, role in roles.items():
        template = LEGACY_CONSULTANT_TEMPLATE if code == LEGACY_CONSULTANT_TEMPLATE.code else BY_CODE_TEMPLATE[code]
        held = {row.permission_code for row in fresh_db.query(RolePermission).filter(
            RolePermission.role_id == role.id, RolePermission.allowed.is_(True))}
        assert held == template.permissions(), code
    assert _count(fresh_db, Discipline) == len(DISCIPLINES)


def test_bootstrap_gives_the_administrator_org_admin_before_writing_it(fresh_db):
    """Nothing fills the role during the flush, so it can only have come from bootstrap."""
    bootstrap_admin(fresh_db, ADMIN)

    admin = _administrator(fresh_db)
    org_admin = fresh_db.query(Role).filter(Role.code == "org_admin", Role.organization_id.is_(None)).one()
    assert admin.org_role_id == org_admin.id
    assert admin.is_internal is True


def test_the_bootstrapped_administrator_can_actually_be_authorized(fresh_db):
    """The symptom the gap produced: an account permission resolution refuses.

    Bootstrap creates the account PENDING, and a non-active account holds no
    permissions by design; the first login activates it (`app/api/auth.py`),
    which is the step taken here before asking what it may do.
    """
    bootstrap_admin(fresh_db, ADMIN)
    admin = _administrator(fresh_db)
    assert admin.status == UserStatus.PENDING
    admin.status = UserStatus.ACTIVE  # what the first successful login does

    granted = effective_permissions(fresh_db, admin)
    assert {"platform.manage_users", "platform.view_all_projects"} <= granted


def test_archived_role_semantics_are_seeded_unchanged(fresh_db):
    bootstrap_admin(fresh_db, ADMIN)

    archived = {role.code for role in fresh_db.query(Role).filter(Role.is_archived.is_(True))}
    assert archived == {code for code, template in BY_CODE_TEMPLATE.items() if template.is_archived}
    assert archived == {"archived_field_staff"}


# --- idempotence -----------------------------------------------------------------

def test_initialization_is_idempotent(fresh_db):
    bootstrap_admin(fresh_db, ADMIN)
    before = (_count(fresh_db, Role), _count(fresh_db, RolePermission), _count(fresh_db, Discipline))

    assert rbac.seed_fresh_database(fresh_db) is False
    assert "already exists" in bootstrap_admin(fresh_db, ADMIN)

    after = (_count(fresh_db, Role), _count(fresh_db, RolePermission), _count(fresh_db, Discipline))
    assert after == before
    assert _count(fresh_db, User) == 1


# --- existing databases are left alone --------------------------------------------

def test_an_initialized_database_keeps_its_role_customizations(fresh_db):
    """Roles that already exist are never re-seeded, so nothing is re-granted.

    `seed_roles` refreshes an existing role's template permissions. The older
    An office's edits to a role would be switched back on by calling it on an
    initialized database; bootstrap must not, even though it runs with the
    roles already there.
    """
    roles = rbac.seed_roles(fresh_db)
    engineer = roles["engineer"]
    denied, removed = sorted(rbac.role_permission_codes(fresh_db, engineer.id))[:2]
    rbac.set_role_permission(fresh_db, role=engineer, code=denied, allowed=False)
    rbac.set_role_permission(fresh_db, role=engineer, code=removed, allowed=None)
    fresh_db.commit()
    snapshot = {
        (row.role_id, row.permission_code, row.allowed)
        for row in fresh_db.query(RolePermission).all()
    }
    role_count = _count(fresh_db, Role)

    bootstrap_admin(fresh_db, ADMIN)

    assert {
        (row.role_id, row.permission_code, row.allowed)
        for row in fresh_db.query(RolePermission).all()
    } == snapshot
    assert _count(fresh_db, Role) == role_count, "no role was duplicated"
    assert _administrator(fresh_db).org_role_id == roles["org_admin"].id


def test_no_account_can_exist_without_an_office_role(fresh_db):
    """`users.org_role_id` is NOT NULL: the invariant belongs to the schema."""
    from sqlalchemy.exc import IntegrityError

    fresh_db.add(User(
        full_name="Roleless", email="roleless@example.com", hashed_password="x", status=UserStatus.ACTIVE,
    ))
    with pytest.raises(IntegrityError):
        fresh_db.flush()
    fresh_db.rollback()


def test_a_fresh_database_carries_none_of_the_retired_schema(fresh_db):
    columns = {
        (row.table_name, row.column_name) for row in fresh_db.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        ))
    }
    for retired in (("users", "role"), ("users", "engineer_affiliation"),
                    ("project_members", "role_on_project"),
                    ("roles", "legacy_role"), ("roles", "legacy_affiliation")):
        assert retired not in columns, retired
    tables = {row[0] for row in fresh_db.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
    ))}
    assert "role_permission_overrides" not in tables
    assert fresh_db.execute(text("SELECT 1 FROM pg_type WHERE typname = 'user_role'")).first() is None


def test_the_legacy_backfill_refuses_a_fresh_database(fresh_db):
    from app.db.rbac_backfill import NothingToBackfill, run

    with pytest.raises(NothingToBackfill):
        run(fresh_db)
    assert _count(fresh_db, Role) == 0


def test_bootstrap_refuses_rather_than_create_an_administrator_without_a_role(fresh_db):
    """A database with roles but no `org_admin` cannot be repaired by guessing."""
    roles = rbac.seed_roles(fresh_db)
    fresh_db.query(RolePermission).filter(RolePermission.role_id == roles["org_admin"].id).delete()
    fresh_db.delete(roles["org_admin"])
    fresh_db.commit()

    with pytest.raises(RuntimeError, match="org_admin"):
        bootstrap_admin(fresh_db, ADMIN)
    fresh_db.rollback()
    assert _count(fresh_db, User) == 0


def test_the_shared_development_database_is_already_initialized():
    """And so, like every existing deployment, is left exactly as it is."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        db.close()
        pytest.skip("database is not reachable")
    try:
        assert rbac.seed_fresh_database(db) is False
        assert not db.new and not db.dirty
    finally:
        db.rollback()
        db.close()


# --- a legacy database ----------------------------------------------------------

#: (email, users.role, engineer_affiliation, the office role it must land on)
LEGACY_PEOPLE = (
    ("admin@legacy.test", "ADMIN", None, "org_admin"),
    ("pm@legacy.test", "PROJECT_MANAGER", None, "project_manager"),
    ("office@legacy.test", "ENGINEER", "internal_engineer", "engineer"),
    ("contractor@legacy.test", "ENGINEER", "main_contractor", "contractor_representative"),
    ("consultant@legacy.test", "ENGINEER", "external_consultant", "senior_engineer"),
    ("client@legacy.test", "OWNER", None, "client_representative"),
    ("worker@legacy.test", "WORKER", None, "archived_field_staff"),
)


def _insert_legacy_account(db, email, role, affiliation):
    insert_legacy_account(db, email=email, role=role, affiliation=affiliation)


def test_a_legacy_database_reaches_head_only_through_the_backfill(legacy_db):
    from app.db.rbac_backfill import run

    db, url = legacy_db
    for email, role, affiliation, _ in LEGACY_PEOPLE:
        _insert_legacy_account(db, email, role, affiliation)
    db.commit()

    # The contract migration refuses while the legacy columns are the only
    # record of what these people may do.
    refused = alembic_upgrade(url, "head")
    assert refused.returncode != 0
    assert "have no office role" in refused.stderr

    run(db)
    assert run_again_is_harmless(db)
    # End the session's transaction: the contract migration alters `roles`
    # and `users`, and an open read would hold the locks it waits for.
    db.rollback()

    upgraded = alembic_upgrade(url, "head")
    assert upgraded.returncode == 0, upgraded.stderr[-4000:]

    db.expire_all()
    landed = {
        email: code for email, code in db.execute(text(
            "SELECT u.email, r.code FROM users u JOIN roles r ON r.id = u.org_role_id"
        ))
    }
    assert landed == {email: expected for email, _, _, expected in LEGACY_PEOPLE}


def run_again_is_harmless(db):
    from app.db.rbac_backfill import run

    before = (_count(db, Role), _count(db, RolePermission))
    report = run(db)
    return report.users_mapped == 0 and (_count(db, Role), _count(db, RolePermission)) == before


def test_an_unknown_affiliation_fails_the_backfill_and_changes_nothing(legacy_db):
    """Fail closed: no guessed role, and the whole run rolls back."""
    from app.db.legacy_rbac import UnknownAffiliation
    from app.db.rbac_backfill import run

    db, _ = legacy_db
    _insert_legacy_account(db, "fine@legacy.test", "ENGINEER", "internal_engineer")
    _insert_legacy_account(db, "odd@legacy.test", "ENGINEER", "visiting_inspector")
    db.commit()

    with pytest.raises(UnknownAffiliation):
        run(db)
    db.rollback()

    assert db.execute(text("SELECT count(*) FROM users WHERE org_role_id IS NOT NULL")).scalar() == 0
    assert _count(db, Role) == 0
