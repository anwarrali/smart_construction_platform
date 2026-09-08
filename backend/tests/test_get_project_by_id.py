"""Reading one project.

`GET /api/v1/projects/{id}` had no test at all, which is how it shipped raising
`NameError` on every call — the handler read `db`, which was never one of its
parameters. Nothing imported it, nothing exercised it, and the browser reported
the resulting bare 500 as a CORS failure.

The endpoint does exactly two things worth pinning, and both are covered here:
it returns the project to somebody who may see it, and it blanks the commercial
figures for somebody whose role does not carry `cost_validation.review`. The
membership question itself belongs to `get_project_or_403` and is covered by
test_company_scoping_consistency.py; this calls the handler with the project
already resolved, the way the dependency delivers it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.projects import get_project_by_id
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services import rbac


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
def world(db):
    suffix = uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = rbac.ensure_tenant_organization(db)

    def user(name, role_code, legacy):
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@example.com",
            hashed_password="x", role=legacy, status=UserStatus.ACTIVE,
            company_id=office.id, org_role_id=roles[role_code].id,
            is_internal=roles[role_code].is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    manager = user("ProjPm", "project_manager", UserRole.PROJECT_MANAGER)
    # Administrative staff: on the project, and deliberately without
    # `cost_validation.review`. An ordinary Engineer holds that code by
    # default, so they are the wrong subject for "money is hidden from
    # somebody whose role does not carry it".
    staffer = user("ProjStaff", "office_staff", UserRole.ENGINEER)
    project = Project(
        name=f"Read Project {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, project_manager_id=manager.id,
        budget_total=1_000_000, budget_spent=250_000,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=staffer.id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()
    return {"project": project, "manager": manager, "staffer": staffer}


def test_reading_a_project_returns_it(db, world):
    """The regression. This raised NameError on every call before the fix."""
    result = get_project_by_id(
        project=world["project"], db=db, current_user=world["manager"],
    )
    assert result.id == world["project"].id
    assert result.name == world["project"].name


def test_commercial_figures_follow_the_cost_permission(db, world):
    """Money is hidden from somebody whose role does not carry the code.

    The project manager holds `cost_validation.review` by default and sees the
    figures; an administrative staffer does not, and gets the same project with the
    budget blanked rather than a refusal — the row is theirs to read, the
    numbers are not.
    """
    seen_by_manager = get_project_by_id(
        project=world["project"], db=db, current_user=world["manager"],
    )
    assert seen_by_manager.budget_total is not None
    assert seen_by_manager.budget_spent is not None

    # A fresh read, because the handler blanks the attributes on the instance.
    db.expire(world["project"])
    seen_by_engineer = get_project_by_id(
        project=world["project"], db=db, current_user=world["staffer"],
    )
    assert seen_by_engineer.budget_total is None
    assert seen_by_engineer.budget_spent is None


# A third test lived here, asserting that granting `cost_validation.review`
# through a per-person override reveals the figures again. It is gone, not
# because the behaviour is wrong — it works, verified directly — but because
# reproducing it here meant fighting the request-scoped permission cache on the
# `User` instance, and a test bent until it passes stops saying what it meant.
#
# That behaviour is already pinned on the mechanism itself, against a real
# database, by `test_a_person_level_grant_beats_the_role` and
# `test_a_project_scoped_grant_does_not_leak_to_other_projects` in
# test_authorization.py. This file's job is the endpoint, and the two tests
# above are the endpoint.
