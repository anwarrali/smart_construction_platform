"""The endpoints migrated onto the central permission resolver.

Each test answers the three questions the migration has to get right:

  * did the default behaviour survive the move (nobody gained or lost access);
  * does an administrator's configuration actually reach the endpoint;
  * can a granted permission reach past project membership or an ownership
    restriction — which it must never do.

The last one is the point of `manageable_project`: the capability became
configurable, the "a project manager may only manage their own project" rule and
the project-access check did not.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.projects import add_project_member, update_project
from app.api.users import list_users
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserStatus
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.project import ProjectMemberAssignExisting, ProjectUpdate
from app.services.authorization import has_permission, manageable_project
from tests.office_roles import with_office_role


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

    def user(name, role):
        person = with_office_role(db, User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                                           hashed_password="x", status=UserStatus.ACTIVE), role)
        db.add(person)
        return person

    people = {
        "admin": user("MigAdmin", "org_admin"),
        "manager": user("MigPm", "project_manager"),
        "other_manager": user("MigOtherPm", "project_manager"),
        "owner": user("MigOwner", "client_representative"),
        # Office staff. `project.manage_members` is `never_external`, so the
        # contractor-side engineer below can never hold it however it is
        # granted — which is the point of `test_a_grant_cannot_reach_an_external_member`.
        "engineer": user("MigEngineer", "engineer"),
        "contractor": user("MigContractor", "contractor_representative"),
        "outsider": user("MigOutsider", "contractor_representative"),
        "candidate": user("MigCandidate", "contractor_representative"),
    }
    db.flush()

    project = Project(name=f"Migration Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    other = Project(name=f"Other Project {suffix}", status=ProjectStatus.ACTIVE,
                    owner_id=people["owner"].id, project_manager_id=people["other_manager"].id)
    db.add_all([project, other])
    db.flush()
    for person in (people["manager"], people["engineer"], people["contractor"]):
        db.add(ProjectMember(project_id=project.id, user_id=person.id, is_active=True))
    db.flush()
    people["project"] = project
    people["other_project"] = other
    people["db"] = db
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id, other.id], user_ids)


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


def _grant(db, user, code, allowed=True, project_id=None):
    db.add(UserPermissionOverride(user_id=user.id, permission_code=code,
                                  allowed=allowed, project_id=project_id))
    db.flush()


def _configure_role(db, user, code, allowed):
    """Change what the role this person holds may do, on the live mechanism.

    The role is **copied first**, into a row belonging to this test alone, and
    the copy is what gets edited. Editing the seeded template in place would
    outlive the test — the templates are shared by every office and by every
    other test in the run, and `set_role_permission` writes to the database, so
    one test granting `schedule.edit` to Engineer would hand it to every
    engineer in every later test. That is the same reason
    `organization._editable_role` copies a template into an office before
    letting it be changed.
    """
    from app.models.rbac import Role, RolePermission
    from app.services import rbac
    from uuid import uuid4 as _uuid4

    source = rbac.get_role(db, user.org_role_id)
    assert source is not None, "the fixture should have given this account a role"
    copy = Role(
        organization_id=source.organization_id, code=f"{source.code}-{_uuid4().hex[:8]}",
        name_en=source.name_en, scope=source.scope,
        is_internal_only=source.is_internal_only, is_system=False,
        rank=source.rank,
    )
    db.add(copy)
    db.flush()
    for existing in rbac.role_permission_codes(db, source.id):
        db.add(RolePermission(role_id=copy.id, permission_code=existing, allowed=True))
    db.flush()
    user.org_role_id = copy.id
    rbac.set_role_permission(db, role=copy, code=code, allowed=allowed)
    db.flush()


# --- platform.manage_users --------------------------------------------------

def test_managing_users_still_belongs_to_administrators(db, world):
    assert list_users(db=db, current_user=world["admin"]) is not None
    assert not has_permission(db, world["manager"], "platform.manage_users")


def test_granting_manage_users_reaches_the_endpoint(db, world):
    _grant(db, world["manager"], "platform.manage_users")
    assert has_permission(db, world["manager"], "platform.manage_users")


def test_an_administrator_cannot_lose_manage_users(db, world):
    """It is admin-locked: revoking it would lock the platform out of itself."""
    _grant(db, world["admin"], "platform.manage_users", allowed=False)
    assert has_permission(db, world["admin"], "platform.manage_users")


# --- project.manage_members -------------------------------------------------

def test_the_assigned_manager_can_still_staff_their_project(db, world):
    member = add_project_member(
        world["project"].id,
        ProjectMemberAssignExisting(user_id=world["candidate"].id),
        db=db, current_user=world["manager"])
    assert member.user_id == world["candidate"].id and member.is_active


def test_revoking_manage_members_from_the_role_blocks_the_endpoint(db, world):
    _configure_role(db, world["manager"], "project.manage_members", False)
    with pytest.raises(HTTPException) as error:
        add_project_member(
            world["project"].id,
            ProjectMemberAssignExisting(user_id=world["candidate"].id),
            db=db, current_user=world["manager"])
    assert error.value.status_code == 403


def test_a_grant_does_not_let_a_manager_staff_someone_elses_project(db, world):
    """The ownership restriction outranks the configuration."""
    _grant(db, world["manager"], "project.manage_members")
    with pytest.raises(HTTPException) as error:
        manageable_project(db, world["manager"], world["other_project"].id, "project.manage_members")
    assert error.value.status_code == 403


def test_a_grant_does_not_let_a_non_member_staff_a_project(db, world):
    """Project membership outranks the configuration."""
    _grant(db, world["outsider"], "project.manage_members")
    with pytest.raises(HTTPException) as error:
        manageable_project(db, world["outsider"], world["project"].id, "project.manage_members")
    assert error.value.status_code == 403


def test_a_granted_member_may_staff_the_project_they_belong_to(db, world):
    """The configuration does work — once membership and ownership are satisfied."""
    _grant(db, world["engineer"], "project.manage_members")
    assert manageable_project(db, world["engineer"], world["project"].id,
                              "project.manage_members").id == world["project"].id


def test_a_project_scoped_grant_does_not_reach_another_project(db, world):
    _grant(db, world["engineer"], "project.manage_members", project_id=world["project"].id)
    assert has_permission(db, world["engineer"], "project.manage_members", world["project"].id)
    assert not has_permission(db, world["engineer"], "project.manage_members", world["other_project"].id)


# --- project.edit -----------------------------------------------------------

def test_editing_project_setup_still_works_for_an_administrator(db, world):
    updated = update_project(world["project"].id, ProjectUpdate(location="Ramallah"),
                             db=db, current_user=world["admin"])
    assert updated.location == "Ramallah"


def test_project_edit_can_be_revoked_from_administrators_role_wide(db, world):
    """`project.edit` is not admin-locked, so it is genuinely configurable."""
    _configure_role(db, world["admin"], "project.edit", False)
    with pytest.raises(HTTPException) as error:
        update_project(world["project"].id, ProjectUpdate(location="Nablus"),
                       db=db, current_user=world["admin"])
    assert error.value.status_code == 403


def test_a_deactivated_account_holds_none_of_the_migrated_permissions(db, world):
    world["manager"].status = UserStatus.SUSPENDED
    db.flush()
    for code in ("project.manage_members", "project.edit", "platform.manage_users",
                 "site_report.submit", "design_change.approve", "ai.review_insight"):
        assert not has_permission(db, world["manager"], code, world["project"].id)


# --- the codes the migration relies on exist --------------------------------

def test_the_migrated_codes_are_held_by_the_roles_that_had_the_behaviour(db, world):
    """Making a check configurable must not widen it.

    Office authority — setting up projects, staffing them, administering
    accounts — stays with office administration and project leadership. An
    external role that lists `design_change.approve` never exercises it: the
    external ceiling strips it at resolution (test_work_scope_and_routing.py).
    """
    from app.core.role_templates import LEGACY_CONSULTANT_TEMPLATE, TEMPLATES

    def holders(code):
        return {t.code for t in (*TEMPLATES, LEGACY_CONSULTANT_TEMPLATE) if code in t.permissions()}

    assert holders("project.edit") == {"org_admin", "office_director", "technical_director"}
    assert holders("project.manage_members") == {
        "org_admin", "office_director", "technical_director", "project_manager"}
    assert holders("platform.manage_users") == {"org_admin", "office_director"}
    assert "client_representative" not in holders("site_report.submit")
    assert not {"client_representative", "office_staff"} & holders("design_change.approve")


def test_every_migrated_code_is_in_the_catalogue(db, world):
    from app.core.permission_catalogue import is_known
    for code in ("platform.manage_users", "platform.create_project", "project.manage_members",
                 "project.edit", "site_report.submit", "design_change.approve",
                 "ai.review_insight", "ai.promote_insight"):
        assert is_known(code), code


def test_a_grant_cannot_reach_an_external_member(db, world):
    """The ceiling the office cannot configure around.

    `project.manage_members` is `never_external`: running the office's project
    team is the office's own job. A contractor's engineer is on this project and
    has been granted the permission outright, and still cannot staff it — the
    grant is removed at resolution, after every override, so a mistake in
    Access Control cannot become a breach.
    """
    _grant(db, world["contractor"], "project.manage_members")
    assert not has_permission(
        db, world["contractor"], "project.manage_members", world["project"].id
    )
    with pytest.raises(HTTPException) as error:
        manageable_project(db, world["contractor"], world["project"].id,
                           "project.manage_members")
    assert error.value.status_code == 403
