"""Regression coverage for the cost-validation IDOR fix.

`get_cost_validation_by_id` used to look a claim up by UUID alone and return
it to any authenticated user, regardless of whether they had anything to do
with the project it belonged to — a classic IDOR, since claim UUIDs are
returned to every project member in ordinary list responses and are not a
secret. The fix layers the same `user_has_project_access` check the sibling
by-project listing (`get_cost_validations_by_project`) already used.

Unauthenticated access is not exercised here: `current_user` is a required
`Depends(get_current_user)` parameter with no anonymous fallback, the same
structural protection every other endpoint in this suite relies on instead of
a per-endpoint 401 test.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.cost_validations import get_cost_validation_by_id
from app.db.database import SessionLocal
from app.models.cost_validation import CostValidation
from app.models.enums import CostValidationStatus, ProjectStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User


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


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM cost_validations WHERE project_id = ANY(:projects)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


@pytest.fixture()
def world(db):
    suffix = uuid4().hex[:10]

    def user(name, role):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE)
        db.add(person)
        return person

    people = {
        "admin": user("CostAdmin", UserRole.ADMIN),
        "manager": user("CostPm", UserRole.PROJECT_MANAGER),
        "owner": user("CostOwner", UserRole.OWNER),
        "engineer": user("CostEngineer", UserRole.ENGINEER),
        # Belongs to a different project entirely - no membership, no ownership,
        # no PM assignment on the project the claim lives under.
        "outsider": user("CostOutsider", UserRole.ENGINEER),
    }
    db.flush()

    project = Project(name=f"Cost Validation Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    other_project = Project(name=f"Other Cost Project {suffix}", status=ProjectStatus.ACTIVE,
                            owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    db.add_all([project, other_project])
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=people["engineer"].id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.add(ProjectMember(project_id=other_project.id, user_id=people["outsider"].id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()

    claim = CostValidation(
        project_id=project.id, requested_by_id=people["manager"].id,
        material_name="Rebar", quantity=10, unit="ton", location="Site A",
        requested_cost=5000, status=CostValidationStatus.PENDING,
    )
    db.add(claim)
    db.flush()

    people["project"] = project
    people["other_project"] = other_project
    people["claim"] = claim
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id, other_project.id], user_ids)


def test_the_requesting_manager_can_read_their_own_claim(db, world):
    result = get_cost_validation_by_id(world["claim"].id, db=db, current_user=world["manager"])
    assert result.id == world["claim"].id


def test_a_project_member_can_read_a_claim_on_their_project(db, world):
    result = get_cost_validation_by_id(world["claim"].id, db=db, current_user=world["engineer"])
    assert result.id == world["claim"].id


def test_an_administrator_can_read_any_claim(db, world):
    result = get_cost_validation_by_id(world["claim"].id, db=db, current_user=world["admin"])
    assert result.id == world["claim"].id


def test_the_project_owner_can_read_a_claim_on_their_project(db, world):
    result = get_cost_validation_by_id(world["claim"].id, db=db, current_user=world["owner"])
    assert result.id == world["claim"].id


def test_an_unrelated_user_cannot_read_another_projects_claim_by_guessing_its_id(db, world):
    """The IDOR this regression test pins: a valid UUID for someone else's
    project must not be enough to read the claim."""
    with pytest.raises(HTTPException) as error:
        get_cost_validation_by_id(world["claim"].id, db=db, current_user=world["outsider"])
    assert error.value.status_code == 403


def test_a_missing_claim_is_a_404_regardless_of_who_asks(db, world):
    with pytest.raises(HTTPException) as error:
        get_cost_validation_by_id(uuid4(), db=db, current_user=world["outsider"])
    assert error.value.status_code == 404
