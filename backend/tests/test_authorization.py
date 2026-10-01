"""Configurable permissions must be real: enforced on the server, least
privilege by default, and impossible to bypass by talking to the API directly.

These tests exercise the resolver and the endpoint guards against the real
database. They also pin the rule that installing the permission layer did not
change who could do what: the defaults must still match the roles the
application shipped with.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.permission_catalogue import BY_CODE, CATALOGUE
from app.core.role_templates import LEGACY_CONSULTANT_TEMPLATE, TEMPLATES
from app.db.database import SessionLocal
from app.models.enums import ConsultantApprovalMode, ProjectStatus, UserStatus
from app.models.permission import ConsultantEngineerScope, UserPermissionOverride
from app.models.project import Project, ProjectConsultantReviewer, ProjectMember
from app.models.task import Task
from app.models.step_up import StepUpGrant
from app.models.user import User
from app.services.authorization import (
    consultant_covers_engineers, effective_permissions, has_permission, require,
)
from app.services.consultant_approval_service import can_consultant_review_task
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
    """One project, two consultants with different remits, two engineers."""
    suffix = uuid4().hex[:10]

    def user(name, role):
        return with_office_role(db, User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                                         hashed_password="x", status=UserStatus.ACTIVE), role)

    admin = user("Admin", "org_admin")
    manager = user("Manager", "project_manager")
    # Office staff, for the role-configuration tests. `civil` below is
    # contractor-side, so an `office_only` code granted to its role is stripped
    # at resolution — correct, and the wrong subject for "can an administrator
    # configure a role".
    office_engineer = user("OfficeEng", "engineer")
    civil = user("CivilEng", "contractor_representative")
    electrical = user("ElecEng", "contractor_representative")
    consultant_a = user("ConsultantA", "senior_engineer")
    consultant_b = user("ConsultantB", "senior_engineer")
    owner = user("Client", "client_representative")
    outsider = user("Outsider", "contractor_representative")
    people = [admin, manager, office_engineer, civil, electrical, consultant_a, consultant_b, owner, outsider]
    db.add_all(people)
    db.flush()

    project = Project(name=f"RBAC Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id,
                      consultant_approval_mode=ConsultantApprovalMode.DISCIPLINE_BASED_REVIEW)
    db.add(project)
    db.flush()

    for person, discipline in (
        (office_engineer, "civil"),
        (civil, "civil"),
        (electrical, "electrical"),
        (consultant_a, "civil"),
        (consultant_b, "electrical"),
    ):
        db.add(ProjectMember(project_id=project.id, user_id=person.id, project_discipline=discipline,
                             is_active=True))
    db.flush()

    # Two consultants, each responsible for a different discipline.
    db.add(ProjectConsultantReviewer(project_id=project.id, user_id=consultant_a.id, discipline="civil"))
    db.add(ProjectConsultantReviewer(project_id=project.id, user_id=consultant_b.id, discipline="electrical"))
    db.flush()

    ids = [person.id for person in people]
    try:
        yield {"db": db, "project": project, "admin": admin, "manager": manager,
               "office_engineer": office_engineer,
               "civil": civil, "electrical": electrical, "consultantA": consultant_a,
               "consultantB": consultant_b, "owner": owner, "outsider": outsider}
    finally:
        _purge(db, project.id, ids)


def _purge(db, project_id, user_ids):
    db.rollback()
    for statement in (
        "DELETE FROM consultant_engineer_scopes WHERE project_id = :project",
        "DELETE FROM user_permission_overrides WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = :project)",
        "DELETE FROM tasks WHERE project_id = :project",
        "DELETE FROM project_consultant_reviewers WHERE project_id = :project",
        "DELETE FROM notifications WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = :project OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = :project",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), {"project": project_id, "users": list(user_ids)})
    db.commit()


def _task(world, discipline, assignees):
    task = Task(project_id=world["project"].id, task_code=f"T-{uuid4().hex[:6]}",
                name="Reinforcement", discipline=discipline,
                created_by_id=world["manager"].id, review_required=True)
    task.assignees = assignees
    world["db"].add(task)
    world["db"].flush()
    return task


# --- defaults ---------------------------------------------------------------

def test_the_catalogue_defaults_match_the_roles_the_app_shipped_with(world):
    """Installing this layer must not silently change anybody's access."""
    admin = effective_permissions(world["db"], world["admin"])
    assert "platform.manage_permissions" in admin
    assert "platform.manage_users" in admin

    manager = effective_permissions(world["db"], world["manager"])
    assert {"task.create", "schedule.edit", "project.manage_members"} <= manager
    assert "platform.manage_permissions" not in manager

    engineer = effective_permissions(world["db"], world["civil"])
    assert "task.update_progress" in engineer
    assert {"platform.manage_users", "schedule.edit"} & engineer == set()

    client = effective_permissions(world["db"], world["owner"])
    assert "owner_request.create" in client
    assert "task.create" not in client


