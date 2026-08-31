"""`platform.view_all_projects` made genuinely configurable.

Previously this catalogue entry was descriptive only: the real rule lived in
the hardcoded `can_view_all_projects(role) -> role == ADMIN`, and toggling the
permission in Access Control had no effect. `can_view_all_projects_effective`
(app.services.authorization) now backs it for real, called from
`user_has_project_access` / `accessible_project_ids` (app.core.deps), from
the project list endpoint's `_scoped_projects_query` (app.api.projects), and
from the portfolio dashboard's `get_dashboard_stats` (app.api.dashboard) —
which turned out to have its own, third, independent copy of the same
role-based scoping logic.

The one thing that made this unsafe to do carelessly: `has_permission` calls
back into `user_has_project_access` for project-scoped permissions, and
`user_has_project_access` now calls `can_view_all_projects_effective`, which
calls `has_permission` — a cycle, unless `platform.view_all_projects` is
`project_scoped=False` (so that inner call never re-enters
`user_has_project_access`). `test_platform_view_all_projects_is_not_project_scoped`
below pins that invariant directly: if it is ever flipped without updating
the code, this file — and every project-scoped authorization check in the
app — would hang instead of quietly regressing, so it is written to fail
loudly and specifically instead.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dashboard import get_dashboard_stats
from app.api.projects import list_projects
from app.core.deps import accessible_project_ids, user_has_project_access
from app.core.permission_catalogue import BY_CODE
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.permission import RolePermissionOverride, UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.authorization import can_view_all_projects_effective, has_permission


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
        # example.com (not test.local): this fixture also exercises
        # list_projects, which builds ProjectsListResponse itself and runs its
        # nested UserOut.email through Pydantic's EmailStr validator, which
        # rejects the reserved .local TLD.
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      engineer_affiliation=affiliation)
        db.add(person)
        return person

    people = {
        "admin": user("VapAdmin", UserRole.ADMIN),
        "owner": user("VapOwner", UserRole.OWNER),
        "pm_a": user("VapPmA", UserRole.PROJECT_MANAGER),
        "pm_b": user("VapPmB", UserRole.PROJECT_MANAGER),
        "consultant": user("VapConsultant", UserRole.CONSULTANT),
        "engineer": user("VapEngineer", UserRole.ENGINEER, "main_contractor"),
        "worker": user("VapWorker", UserRole.WORKER, "main_contractor"),
        "outsider": user("VapOutsider", UserRole.WORKER, "main_contractor"),
    }
    db.flush()

    project_a = Project(name=f"View-All Project A {suffix}", status=ProjectStatus.ACTIVE,
                        owner_id=people["owner"].id, project_manager_id=people["pm_a"].id)
    project_b = Project(name=f"View-All Project B {suffix}", status=ProjectStatus.ACTIVE,
                        owner_id=people["owner"].id, project_manager_id=people["pm_b"].id)
    db.add_all([project_a, project_b])
    db.flush()
    for key in ("pm_a", "consultant", "engineer", "worker"):
        db.add(ProjectMember(project_id=project_a.id, user_id=people[key].id,
                             role_on_project=people[key].role, is_active=True))
    db.add(ProjectMember(project_id=project_b.id, user_id=people["pm_b"].id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))
    db.flush()

    people["project_a"] = project_a
    people["project_b"] = project_b
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project_a.id, project_b.id], user_ids)


def _grant(db, user, code, allowed=True, project_id=None):
    db.add(UserPermissionOverride(user_id=user.id, permission_code=code, allowed=allowed, project_id=project_id))
    db.flush()


def _configure_role(db, user, code, allowed):
    """Change what the role this person holds may do, on the live mechanism.

    `RolePermissionOverride` used to be how a role was configured, and these
    tests used it directly. `effective_permissions` read that table only while
    an account had no `org_role_id`; the contract step removed that branch, so
    writing to it now changes nothing.

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
    assert source is not None, "the backstop should have given this account a role"
    copy = Role(
        organization_id=source.organization_id, code=f"{source.code}-{_uuid4().hex[:8]}",
        name_en=source.name_en, scope=source.scope,
        is_internal_only=source.is_internal_only, is_system=False,
        rank=source.rank, legacy_role=source.legacy_role,
        legacy_affiliation=source.legacy_affiliation,
    )
    db.add(copy)
    db.flush()
    for existing in rbac.role_permission_codes(db, source.id):
        db.add(RolePermission(role_id=copy.id, permission_code=existing, allowed=True))
    db.flush()
    user.org_role_id = copy.id
    rbac.set_role_permission(db, role=copy, code=code, allowed=allowed)
    db.flush()


