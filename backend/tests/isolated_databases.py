"""Throwaway databases on the test server, migrated with Alembic.

For tests that need a database the shared development one cannot be: freshly
migrated with no roles, or still at the revision that has the retired role
columns. Each template is migrated once per session; every test gets its own
copy (`CREATE DATABASE ... TEMPLATE`), dropped afterwards.
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.database import SessionLocal

BACKEND = Path(__file__).resolve().parents[1]

#: The last revision with the retired role columns; the legacy backfill runs here.
PRE_CONTRACT = "c84d6e2f1a37"


def server_url():
    return make_url(os.environ.get("DATABASE_URL") or str(SessionLocal.kw["bind"].url))


def _admin_engine():
    # Any database will do for CREATE/DROP DATABASE; AUTOCOMMIT because neither
    # may run inside a transaction.
    return create_engine(server_url(), isolation_level="AUTOCOMMIT")


def _drop(admin, name):
    admin.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def url_for(name: str) -> str:
    return server_url().set(database=name).render_as_string(hide_password=False)


def alembic_upgrade(url: str, target: str):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=BACKEND, env={**os.environ, "DATABASE_URL": url},
        capture_output=True, text=True, timeout=600,
    )


@contextmanager
def migrated_template(prefix: str, target: str):
    """A database migrated from nothing to `target`, used only as a template."""
    name = f"{prefix}_{uuid4().hex[:10]}"
    try:
        admin = _admin_engine().connect()
        # From template0, not the default template1: an image upgrade can leave
        # template1's recorded collation version behind the OS's, and Postgres
        # then refuses to copy it. template0 carries nothing to disagree about.
        admin.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
    except SQLAlchemyError as exc:  # pragma: no cover - only without a server or privilege
        pytest.skip(f"cannot create an isolated database: {exc}")
    try:
        migrated = alembic_upgrade(url_for(name), target)
        assert migrated.returncode == 0, migrated.stderr[-4000:]
        yield name
    finally:
        _drop(admin, name)
        admin.close()


@contextmanager
def copy_of(template: str, prefix: str):
    """A session on a private copy of `template`: (session, url)."""
    name = f"{prefix}_{uuid4().hex[:10]}"
    admin = _admin_engine().connect()
    admin.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{template}"'))
    engine = create_engine(server_url().set(database=name))
    session = sessionmaker(bind=engine, autoflush=True)()
    try:
        yield session, url_for(name)
    finally:
        session.close()
        engine.dispose()
        _drop(admin, name)
        admin.close()


def insert_legacy_account(db, *, email, role, affiliation=None, company_id=None,
                          organization=None, full_name=None, status="active"):
    """An account as the retired model wrote it: legacy columns, no office role.

    Raw SQL, because the ORM no longer maps `users.role` or
    `engineer_affiliation`. Returns the new id.
    """
    user_id = uuid4()
    db.execute(text(
        "INSERT INTO users (id, email, full_name, hashed_password, status, is_email_verified, "
        "is_superuser, notify_by_email, notify_by_telegram, role, engineer_affiliation, "
        "company_id, organization) "
        "VALUES (:id, :email, :full_name, 'x', CAST(:status AS user_status), true, false, "
        "false, false, CAST(:role AS user_role), :affiliation, :company_id, :organization)"
    ), {"id": user_id, "email": email, "full_name": full_name or email, "status": status,
        "role": role, "affiliation": affiliation, "company_id": company_id,
        "organization": organization})
    return user_id


def insert_legacy_member(db, *, project_id, user_id, role_on_project, site_engineer=False,
                         discipline=None):
    """A project membership with the retired `role_on_project`. Returns the id."""
    member_id = uuid4()
    db.execute(text(
        "INSERT INTO project_members (id, project_id, user_id, role_on_project, is_active, "
        "is_site_engineer, project_discipline) "
        "VALUES (:id, :project, :user, CAST(:role AS user_role), true, :site, :discipline)"
    ), {"id": member_id, "project": project_id, "user": user_id, "role": role_on_project,
        "site": site_engineer, "discipline": discipline})
    return member_id