def test_a_deactivated_account_holds_no_permissions_at_all(world):
    world["manager"].status = UserStatus.SUSPENDED
    world["db"].flush()
    assert effective_permissions(world["db"], world["manager"]) == set()
    assert not has_permission(world["db"], world["manager"], "task.create", world["project"].id)


def test_an_unknown_permission_code_is_denied_rather_than_ignored(world):
    assert not has_permission(world["db"], world["admin"], "totally.made.up")


# --- overrides --------------------------------------------------------------


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


def test_an_administrator_can_grant_a_permission_to_a_whole_role(world):
    engineer = world["office_engineer"]
    assert not has_permission(world["db"], engineer, "schedule.edit", world["project"].id)
    _configure_role(world["db"], engineer, "schedule.edit", True)
    assert has_permission(world["db"], engineer, "schedule.edit", world["project"].id)

    # And the ceiling the configuration cannot lift: the same code, the same
    # role edit, a contractor-side member — still refused, because
    # `schedule.edit` is the office's own authority.
    assert not has_permission(world["db"], world["civil"], "schedule.edit", world["project"].id)


def test_an_administrator_can_revoke_a_default_permission_from_a_role(world):
    assert has_permission(world["db"], world["manager"], "task.create", world["project"].id)
    _configure_role(world["db"], world["manager"], "task.create", False)
    assert not has_permission(world["db"], world["manager"], "task.create", world["project"].id)


def test_a_person_level_grant_beats_the_role(world):
    world["db"].add(UserPermissionOverride(user_id=world["civil"].id, permission_code="issue.resolve", allowed=True))
    world["db"].flush()
    assert has_permission(world["db"], world["civil"], "issue.resolve", world["project"].id)
    # and only for that person
    assert not has_permission(world["db"], world["electrical"], "issue.resolve", world["project"].id)


def test_a_project_scoped_grant_does_not_leak_to_other_projects(world):
    other = Project(name=f"Other {uuid4().hex[:6]}", status=ProjectStatus.ACTIVE,
                    project_manager_id=world["manager"].id)
    world["db"].add(other)
    world["db"].flush()
    world["db"].add(UserPermissionOverride(
        user_id=world["civil"].id, project_id=world["project"].id,
        permission_code="task.create", allowed=True))
    world["db"].flush()

    assert has_permission(world["db"], world["civil"], "task.create", world["project"].id)
    assert not has_permission(world["db"], world["civil"], "task.create", other.id)
    world["db"].execute(text("DELETE FROM projects WHERE id = :id"), {"id": other.id})


def test_the_narrower_project_decision_wins_over_the_global_one(world):
    world["db"].add(UserPermissionOverride(
        user_id=world["manager"].id, permission_code="schedule.edit", allowed=True))
    world["db"].add(UserPermissionOverride(
        user_id=world["manager"].id, project_id=world["project"].id,
        permission_code="schedule.edit", allowed=False))
    world["db"].flush()
    assert not has_permission(world["db"], world["manager"], "schedule.edit", world["project"].id)


