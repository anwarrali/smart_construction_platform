"""Two capabilities migrated onto the central resolver in this pass.

`schedule.view` (Gantt / critical path / delay analysis): the endpoints used to
gate on a hardcoded "Engineers are blocked from the portfolio view" rule plus
bare project membership, which let any other member — including a Worker,
who was never meant to hold this — reach the full schedule. `require` closes
that gap; project membership itself is unchanged (still required underneath).

`ai.view_insights`: the endpoint gated purely on `can_ifc`'s "VIEW" verb
(the same broad IFC-visibility set the model workspace uses, which includes
Worker). The catalogue's own `ai.view_insights` entry is narrower and is now
layered on top, additive to the existing IFC check, matching the pattern
already used for `ai.review_insight` / `ai.promote_insight` in the same file.
The catalogue default was also corrected to include Owner — the frontend has
always routed Owner to this page and the endpoint has always allowed it, the
catalogue entry just never said so; this is a documentation fix, not a grant.

Each capability gets the same four questions: does the default role succeed,
does a role outside the default get 403, does an administrator's revoke
actually block someone who used to be let in, and does an administrator's
grant actually let someone in who used to be blocked — all without touching
project membership.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.ai_intelligence import list_insights
from app.api.scheduling import calculate_critical_path, get_delay_analysis, get_gantt_data
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.permission import RolePermissionOverride, UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.authorization import has_permission


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
        "DELETE FROM user_permission_overrides WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM role_permission_overrides WHERE updated_by_id = ANY(:users)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


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
        "admin": user("RbacAdmin", UserRole.ADMIN),
        "manager": user("RbacPm", UserRole.PROJECT_MANAGER),
        "owner": user("RbacOwner", UserRole.OWNER),
        # schedule.view's default is the UserRole.CONSULTANT *role*, not an
        # Engineer carrying the external-consultant affiliation — those are two
        # different shapes elsewhere in this app and must not be conflated here.
        # Confirmed intentional, not a migration artifact, in the investigation
        # below `test_a_consultant_engineer_is_intentionally_excluded_...`:
        # the pre-catalogue hardcoded rule already blocked every Engineer
        # (see this file's module docstring), the frontend has never had a
        # schedule/Gantt route for either Engineer variant (only Admin/PM/
        # Owner do), and `UserRole.CONSULTANT` itself can never be a real
        # stored role (`UserCreateByAdmin` persists it as unified Engineer) —
        # so this default has only ever really meant {ADMIN, PM, OWNER} in
        # practice, consistently, on both sides of the stack.
        "consultant": user("RbacConsultant", UserRole.CONSULTANT),
        # The real "Consultant" shape: Engineer + external_consultant.
        "consultant_engineer": user("RbacConsultantEngineer", UserRole.ENGINEER, "external_consultant"),
        "engineer": user("RbacEngineer", UserRole.ENGINEER, "main_contractor"),
        "worker": user("RbacWorker", UserRole.WORKER, "main_contractor"),
    }
    db.flush()

    project = Project(name=f"RBAC Coverage Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    db.add(project)
    db.flush()
    for key in ("manager", "consultant", "consultant_engineer", "engineer", "worker"):
        db.add(ProjectMember(project_id=project.id, user_id=people[key].id,
                             role_on_project=UserRole.CONSULTANT if key == "consultant_engineer" else people[key].role,
                             is_active=True))
    db.flush()

    people["project"] = project
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id], user_ids)


def _grant(db, user, code, allowed=True, project_id=None):
    db.add(UserPermissionOverride(user_id=user.id, permission_code=code, allowed=allowed, project_id=project_id))
    db.flush()


# --- schedule.view -----------------------------------------------------------

def test_the_default_holders_can_see_the_gantt(db, world):
    for key in ("admin", "manager", "consultant", "owner"):
        result = get_gantt_data(world["project"].id, db=db, current_user=world[key])
        assert "tasks" in result


def test_a_worker_member_no_longer_reaches_the_schedule(db, world):
    """The gap this migration closes: bare membership used to be enough."""
    with pytest.raises(HTTPException) as error:
        get_gantt_data(world["project"].id, db=db, current_user=world["worker"])
    assert error.value.status_code == 403


def test_an_engineer_member_still_cannot_see_the_portfolio_schedule(db, world):
    with pytest.raises(HTTPException) as error:
        get_gantt_data(world["project"].id, db=db, current_user=world["engineer"])
    assert error.value.status_code == 403


def test_a_consultant_engineer_is_intentionally_excluded_from_the_portfolio_schedule(db, world):
    """Investigated, not assumed: is a real Consultant Engineer's exclusion
    from `schedule.view` a leftover of the legacy CONSULTANT-role migration
    (a bug — they should be let in), or the actual current architecture (not
    a bug — leave it closed)? Every independent source agrees on the latter:

    * This file's own module docstring: the pre-catalogue hardcoded rule
      already read "Engineers are blocked from the portfolio view", with no
      affiliation carve-out — `schedule.view`'s default is a faithful copy of
      behaviour that predates the permission system entirely, not something
      introduced or narrowed by it.
    * `app.core.permission_catalogue`'s own design rule ("keeping the
      defaults identical to the previous hardcoded behaviour is deliberate")
      backs the same conclusion from the other direction.
    * The frontend has never had a Gantt/critical-path route for *either*
      Engineer variant — `frontend/src/utils/constants.ts` defines
      `PM_PROJECT_SCHEDULE` and the generic `PROJECT_SCHEDULE`/`SCHEDULE`,
      but no `ENGINEER_PROJECT_SCHEDULE` or `CONSULTANT_PROJECT_SCHEDULE`
      exists alongside every other `CONSULTANT_PROJECT_*` route that does
      (dashboard, reviews, design-changes, issues, IFC, AI intelligence,
      messages, ...). No page anywhere calls the gantt/critical-path/
      delay-analysis endpoints for a Consultant Engineer to reach even if
      this test allowed it.
    * A Consultant Engineer's actual review workflow — `task.review`,
      `design_change.approve`, `cost_validation.review`, IFC findings/
      suggestions — is scoped to individual items assigned for their review,
      not portfolio-wide schedule visibility; nothing in that workflow reads
      Gantt/critical-path data.

    So this stays closed: a real Consultant Engineer, unlike the literal
    (unreachable) CONSULTANT role sharing this default's name, was never
    granted this by the pre-catalogue behaviour either. Nothing was widened
    or narrowed by migrating this permission onto `require`.
    """
    with pytest.raises(HTTPException) as error:
        get_gantt_data(world["project"].id, db=db, current_user=world["consultant_engineer"])
    assert error.value.status_code == 403


def test_an_administrator_can_still_grant_a_specific_consultant_engineer_the_schedule(db, world):
    """The point of a configurable resolver: "intentionally closed by
    default" is not "hardcoded shut". An administrator can open it for one
    person on one project through Access Control without this file's
    conclusion above needing to change, and without it opening for anyone
    else."""
    _grant(db, world["consultant_engineer"], "schedule.view", project_id=world["project"].id)
    assert get_gantt_data(world["project"].id, db=db, current_user=world["consultant_engineer"])
    with pytest.raises(HTTPException):
        get_gantt_data(world["project"].id, db=db, current_user=world["engineer"])


def test_revoking_schedule_view_from_consultants_blocks_the_endpoint(db, world):
    assert get_gantt_data(world["project"].id, db=db, current_user=world["consultant"])
    db.add(RolePermissionOverride(role=UserRole.CONSULTANT, permission_code="schedule.view", allowed=False))
    db.flush()
    with pytest.raises(HTTPException) as error:
        get_gantt_data(world["project"].id, db=db, current_user=world["consultant"])
    assert error.value.status_code == 403


def test_granting_schedule_view_lets_a_worker_in_without_widening_membership(db, world):
    """A grant is still an AND with project access, not a bypass of it."""
    _grant(db, world["worker"], "schedule.view")
    assert get_gantt_data(world["project"].id, db=db, current_user=world["worker"])

    outsider = User(full_name="RbacOutsider", email=f"outsider-{uuid4().hex[:8]}@test.local",
                    hashed_password="x", role=UserRole.WORKER, status=UserStatus.ACTIVE)
    db.add(outsider)
    db.flush()
    _grant(db, outsider, "schedule.view")
    try:
        with pytest.raises(HTTPException) as error:
            get_gantt_data(world["project"].id, db=db, current_user=outsider)
        assert error.value.status_code == 403
    finally:
        _purge(db, [], [outsider.id])


def test_critical_path_and_delay_analysis_follow_the_same_rule(db, world):
    assert calculate_critical_path(world["project"].id, db=db, current_user=world["manager"]) is not None
    assert get_delay_analysis(world["project"].id, db=db, current_user=world["manager"]) is not None
    with pytest.raises(HTTPException):
        calculate_critical_path(world["project"].id, db=db, current_user=world["worker"])
    with pytest.raises(HTTPException):
        get_delay_analysis(world["project"].id, db=db, current_user=world["worker"])


# --- ai.view_insights ---------------------------------------------------------

def test_the_default_holders_can_list_insights(db, world):
    for key in ("admin", "manager", "consultant", "engineer", "owner"):
        assert list_insights(world["project"].id, db=db, current_user=world[key], page=1, page_size=50) == []


def test_a_worker_member_cannot_list_ai_insights(db, world):
    with pytest.raises(HTTPException) as error:
        list_insights(world["project"].id, db=db, current_user=world["worker"], page=1, page_size=50)
    assert error.value.status_code == 403


def test_revoking_ai_view_insights_from_engineers_blocks_the_endpoint(db, world):
    assert list_insights(world["project"].id, db=db, current_user=world["engineer"], page=1, page_size=50) == []
    db.add(RolePermissionOverride(role=UserRole.ENGINEER, permission_code="ai.view_insights", allowed=False))
    db.flush()
    with pytest.raises(HTTPException) as error:
        list_insights(world["project"].id, db=db, current_user=world["engineer"], page=1, page_size=50)
    assert error.value.status_code == 403


def test_granting_ai_view_insights_to_a_worker_still_requires_project_access(db, world):
    _grant(db, world["worker"], "ai.view_insights")
    assert list_insights(world["project"].id, db=db, current_user=world["worker"], page=1, page_size=50) == []

    outsider = User(full_name="RbacAiOutsider", email=f"ai-outsider-{uuid4().hex[:8]}@test.local",
                    hashed_password="x", role=UserRole.WORKER, status=UserStatus.ACTIVE)
    db.add(outsider)
    db.flush()
    _grant(db, outsider, "ai.view_insights")
    try:
        with pytest.raises(HTTPException) as error:
            list_insights(world["project"].id, db=db, current_user=outsider, page=1, page_size=50)
        assert error.value.status_code == 403
    finally:
        _purge(db, [], [outsider.id])


def test_owner_holds_ai_view_insights_by_default_matching_shipped_frontend_routing(db, world):
    """Pins the catalogue correction: this was already true in the UI/endpoint,
    the catalogue entry just didn't say so."""
    assert has_permission(db, world["owner"], "ai.view_insights", world["project"].id)


def test_a_deactivated_account_holds_neither_migrated_permission(db, world):
    world["manager"].status = UserStatus.SUSPENDED
    db.flush()
    assert not has_permission(db, world["manager"], "schedule.view", world["project"].id)
    assert not has_permission(db, world["manager"], "ai.view_insights", world["project"].id)
