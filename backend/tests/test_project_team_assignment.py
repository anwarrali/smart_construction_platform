"""Assigning consultants to a project.

The reported defect: configuring one consultant to review every discipline
produced `POST /projects/{id}/members` 400. Two separate causes were found, and
both are pinned here.

  1. The eligible-user list never returned an account whose global role is
     Consultant — it only listed Engineers and Workers — so a Consultant account
     an administrator had created could not be picked at all, even though the
     assignment endpoint accepts one.
  2. The same list offered Workers who carry the external-consultant affiliation
     under the "Consultant" filter. The UI derives the project role from that
     affiliation, so assigning one was rejected as a role mismatch.

The validation itself is correct and is left in place: these tests also pin that
a genuine mismatch and a site-engineer assignment on a non-engineer still fail.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.projects import add_project_member, get_available_team_members
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.project import ProjectMemberAssignExisting


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

    def user(name, role, affiliation=None):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      engineer_affiliation=affiliation)
        db.add(person)
        return person

    people = {
        "admin": user("TeamAdmin", UserRole.ADMIN),
        "manager": user("TeamPm", UserRole.PROJECT_MANAGER),
        "owner": user("TeamOwner", UserRole.OWNER),
        # The two shapes a consultant can take.
        "pure_consultant": user("PureConsultant", UserRole.CONSULTANT),
        "external_engineer": user("ExternalConsultant", UserRole.ENGINEER, "external_consultant"),
        # A contractor-side engineer, and a worker wearing the same affiliation.
        "engineer": user("SiteEngineer", UserRole.ENGINEER, "main_contractor"),
        "worker": user("ExternalWorker", UserRole.WORKER, "external_consultant"),
    }
    db.flush()

    project = Project(name=f"Team Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=people["manager"].id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    db.flush()
    people["project"] = project
    people["suffix"] = suffix
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id], user_ids + [people[key].id for key in ("outsider",) if key in people])


def _purge(db, project_ids, user_ids):
    """Remove what the fixture created.

    Several of these endpoints commit (`add_project_member`, `update_project`),
    so rolling the session back is not enough: without this the fixture would
    leave its people and projects behind on every run.
    """
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM consultant_engineer_scopes WHERE project_id = ANY(:projects) OR consultant_user_id = ANY(:users)",
        "DELETE FROM user_permission_overrides WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM role_permission_overrides WHERE updated_by_id = ANY(:users)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_model_versions WHERE project_id = ANY(:projects) OR uploaded_by_id = ANY(:users)",
        "DELETE FROM ifc_model_groups WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM project_consultant_reviewers WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM engineer_profiles WHERE user_id = ANY(:users)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


def _offered(db, world, **kwargs):
    rows = get_available_team_members(world["project"].id, db=db, current_user=world["admin"], **kwargs)
    return {row.id for row in rows if world["suffix"] in row.email}


def _assign(db, world, person, role_on_project, *, site_engineer=False, actor="admin"):
    payload = ProjectMemberAssignExisting(user_id=world[person].id, role_on_project=role_on_project,
                                          is_site_engineer=site_engineer)
    return add_project_member(world["project"].id, payload, db=db, current_user=world[actor])


# --- Who the administrator is offered --------------------------------------

def test_consultant_role_accounts_are_offered_as_consultants(db, world):
    offered = _offered(db, world, role=UserRole.CONSULTANT)
    assert world["pure_consultant"].id in offered
    assert world["external_engineer"].id in offered


def test_workers_are_not_offered_as_consultants(db, world):
    """They were, and the assignment that followed was rejected with 400."""
    assert world["worker"].id not in _offered(db, world, role=UserRole.CONSULTANT)
    assert world["worker"].id in _offered(db, world, role=UserRole.WORKER)


def test_contractor_engineers_are_not_offered_as_consultants(db, world):
    offered = _offered(db, world, role=UserRole.CONSULTANT)
    assert world["engineer"].id not in offered
    assert world["engineer"].id in _offered(db, world, role=UserRole.ENGINEER)


def test_unfiltered_list_includes_every_assignable_account(db, world):
    offered = _offered(db, world)
    assert {world["pure_consultant"].id, world["external_engineer"].id,
            world["engineer"].id, world["worker"].id} <= offered


# --- What the assignment endpoint accepts -----------------------------------

def test_project_wide_consultant_can_be_assigned(db, world):
    member = _assign(db, world, "pure_consultant", UserRole.CONSULTANT)
    assert member.role_on_project == UserRole.CONSULTANT
    assert member.is_site_engineer is False


def test_external_consultant_engineer_can_be_assigned(db, world):
    member = _assign(db, world, "external_engineer", UserRole.CONSULTANT)
    assert member.role_on_project == UserRole.CONSULTANT


def test_multiple_consultants_can_serve_on_one_project(db, world):
    _assign(db, world, "pure_consultant", UserRole.CONSULTANT)
    _assign(db, world, "external_engineer", UserRole.CONSULTANT)
    consultants = db.query(ProjectMember).filter(
        ProjectMember.project_id == world["project"].id,
        ProjectMember.role_on_project == UserRole.CONSULTANT,
        ProjectMember.is_active == True,  # noqa: E712
    ).count()
    assert consultants == 2


def test_engineer_scoped_assignment_keeps_the_site_engineer_flag(db, world):
    member = _assign(db, world, "engineer", UserRole.ENGINEER, site_engineer=True)
    assert member.role_on_project == UserRole.ENGINEER
    assert member.is_site_engineer is True


# --- The validation that must stay -----------------------------------------

def test_role_mismatch_is_still_rejected(db, world):
    with pytest.raises(HTTPException) as error:
        _assign(db, world, "worker", UserRole.CONSULTANT)
    assert error.value.status_code == 400


def test_site_engineer_flag_on_a_consultant_is_still_rejected(db, world):
    """The server rule stays; the UI no longer sends a stale flag into it."""
    with pytest.raises(HTTPException) as error:
        _assign(db, world, "external_engineer", UserRole.CONSULTANT, site_engineer=True)
    assert error.value.status_code == 400


def test_assigning_the_same_consultant_twice_conflicts(db, world):
    _assign(db, world, "pure_consultant", UserRole.CONSULTANT)
    with pytest.raises(HTTPException) as error:
        _assign(db, world, "pure_consultant", UserRole.CONSULTANT)
    assert error.value.status_code == 409


def test_already_assigned_people_drop_out_of_the_offered_list(db, world):
    _assign(db, world, "pure_consultant", UserRole.CONSULTANT)
    assert world["pure_consultant"].id not in _offered(db, world, role=UserRole.CONSULTANT)


def test_a_project_manager_cannot_staff_someone_elses_project(db, world):
    outsider = User(full_name="OtherPm", email=f"otherpm-{world['suffix']}@test.local",
                    hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    db.add(outsider)
    db.flush()
    world["outsider"] = outsider
    with pytest.raises(HTTPException) as error:
        _assign(db, world, "pure_consultant", UserRole.CONSULTANT, actor="outsider")
    assert error.value.status_code == 403


def test_inactive_accounts_are_neither_offered_nor_assignable(db, world):
    world["pure_consultant"].status = UserStatus.INACTIVE
    db.flush()
    assert world["pure_consultant"].id not in _offered(db, world, role=UserRole.CONSULTANT)
    with pytest.raises(HTTPException) as error:
        _assign(db, world, "pure_consultant", UserRole.CONSULTANT)
    assert error.value.status_code == 400