def test_a_granted_permission_still_requires_access_to_the_project(world):
    """A grant must never smuggle in access to a project you are not on."""
    world["db"].add(UserPermissionOverride(
        user_id=world["outsider"].id, permission_code="task.create", allowed=True))
    world["db"].flush()
    assert "task.create" in effective_permissions(world["db"], world["outsider"])
    assert not has_permission(world["db"], world["outsider"], "task.create", world["project"].id)


def test_an_administrator_cannot_be_stripped_of_administration(world):
    """Neither through the role's own rows nor through a per-person override."""
    from app.services import rbac
    admin_role = rbac.get_role(world["db"], world["admin"].org_role_id)
    rbac.set_role_permission(world["db"], role=admin_role, code="platform.manage_permissions", allowed=None)
    world["db"].add(UserPermissionOverride(
        user_id=world["admin"].id, permission_code="platform.manage_users", allowed=False))
    world["db"].flush()
    granted = effective_permissions(world["db"], world["admin"])
    assert "platform.manage_permissions" in granted
    assert "platform.manage_users" in granted


def test_require_raises_forbidden_for_a_denied_operation(world):
    with pytest.raises(HTTPException) as raised:
        require(world["db"], world["owner"], "task.create", world["project"].id)
    assert raised.value.status_code == 403


# --- consultants ------------------------------------------------------------

def test_each_consultant_reviews_only_their_own_discipline(world):
    civil_task = _task(world, "civil", [world["civil"]])
    electrical_task = _task(world, "electrical", [world["electrical"]])

    assert can_consultant_review_task(world["db"], world["consultantA"], civil_task)
    assert not can_consultant_review_task(world["db"], world["consultantA"], electrical_task)
    assert can_consultant_review_task(world["db"], world["consultantB"], electrical_task)
    assert not can_consultant_review_task(world["db"], world["consultantB"], civil_task)


def test_a_project_wide_consultant_reviews_every_discipline(world):
    """Case C: one consultant responsible for the whole project."""
    world["project"].consultant_approval_mode = ConsultantApprovalMode.CENTRALIZED_REVIEW
    world["db"].add(ProjectConsultantReviewer(
        project_id=world["project"].id, user_id=world["consultantA"].id, discipline=None))
    world["db"].flush()

    assert can_consultant_review_task(world["db"], world["consultantA"], _task(world, "civil", [world["civil"]]))
    assert can_consultant_review_task(world["db"], world["consultantA"], _task(world, "electrical", [world["electrical"]]))
    # The other consultant has no centralized assignment, so they hold nothing.
    assert not can_consultant_review_task(world["db"], world["consultantB"], _task(world, "civil", [world["civil"]]))


def test_a_consultant_can_be_limited_to_named_engineers(world):
    """Case D: division of work by person rather than by discipline."""
    world["db"].add(ConsultantEngineerScope(
        project_id=world["project"].id, consultant_user_id=world["consultantA"].id,
        engineer_user_id=world["civil"].id))
    world["db"].flush()

    mine = _task(world, "civil", [world["civil"]])
    not_mine = _task(world, "civil", [world["outsider"]])
    assert can_consultant_review_task(world["db"], world["consultantA"], mine)
    assert not can_consultant_review_task(world["db"], world["consultantA"], not_mine)


def test_no_engineer_scope_means_no_engineer_restriction(world):
    """Existing projects that never configure this must be unaffected."""
    assert consultant_covers_engineers(
        world["db"], world["project"].id, world["consultantA"].id, {world["outsider"].id})


def test_a_consultant_who_is_not_a_project_member_reviews_nothing(world):
    stranger = with_office_role(world["db"], User(
        full_name="Stranger", email=f"stranger-{uuid4().hex[:6]}@test.local",
        hashed_password="x", status=UserStatus.ACTIVE), "senior_engineer")
    world["db"].add(stranger)
    world["db"].flush()
    assert not can_consultant_review_task(
        world["db"], stranger, _task(world, "civil", [world["civil"]]))
    world["db"].execute(text("DELETE FROM users WHERE id = :id"), {"id": stranger.id})