# --- the invariant the whole design leans on -----------------------------

def test_platform_view_all_projects_is_not_project_scoped():
    assert BY_CODE["platform.view_all_projects"].project_scoped is False


# --- default behaviour is unchanged ---------------------------------------

def test_admin_sees_every_project_by_default(db, world):
    assert user_has_project_access(db, world["admin"], world["project_a"].id)
    assert user_has_project_access(db, world["admin"], world["project_b"].id)
    assert accessible_project_ids(db, world["admin"]) is None


def test_a_pm_does_not_see_the_other_pms_project_by_default(db, world):
    assert user_has_project_access(db, world["pm_a"], world["project_a"].id)
    assert not user_has_project_access(db, world["pm_a"], world["project_b"].id)
    assert accessible_project_ids(db, world["pm_a"]) == [world["project_a"].id]


def test_a_project_member_does_not_see_an_unrelated_project_by_default(db, world):
    for key in ("consultant", "engineer", "worker"):
        assert user_has_project_access(db, world[key], world["project_a"].id)
        assert not user_has_project_access(db, world[key], world["project_b"].id)


def test_an_outsider_sees_nothing_by_default(db, world):
    assert not user_has_project_access(db, world["outsider"], world["project_a"].id)
    assert not user_has_project_access(db, world["outsider"], world["project_b"].id)
    assert accessible_project_ids(db, world["outsider"]) == []


def test_the_list_projects_endpoint_keeps_a_pm_scoped_to_their_own_project_by_default(db, world):
    """Regression pin for the `_scoped_projects_query` ordering fix: this used
    to check `role == PROJECT_MANAGER` before the view-all gate, so the gate
    could never take effect for a PM. Confirms the reordering changed nothing
    when no grant is configured."""
    result = list_projects(db=db, current_user=world["pm_a"])
    ids = {project.id for project in result.data}
    assert world["project_a"].id in ids
    assert world["project_b"].id not in ids


# --- granting actually works ------------------------------------------------

def test_granting_view_all_projects_to_a_pm_lets_them_see_the_other_pms_project(db, world):
    _grant(db, world["pm_b"], "platform.view_all_projects")
    assert user_has_project_access(db, world["pm_b"], world["project_a"].id)
    assert accessible_project_ids(db, world["pm_b"]) is None

    result = list_projects(db=db, current_user=world["pm_b"])
    ids = {project.id for project in result.data}
    assert world["project_a"].id in ids
    assert world["project_b"].id in ids


def test_granting_view_all_projects_also_widens_the_portfolio_dashboard(db, world):
    """`get_dashboard_stats` had its own independent copy of the scoping
    logic (hardcoded `role != ADMIN`), so this pins that the fix there
    actually took: a granted PM must see project_a reflected in their
    portfolio totals (via `taskCompletion`, one entry per visible project),
    not just in the plain project list. Checked by name rather than a raw
    count, since `db.query(Project)` with no filter also picks up whatever
    else is in this database (e.g. the one real production project)."""
    without_grant = get_dashboard_stats(db=db, current_user=world["pm_b"])
    names_without = {row["name"] for row in without_grant["taskCompletion"]}
    assert world["project_a"].name not in names_without
    assert world["project_b"].name in names_without

    _grant(db, world["pm_b"], "platform.view_all_projects")
    with_grant = get_dashboard_stats(db=db, current_user=_as_fresh_object(world["pm_b"]))
    names_with = {row["name"] for row in with_grant["taskCompletion"]}
    assert world["project_a"].name in names_with
    assert world["project_b"].name in names_with


def test_granting_view_all_projects_to_a_worker_bypasses_membership_for_read_only_visibility(db, world):
    """The permission's own description is "read any project without being a
    member of it" — a Worker with no relationship to project_b at all must be
    able to see it once explicitly granted, same as any other role."""
    _grant(db, world["outsider"], "platform.view_all_projects")
    assert user_has_project_access(db, world["outsider"], world["project_a"].id)
    assert user_has_project_access(db, world["outsider"], world["project_b"].id)
    assert accessible_project_ids(db, world["outsider"]) is None


def test_granting_is_scoped_to_the_specific_user_not_every_worker(db, world):
    _grant(db, world["outsider"], "platform.view_all_projects")
    # A different Worker, not granted anything, must be unaffected.
    assert not user_has_project_access(db, world["worker"], world["project_b"].id)


# --- revoking actually works, including from an administrator --------------

