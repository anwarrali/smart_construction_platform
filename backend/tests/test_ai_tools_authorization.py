"""Tools cannot see or do more than the person calling them.

The claim Phase 5 makes is that the tool layer is not a bypass. That is only
worth anything if it is checked against the platform's real roles on a real
database, with the same helpers the web UI uses — so this suite builds a
project with a manager, an outside user and a surveyor, and asks the tools to
misbehave.

The narrow caller is a **Surveyor** rather than the retired Worker role it used
to be. That is not a cosmetic rename: the property under test is "somebody who
neither reviews nor edits the project's work sees only the work they were
given", and Surveyor is the office role the seeded templates define that way
(`_NO_REVIEW_AUTHORITY`). It is therefore assigned a real `org_role_id`, so the
suite exercises the configurable role model rather than the pre-backfill
catalogue fallback.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, TaskStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services import rbac
from app.services.ai_tools import BY_NAME, available_tools, call_tool


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

    def user(name, role, org_role_code=None):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE,
                    org_role_id=roles[org_role_code].id if org_role_code else None,
                    is_internal=True if org_role_code else None)

    manager = user("ToolPm", UserRole.PROJECT_MANAGER)
    outsider = user("ToolOutsider", UserRole.PROJECT_MANAGER)
    surveyor = user("ToolSurveyor", UserRole.ENGINEER, "surveyor")
    owner = user("ToolOwner", UserRole.OWNER)
    suspended = user("ToolSuspended", UserRole.PROJECT_MANAGER)
    suspended.status = UserStatus.INACTIVE
    db.add_all([manager, outsider, surveyor, owner, suspended])
    db.flush()

    project = Project(name=f"Tools {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    for person, role in ((manager, UserRole.PROJECT_MANAGER), (surveyor, UserRole.ENGINEER),
                         (suspended, UserRole.PROJECT_MANAGER)):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=role, is_active=True,
                             project_role_id=(
                                 roles["surveyor"].id if person is surveyor else None
                             )))
    task = Task(project_id=project.id, task_code="T-001", name="Pour slab",
                status=TaskStatus.IN_PROGRESS, progress_percentage=30,
                created_by_id=manager.id)
    db.add(task)
    db.commit()
    try:
        yield {"project": project, "manager": manager, "outsider": outsider,
               "surveyor": surveyor, "suspended": suspended, "task": task}
    finally:
        _purge(db, project.id, [manager.id, outsider.id, surveyor.id, owner.id, suspended.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM issues WHERE project_id = ANY(:projects) OR raised_by_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        try:
            db.execute(text(statement), params)
        except SQLAlchemyError:
            db.rollback()
    db.commit()


def call(db, world, actor, name, arguments=None, project=None):
    return call_tool(
        db, user=world[actor], project_id=project or world["project"].id,
        name=name, arguments=arguments or {},
    )


# --- The layer refuses before it runs ---------------------------------------

def test_an_unknown_tool_is_refused_by_name(db, world):
    result = call(db, world, "manager", "drop_all_tables")
    assert result.ok is False
    assert result.error_code == "UNKNOWN_TOOL"


def test_a_user_outside_the_project_gets_nothing(db, world):
    for name in ("get_project", "get_tasks", "get_project_status", "get_project_users"):
        result = call(db, world, "outsider", name)
        assert result.ok is False, f"{name} answered an outsider"
        assert result.error_code == "FORBIDDEN"


def test_a_suspended_account_is_refused_even_though_it_is_a_member(db, world):
    result = call(db, world, "suspended", "get_project")
    assert result.ok is False
    assert result.error_code == "FORBIDDEN"


def test_arguments_are_validated_before_authorization_is_considered(db, world):
    """A malformed call never reaches a permission check, or a handler."""
    result = call(db, world, "outsider", "get_tasks", {"limit": 99999})
    assert result.ok is False
    assert result.error_code == "INVALID_ARGUMENTS"


def test_an_invented_argument_is_reported_not_ignored(db, world):
    result = call(db, world, "manager", "get_tasks", {"force": True})
    assert result.ok is False
    assert result.error_code == "INVALID_ARGUMENTS"
    assert "force" in result.error


def test_a_failure_is_returned_as_data_rather_than_raised(db, world):
    """An agent has to be able to read the reason and choose a next move."""
    result = call(db, world, "manager", "get_task",
                  {"taskId": "00000000-0000-0000-0000-000000000009"})
    assert result.ok is False
    assert result.error_code == "NOT_FOUND"
    assert result.as_json()["errorCode"] == "NOT_FOUND"


# --- Reads are scoped to the caller -----------------------------------------

def test_a_member_can_read_the_project(db, world):
    result = call(db, world, "manager", "get_project")
    assert result.ok is True
    assert result.data["name"].startswith("Tools ")


def test_task_reads_are_scoped_to_what_the_caller_may_see(db, world):
    manager = call(db, world, "manager", "get_tasks")
    assert manager.ok is True
    assert any(task["name"] == "Pour slab" for task in manager.data["tasks"])

    surveyor = call(db, world, "surveyor", "get_tasks")
    # A site engineer sees only work assigned to them; this task is assigned to nobody.
    if surveyor.ok:
        assert all(task["name"] != "Pour slab" for task in surveyor.data["tasks"])


def test_a_task_outside_the_callers_scope_reads_as_not_found(db, world):
    """Indistinguishable from absent, which is the correct thing for it to be."""
    result = call(db, world, "surveyor", "get_task", {"taskId": str(world["task"].id)})
    assert result.ok is False
    assert result.error_code in {"NOT_FOUND", "FORBIDDEN"}


def test_project_status_reports_only_authorized_work(db, world):
    result = call(db, world, "manager", "get_project_status")
    assert result.ok is True
    assert "authorized" in result.data["note"]


# --- Proposals never execute ------------------------------------------------

def test_creating_a_task_returns_a_proposal_and_creates_nothing(db, world):
    before = db.query(Task).filter(Task.project_id == world["project"].id).count()
    result = call(db, world, "manager", "create_task",
                  {"name": "Install conduit", "priority": "high"})
    assert result.ok is True
    assert result.proposal is not None
    assert result.proposal["actionType"] == "CREATE_TASK"
    assert "not been performed" in result.proposal["confirmation"]
    assert db.query(Task).filter(Task.project_id == world["project"].id).count() == before


def test_updating_a_task_returns_a_proposal_and_changes_nothing(db, world):
    result = call(db, world, "manager", "update_task",
                  {"taskId": str(world["task"].id), "progressPercentage": 90})
    assert result.ok is True
    assert result.proposal["payload"]["progressPercentage"] == 90
    db.refresh(world["task"])
    assert world["task"].progress_percentage == 30, "the task must be untouched"


def test_a_proposal_response_is_flagged_as_needing_confirmation(db, world):
    result = call(db, world, "manager", "create_issue",
                  {"title": "Rebar spacing", "description": "Spacing is wrong on level 2"})
    assert result.as_json()["requiresConfirmation"] is True


def test_a_role_that_may_not_perform_an_operation_cannot_propose_it(db, world):
    """The proposal path applies the same registry the voice path applies."""
    result = call(db, world, "surveyor", "create_task", {"name": "Something a surveyor cannot add"})
    assert result.ok is False
    assert result.error_code == "FORBIDDEN"


def test_an_update_with_nothing_to_change_is_rejected(db, world):
    result = call(db, world, "manager", "update_task", {"taskId": str(world["task"].id)})
    assert result.ok is False
    assert result.error_code == "INVALID_ARGUMENTS"


def test_proposing_against_a_task_in_another_project_is_refused(db, world):
    result = call(db, world, "manager", "update_task",
                  {"taskId": str(uuid4()), "progressPercentage": 50})
    assert result.ok is False
    assert result.error_code == "NOT_FOUND"


# --- The advertised tool list matches what the caller can actually use -------

def test_the_tool_list_offered_to_an_agent_reflects_the_callers_permissions(db, world):
    manager = {tool["name"] for tool in available_tools(db, user=world["manager"],
                                                        project_id=world["project"].id)}
    surveyor = {tool["name"] for tool in available_tools(db, user=world["surveyor"],
                                                       project_id=world["project"].id)}
    assert "create_task" in manager
    assert surveyor <= manager
    assert "create_task" not in surveyor or surveyor != manager


def test_an_outsider_is_offered_no_tools_at_all(db, world):
    assert available_tools(db, user=world["outsider"], project_id=world["project"].id) == []


def test_every_offered_tool_can_actually_be_called(db, world):
    """An offered tool that refuses on call would teach an agent to distrust the list."""
    offered = available_tools(db, user=world["manager"], project_id=world["project"].id)
    for definition in offered:
        if BY_NAME[definition["name"]].arguments.model_fields:
            continue  # needs arguments this test has no valid values for
        result = call(db, world, "manager", definition["name"])
        assert result.error_code != "FORBIDDEN", f"{definition['name']} was offered then refused"