# --- catalogue integrity ----------------------------------------------------

def test_every_permission_code_is_unique_and_grouped():
    codes = [item.code for item in CATALOGUE]
    assert len(codes) == len(set(codes))
    assert all(item.group and item.label and item.description for item in CATALOGUE)
    assert set(BY_CODE) == set(codes)


def test_only_office_administration_roles_hold_platform_administration():
    """Administering accounts and permissions belongs to the two office-administration templates."""
    for code in ("platform.manage_permissions", "platform.manage_users"):
        holders = {
            template.code for template in (*TEMPLATES, LEGACY_CONSULTANT_TEMPLATE)
            if code in template.permissions()
        }
        assert holders == {"org_admin", "office_director"}, (code, holders)


# --- direct API access ------------------------------------------------------
# Hiding a control in the browser is not protection. These call the endpoint
# functions the router exposes, exactly as a crafted HTTP request would.

def test_a_manager_cannot_read_the_permission_catalogue(world):
    from app.api.permissions import list_permissions
    with pytest.raises(HTTPException) as raised:
        list_permissions(db=world["db"], current_user=world["manager"])
    assert raised.value.status_code == 403


# Changing what a *role* may do is the organization API's job
# (`PUT /organization/roles/{id}/permissions`), and who may do it is covered in
# test_organization_api.py. The retired role-by-permission matrix that lived at
# `/access-control/roles` is gone.


def test_an_owner_cannot_grant_themselves_a_permission(world):
    from app.api.permissions import set_user_permission
    from app.schemas.permission import UserPermissionUpdate
    payload = UserPermissionUpdate(permissionCode="task.create", allowed=True)
    with pytest.raises(HTTPException) as raised:
        set_user_permission(world["owner"].id, payload, db=world["db"], current_user=world["owner"])
    assert raised.value.status_code == 403


def test_an_administrator_can_read_the_permission_catalogue(world):
    from app.api.permissions import list_permissions
    listed = list_permissions(db=world["db"], current_user=world["admin"])
    assert len(listed) == len(CATALOGUE)
    broadcast = next(item for item in listed if item["code"] == "message.broadcast")
    assert broadcast["office_only"] is True and broadcast["never_external"] is False
    assert all("default_roles" not in item for item in listed)


def test_scheduling_a_site_visit_is_refused_once_the_permission_is_revoked(world):
    """The endpoint guard, not just the resolver."""
    from datetime import datetime, timedelta, timezone
    from app.api.collaboration import create_site_visit
    from app.schemas.collaboration import SiteVisitCreate

    start = datetime.now(timezone.utc) + timedelta(days=3)
    payload = SiteVisitCreate(
        projectId=world["project"].id, engineerId=world["civil"].id, title="Formwork check",
        scheduledStart=start, scheduledEnd=start + timedelta(hours=2), visitType="ROUTINE_INSPECTION")

    world["db"].add(UserPermissionOverride(
        user_id=world["manager"].id, permission_code="site_visit.schedule", allowed=False))
    world["db"].flush()

    with pytest.raises(HTTPException) as raised:
        create_site_visit(payload, db=world["db"], current_user=world["manager"])
    assert raised.value.status_code == 403


def test_an_owner_cannot_shift_the_schedule_directly(world):
    from app.api.scheduling import shift_task_schedule
    from app.schemas.scheduling import ShiftTaskRequest
    task = _task(world, "civil", [world["civil"]])
    with pytest.raises(HTTPException) as raised:
        shift_task_schedule(world["project"].id, ShiftTaskRequest(task_id=task.id, shift_days=3),
                            db=world["db"], current_user=world["owner"])
    assert raised.value.status_code == 403


# --- migrated permission families -------------------------------------------
# Each of these calls the endpoint function directly, which is what a crafted
# HTTP request reaches. The frontend is never the boundary.

