"""Who may write a project milestone.

The three write endpoints had no test of any kind, and were the last
authorization decisions in the platform read off the retired `UserRole` enum:
`is_admin(user.role) or user.id == project.project_manager_id`. They now require
`schedule.edit`, which is what the rest of the product already called this — the
milestones route sits inside the frontend's `schedule.view` guard beside the
Gantt, and reading a milestone already required the schedule permission.

**These tests exercise the endpoint functions, not `has_permission`.** The RBAC
equivalence gate compares permission *resolution* for each (user, project) pair;
it says nothing about which code an endpoint requires, so it would report PASS
whatever this migration did. Endpoint-level tests are the only thing that can
prove this change, which is why they assert against `create_milestone`,
`update_milestone` and `delete_milestone` directly.

The delegation case is deliberate. `schedule.edit` is `office_only` but not
`never_external`, so an administrator can grant it to an external participant on
one project — an office asking its main contractor to maintain the construction
programme is describing a real arrangement. `test_an_external_participant_...`
pins that as intended behaviour rather than leaving it to be discovered.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.milestones import create_milestone, delete_milestone, update_milestone
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, TaskStatus, UserRole, UserStatus
from app.models.milestone import Milestone
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.schemas.milestone import MilestoneCreate, MilestoneUpdate
from app.services.authorization import has_permission

CODE = "schedule.edit"


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
    """One project with a full cast, and a second project nobody here is on."""
    suffix = uuid4().hex[:10]

    def user(name, role, affiliation=None):
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@test.local",
            hashed_password="x", role=role, status=UserStatus.ACTIVE,
            engineer_affiliation=affiliation,
        )
        db.add(person)
        return person

    people = {
        "admin": user("MsAdmin", UserRole.ADMIN),
        "manager": user("MsPm", UserRole.PROJECT_MANAGER),
        "engineer": user("MsEngineer", UserRole.ENGINEER, "internal_engineer"),
        "consultant": user("MsConsultant", UserRole.ENGINEER, "external_consultant"),
        "owner": user("MsOwner", UserRole.OWNER),
        "contractor": user("MsContractor", UserRole.ENGINEER, "main_contractor"),
        "stranger": user("MsStranger", UserRole.PROJECT_MANAGER),
    }
    db.flush()

    project = Project(
        name=f"Milestone Project {suffix}", status=ProjectStatus.ACTIVE,
        owner_id=people["owner"].id, project_manager_id=people["manager"].id,
    )
    # A second project, managed by the stranger, so "cannot touch another
    # project's milestone" is tested against somebody with real authority
    # somewhere rather than somebody with none anywhere.
    elsewhere = Project(
        name=f"Elsewhere {suffix}", status=ProjectStatus.ACTIVE,
        owner_id=people["owner"].id, project_manager_id=people["stranger"].id,
    )
    db.add_all([project, elsewhere])
    db.flush()
    for person in ("manager", "engineer", "consultant", "contractor"):
        db.add(ProjectMember(
            project_id=project.id, user_id=people[person].id,
            role_on_project=people[person].role, is_active=True,
        ))
    db.add(ProjectMember(
        project_id=elsewhere.id, user_id=people["stranger"].id,
        role_on_project=people["stranger"].role, is_active=True,
    ))
    db.flush()

    task = Task(
        project_id=project.id, name=f"Milestone task {suffix}",
        task_code=f"M-{suffix[:6].upper()}", status=TaskStatus.IN_PROGRESS,
        created_by_id=people["manager"].id,
    )
    db.add(task)
    db.flush()

    milestone = Milestone(
        project_id=project.id, milestone_code="MS-001", name=f"Existing {suffix}",
        planned_date=date.today() + timedelta(days=30),
        created_by_id=people["manager"].id, tasks=[task],
    )
    db.add(milestone)
    db.commit()

    people.update({"project": project, "elsewhere": elsewhere,
                   "task": task, "milestone": milestone, "db": db})
    user_ids = [p.id for p in people.values() if isinstance(p, User)]
    project_ids = [project.id, elsewhere.id]
    try:
        yield people
    finally:
        # The endpoints commit, so rolling back is not enough.
        db.rollback()
        params = {"projects": project_ids, "users": user_ids}
        for statement in (
            "DELETE FROM user_permission_overrides WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
            "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
            "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
            "UPDATE tasks SET milestone_id = NULL WHERE project_id = ANY(:projects)",
            "DELETE FROM milestones WHERE project_id = ANY(:projects)",
            "DELETE FROM tasks WHERE project_id = ANY(:projects)",
            "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
            "DELETE FROM projects WHERE id = ANY(:projects)",
            "DELETE FROM users WHERE id = ANY(:users)",
        ):
            db.execute(text(statement), params)
        db.commit()


def _create_payload(world, name="New milestone"):
    return MilestoneCreate(
        project_id=world["project"].id, name=name,
        planned_date=date.today() + timedelta(days=60), task_ids=[],
    )


def _grant(db, user, project_id, allowed=True):
    db.add(UserPermissionOverride(
        user_id=user.id, permission_code=CODE, allowed=allowed, project_id=project_id,
    ))
    db.flush()


# --- who may write -----------------------------------------------------------

def test_an_administrator_can_create_update_and_delete(world):
    db = world["db"]
    created = create_milestone(data=_create_payload(world), db=db, current_user=world["admin"])
    assert created["name"] == "New milestone"

    updated = update_milestone(
        milestone_id=world["milestone"].id, data=MilestoneUpdate(name="Renamed"),
        db=db, current_user=world["admin"],
    )
    assert updated["name"] == "Renamed"

    result = delete_milestone(
        milestone_id=world["milestone"].id, db=db, current_user=world["admin"],
    )
    assert "deleted" in result["message"].lower()


def test_the_assigned_project_manager_can_create_update_and_delete(world):
    """The behaviour the retired check existed to allow, preserved."""
    db = world["db"]
    manager = world["manager"]
    assert has_permission(db, manager, CODE, world["project"].id)

    create_milestone(data=_create_payload(world, "PM milestone"), db=db, current_user=manager)
    update_milestone(
        milestone_id=world["milestone"].id, data=MilestoneUpdate(name="PM renamed"),
        db=db, current_user=manager,
    )
    delete_milestone(milestone_id=world["milestone"].id, db=db, current_user=manager)


def test_a_member_granted_schedule_edit_can_write(world):
    """What the retired check made impossible.

    An engineer on the project, given `schedule.edit` by an administrator, could
    not touch a milestone before: the check asked whether they were an
    administrator or the assigned manager, and no configuration changed that.
    """
    db = world["db"]
    engineer = world["engineer"]
    assert not has_permission(db, engineer, CODE, world["project"].id)

    _grant(db, engineer, world["project"].id)
    assert has_permission(db, engineer, CODE, world["project"].id)

    created = create_milestone(
        data=_create_payload(world, "Engineer milestone"), db=db, current_user=engineer,
    )
    assert created["name"] == "Engineer milestone"


# --- who may not -------------------------------------------------------------

@pytest.mark.parametrize("who", ["engineer", "owner", "consultant"])
def test_reading_the_schedule_is_not_writing_it(world, who):
    """`schedule.view` reaches the page; it does not reach these endpoints.

    The owner holds `schedule.view` by default and the consultant is office
    staff — neither holds `schedule.edit`, and the frontend renders the buttons
    to both, so this is the check that actually stops them.
    """
    db = world["db"]
    person = world[who]
    assert not has_permission(db, person, CODE, world["project"].id)

    with pytest.raises(HTTPException) as refusal:
        create_milestone(data=_create_payload(world), db=db, current_user=person)
    assert refusal.value.status_code == 403


def test_a_consultant_can_write_once_granted(world):
    """Office staff, so the grant is allowed to reach them."""
    db = world["db"]
    consultant = world["consultant"]
    _grant(db, consultant, world["project"].id)

    created = create_milestone(
        data=_create_payload(world, "Consultant milestone"), db=db, current_user=consultant,
    )
    assert created["name"] == "Consultant milestone"


def test_an_external_participant_follows_the_schedule_edit_delegation_rule(world):
    """Deliberate, and pinned so it is not mistaken for a hole.

    `schedule.edit` is `office_only` but not `never_external`: an external
    participant never inherits it from a role, and an administrator may still
    grant it to one named person on one named project. An office asking its main
    contractor to maintain the programme is describing a real arrangement.

    Contrast `project.delete` and `project.manage_members`, which are
    `never_external` and refuse the same grant outright.
    """
    db = world["db"]
    contractor = world["contractor"]
    # Not inherited.
    assert not has_permission(db, contractor, CODE, world["project"].id)

    with pytest.raises(HTTPException):
        create_milestone(data=_create_payload(world), db=db, current_user=contractor)

    # Delegable by an explicit administrator decision.
    _grant(db, contractor, world["project"].id)
    assert has_permission(db, contractor, CODE, world["project"].id)
    created = create_milestone(
        data=_create_payload(world, "Contractor milestone"), db=db, current_user=contractor,
    )
    assert created["name"] == "Contractor milestone"


def test_a_manager_of_another_project_cannot_touch_this_milestone(world):
    """Project scope, not permission level, is what refuses them.

    The stranger manages their own project and holds `schedule.edit` there, so
    what stops them here is that `has_permission` re-checks project access for
    a project-scoped code.
    """
    db = world["db"]
    stranger = world["stranger"]
    assert has_permission(db, stranger, CODE, world["elsewhere"].id)
    assert not has_permission(db, stranger, CODE, world["project"].id)

    with pytest.raises(HTTPException) as refusal:
        update_milestone(
            milestone_id=world["milestone"].id, data=MilestoneUpdate(name="Hijacked"),
            db=db, current_user=stranger,
        )
    assert refusal.value.status_code == 403

    with pytest.raises(HTTPException) as refusal:
        delete_milestone(milestone_id=world["milestone"].id, db=db, current_user=stranger)
    assert refusal.value.status_code == 403

    db.rollback()
    assert db.get(Milestone, world["milestone"].id) is not None


def test_a_revoked_grant_takes_the_ability_away_again(world):
    """The point of making it configurable: it can be withdrawn."""
    db = world["db"]
    engineer = world["engineer"]
    _grant(db, engineer, world["project"].id, allowed=False)
    assert not has_permission(db, engineer, CODE, world["project"].id)

    with pytest.raises(HTTPException) as refusal:
        delete_milestone(milestone_id=world["milestone"].id, db=db, current_user=engineer)
    assert refusal.value.status_code == 403


# --- behaviour that must survive the authorization change --------------------

def test_deleting_a_milestone_still_unlinks_its_tasks_without_deleting_them(world):
    """The business rule the endpoint's own message promises.

    Worth asserting here because the authorization change sits two lines above
    the unlink, and a mistake in either would look like the other.
    """
    db = world["db"]
    task_id = world["task"].id
    milestone_id = world["milestone"].id
    assert db.get(Task, task_id).milestone_id == milestone_id

    result = delete_milestone(milestone_id=milestone_id, db=db, current_user=world["admin"])

    assert "preserved" in result["message"].lower()
    assert db.get(Milestone, milestone_id) is None
    surviving = db.get(Task, task_id)
    assert surviving is not None, "the linked task was deleted along with the milestone"
    assert surviving.milestone_id is None


def test_a_missing_milestone_is_not_found_rather_than_forbidden(world):
    """Order preserved: the milestone lookup still runs before the permission
    check, so an administrator asking for one that does not exist is told so."""
    with pytest.raises(HTTPException) as refusal:
        update_milestone(
            milestone_id=uuid4(), data=MilestoneUpdate(name="x"),
            db=world["db"], current_user=world["admin"],
        )
    assert refusal.value.status_code == 404