def _as_fresh_object(user: User) -> User:
    """A new `User` instance for the same row, standing in for the fresh
    instance a new HTTP request's `get_current_user` would produce. Needed
    whenever a test checks, mutates an override, then checks again: the
    per-instance cache is deliberately request-scoped (see
    `can_view_all_projects_effective`'s docstring), so re-using the same
    object across a mutation - which a real request never does to itself -
    would read back its own first, now-stale, answer instead of the change.
    """
    # `org_role_id` and `is_internal` travel with it. Since the contract step
    # an account without a role cannot resolve at all, so a stand-in that
    # omitted them would raise `UnmigratedUser` instead of exercising the cache
    # behaviour this helper exists to test.
    return User(
        id=user.id, role=user.role, status=user.status,
        org_role_id=user.org_role_id, is_internal=user.is_internal,
    )


def test_revoking_view_all_projects_from_the_admin_role_actually_restricts_admins(db, world):
    assert user_has_project_access(db, world["admin"], world["project_b"].id)
    _configure_role(db, world["admin"], "platform.view_all_projects", False)

    admin = _as_fresh_object(world["admin"])
    assert not user_has_project_access(db, admin, world["project_b"].id)
    assert accessible_project_ids(db, admin) == []
    # Losing this does not touch the admin-locked platform administration
    # permissions - the whole reason this one is safe to leave unlocked.
    assert has_permission(db, admin, "platform.manage_permissions")
    assert has_permission(db, admin, "platform.manage_users")


def test_revoking_view_all_projects_does_not_touch_ordinary_project_membership(db, world):
    """Revoking the bypass must not revoke the admin's ordinary access to a
    project they would see anyway through some other route - there is none
    here (admin holds no membership row), so this pins that an admin without
    the bypass genuinely cannot read project_a either, i.e. the revoke is a
    real restriction and not a no-op."""
    _configure_role(db, world["admin"], "platform.view_all_projects", False)
    admin = _as_fresh_object(world["admin"])
    assert not user_has_project_access(db, admin, world["project_a"].id)


# --- the two rules that must never bend --------------------------------

def test_a_deactivated_account_never_gets_the_bypass_even_if_granted(db, world):
    _grant(db, world["outsider"], "platform.view_all_projects")
    world["outsider"].status = UserStatus.SUSPENDED
    db.flush()
    assert can_view_all_projects_effective(db, world["outsider"]) is False
    assert not user_has_project_access(db, world["outsider"], world["project_a"].id)


def test_granting_view_all_projects_does_not_grant_management_authority(db, world):
    """Read visibility and write/management authority are different
    boundaries. `manageable_project` (app.services.authorization) still
    hardcodes "admin, or the PM assigned to this exact project" regardless of
    this permission - a granted PM can now *see* the other project but must
    still not be treated as able to *manage* it by this helper."""
    from app.services.authorization import manageable_project
    _grant(db, world["pm_b"], "platform.view_all_projects")
    assert user_has_project_access(db, world["pm_b"], world["project_a"].id)
    with pytest.raises(HTTPException) as error:
        manageable_project(db, world["pm_b"], world["project_a"].id, "project.edit")
    assert error.value.status_code == 403


# --- no recursion, no cross-instance cache leakage --------------------------

def test_repeated_calls_on_the_same_user_object_do_not_recurse_or_change_answer(db, world):
    for _ in range(50):
        assert user_has_project_access(db, world["admin"], world["project_a"].id) is True
        assert user_has_project_access(db, world["admin"], world["project_b"].id) is True


def test_the_per_request_cache_does_not_leak_across_different_user_objects(db, world):
    """`can_view_all_projects_effective` caches on the `User` instance, not
    globally - a second, separately-loaded `User` row for someone who was NOT
    granted the permission must not see another user's cached `True`."""
    _grant(db, world["pm_b"], "platform.view_all_projects")
    assert can_view_all_projects_effective(db, world["pm_b"]) is True
    assert can_view_all_projects_effective(db, world["pm_a"]) is False


def test_a_different_user_object_for_the_same_row_does_not_read_a_stale_cached_answer(db, world):
    """`can_view_all_projects_effective` caches on the Python `User` instance
    (see its docstring for why that is safe), not in some id-keyed global -
    a second instance representing the same person, as a new HTTP request's
    `get_current_user` would produce, must not inherit a stale answer left on
    a different instance from an earlier request."""
    assert can_view_all_projects_effective(db, world["pm_b"]) is False
    _grant(db, world["pm_b"], "platform.view_all_projects")

    reloaded = _as_fresh_object(world["pm_b"])
    assert reloaded is not world["pm_b"]
    assert can_view_all_projects_effective(db, reloaded) is True