def test_raising_an_issue_is_refused_once_the_permission_is_revoked(world):
    from app.api.issues import create_issue
    from app.schemas.issue import IssueCreate

    payload = IssueCreate(projectId=world["project"].id, title="Cracked slab",
                          description="Observed on the second floor.", severity="high")
    world["db"].add(UserPermissionOverride(
        user_id=world["civil"].id, permission_code="issue.create", allowed=False))
    world["db"].flush()

    with pytest.raises(HTTPException) as raised:
        create_issue(payload, db=world["db"], current_user=world["civil"])
    assert raised.value.status_code == 403


def test_a_client_cannot_raise_an_issue_by_default(world):
    from app.api.issues import create_issue
    from app.schemas.issue import IssueCreate
    payload = IssueCreate(projectId=world["project"].id, title="x", description="y", severity="low")
    with pytest.raises(HTTPException) as raised:
        create_issue(payload, db=world["db"], current_user=world["owner"])
    assert raised.value.status_code == 403


def test_an_administrator_can_grant_issue_creation_to_a_client(world):
    """The point of the feature: an unusual structure can be supported."""
    from app.api.issues import create_issue
    from app.schemas.issue import IssueCreate
    world["db"].add(UserPermissionOverride(
        user_id=world["owner"].id, project_id=world["project"].id,
        permission_code="issue.create", allowed=True))
    world["db"].flush()
    payload = IssueCreate(projectId=world["project"].id, title="Client observation",
                          description="Raised by the client.", severity="low")
    issue = create_issue(payload, db=world["db"], current_user=world["owner"])
    assert issue is not None


def test_proposing_a_design_change_respects_the_permission(world):
    from app.api.design_changes import create_design_change
    from app.schemas.design_change import DesignChangeCreate

    payload = DesignChangeCreate(projectId=world["project"].id, title="Window move",
                                 description="Shift the opening north.", reason="Client request",
                                 sourceDiscipline="civil", affectedDisciplines=["civil"])
    # Denied for a role that never had it.
    with pytest.raises(HTTPException) as raised:
        create_design_change(payload, db=world["db"], current_user=world["owner"])
    assert raised.value.status_code == 403

    # And revocable for a role that did.
    world["db"].add(UserPermissionOverride(
        user_id=world["civil"].id, permission_code="design_change.propose", allowed=False))
    world["db"].flush()
    with pytest.raises(HTTPException) as raised:
        create_design_change(payload, db=world["db"], current_user=world["civil"])
    assert raised.value.status_code == 403


def test_task_creation_keeps_its_ownership_rule_after_migration(world):
    """Migrating must not widen: only the assigned manager still creates tasks."""
    from app.api.tasks import create_task
    from app.schemas.task import TaskCreate
    from datetime import date, timedelta

    def payload():
        return TaskCreate(projectId=world["project"].id, name="Pour slab",
                          plannedStartDate=date.today(),
                          plannedEndDate=date.today() + timedelta(days=3))

    # An administrator holds task.create in the catalogue but is not the
    # assigned manager, so the original rule still refuses — unchanged default.
    with pytest.raises(HTTPException) as raised:
        create_task(payload(), db=world["db"], current_user=world["admin"])
    assert raised.value.status_code == 403

    # The assigned manager still succeeds.
    created = create_task(payload(), db=world["db"], current_user=world["manager"])
    assert created is not None


def test_task_creation_can_be_revoked_from_the_assigned_manager(world):
    from app.api.tasks import create_task
    from app.schemas.task import TaskCreate
    from datetime import date, timedelta

    world["db"].add(UserPermissionOverride(
        user_id=world["manager"].id, permission_code="task.create", allowed=False))
    world["db"].flush()
    with pytest.raises(HTTPException) as raised:
        create_task(TaskCreate(projectId=world["project"].id, name="Blocked",
                               plannedStartDate=date.today(),
                               plannedEndDate=date.today() + timedelta(days=1)),
                    db=world["db"], current_user=world["manager"])
    assert raised.value.status_code == 403
