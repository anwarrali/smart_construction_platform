"""A brand-new deployment gets its roles, and its first administrator gets one.

Role rows used to reach a database only through `python -m
app.db.rbac_backfill`, a hand-run script in no start sequence. On a fresh
deployment `bootstrap_admin` therefore found no `org_admin`, wrote the initial
administrator without an office role, and every permission check refused them.

These tests run against a **genuinely fresh database**: a throwaway database on
the same server, migrated to head with Alembic exactly as a new deployment is,
and dropped afterwards. The shared development database is never written to —
a fresh database cannot be simulated there, because it already holds roles.

Migrating takes a while, so it is done once into a template database; every
test gets its own copy of that template (`CREATE DATABASE ... TEMPLATE`), so no
test sees another's changes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.role_templates import BY_CODE_TEMPLATE, DISCIPLINES, LEGACY_CONSULTANT_TEMPLATE, TEMPLATES
from app.db.bootstrap_admin import BootstrapConfig, bootstrap_admin
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.rbac import Discipline, Role, RolePermission
from app.models.user import User
from app.services import rbac
from app.services.authorization import effective_permissions

BACKEND = Path(__file__).resolve().parents[1]
ADMIN = BootstrapConfig(
    email="first.admin@example.com", password="FreshDeploy!2345", full_name="First Administrator",
)
#: Every role a fresh database should hold: the templates, plus the one kept
#: for pre-redesign CONSULTANT accounts, which `seed_roles` seeds unconditionally.
EXPECTED_ROLE_CODES = {template.code for template in TEMPLATES} | {LEGACY_CONSULTANT_TEMPLATE.code}


def _server_url():
    return make_url(os.environ.get("DATABASE_URL") or str(SessionLocal.kw["bind"].url))


def _admin_engine():
    # Any database will do for CREATE/DROP DATABASE; AUTOCOMMIT because neither
    # may run inside a transaction.
    return create_engine(_server_url(), isolation_level="AUTOCOMMIT")


def _drop(admin, name):
    admin.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="module")
def migrated_template():
    """A database migrated to head from nothing, used only as a template."""
    name = f"cps_fresh_template_{uuid4().hex[:10]}"
    try:
        admin = _admin_engine().connect()
        # From template0, not the default template1: an image upgrade can leave
        # template1's recorded collation version behind the OS's, and Postgres
        # then refuses to copy it. template0 carries nothing to disagree about.
        admin.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
    except SQLAlchemyError as exc:  # pragma: no cover - only without a server or privilege
        pytest.skip(f"cannot create an isolated database: {exc}")
    try:
        url = _server_url().set(database=name).render_as_string(hide_password=False)
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND, env={**os.environ, "DATABASE_URL": url},
            capture_output=True, text=True, timeout=600,
        )
        assert migrated.returncode == 0, migrated.stderr[-4000:]
        yield name
    finally:
        _drop(admin, name)
        admin.close()


@pytest.fixture()
def fresh_db(migrated_template):
    """A session on a private copy of the freshly migrated database."""
    name = f"cps_fresh_{uuid4().hex[:10]}"
    admin = _admin_engine().connect()
    admin.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{migrated_template}"'))
    engine = create_engine(_server_url().set(database=name))
    session = sessionmaker(bind=engine, autoflush=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        _drop(admin, name)
        admin.close()


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
    assert admin.role == UserRole.ADMIN, "the legacy column is still written"


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
    Access Control screen writes denials onto the shared templates, so calling
    it on an initialized database would switch those back on; bootstrap must
    not, even though it runs with the roles already there.
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


def test_a_legacy_database_with_accounts_but_no_roles_is_not_seeded(fresh_db):
    """Those accounts need `rbac_backfill`, which folds their retired overrides
    into the roles as it seeds them. Seeding plain templates first would lose them."""
    fresh_db.add(User(
        full_name="Legacy Account", email="legacy@example.com", hashed_password="x",
        role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE,
    ))
    fresh_db.flush()

    assert rbac.seed_fresh_database(fresh_db) is False
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
