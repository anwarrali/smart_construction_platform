"""`company_id` is directory scoping (which company a person belongs to, used
by app.api.users to scope the user list and by app.api.company for
`/company/settings`), not a project-visibility boundary — and it must not be
used as one, because cross-company collaboration on one project is how this
app is actually modelled, not an edge case.

Evidence, not invention: app.db.seed_demo seeds a single project owned by one
company ("Al-Nour Developments") whose Main Contractor engineers belong to a
second company ("Al-Nour General Contracting") and whose reviewing
consultants belong to a third ("Horizon Design Consultants") — joined to the
project only through `ProjectMember`, with different `company_id` values
throughout. `app.core.deps.accessible_project_ids` / `user_has_project_access`
and `app.api.dashboard.get_dashboard_stats` already grant these members
access with no `company_id` filter anywhere in the chain; only
`app.api.projects._scoped_projects_query` additionally AND-filtered on
`Project.company_id == current_user.company_id`, which — for every one of
those contractor/consultant members, whose own `company_id` differs from the
project's owning company — silently removed the project from their own
project list even though every other endpoint already let them into it.
This pins the fix: no `company_id` filter in `_scoped_projects_query` either,
bringing all three access paths into agreement.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.projects import list_projects
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.enums import ProjectStatus, UserRole, UserStatus
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


def _purge(db, project_ids, user_ids, company_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids), "companies": list(company_ids)}
    for statement in (
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
        "DELETE FROM companies WHERE id = ANY(:companies)",
    ):
        db.execute(text(statement), params)
    db.commit()


@pytest.fixture()
def world(db):
    suffix = uuid4().hex[:10]

    owner_co = Company(name=f"Owner Co {suffix}")
    contractor_co = Company(name=f"Contractor Co {suffix}")
    unrelated_co = Company(name=f"Unrelated Co {suffix}")
    db.add_all([owner_co, contractor_co, unrelated_co])
    db.flush()

    def user(name, role, company=None, affiliation=None):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      company_id=company.id if company else None,
                      engineer_affiliation=affiliation)
        db.add(person)
        return person

    people = {
        "admin": user("CoAdmin", UserRole.ADMIN, owner_co),
        "owner": user("CoOwner", UserRole.OWNER, owner_co),
        # Same-company contractor engineer: the case that already worked.
        "same_company_engineer": user("CoSameEngineer", UserRole.ENGINEER, owner_co, "main_contractor"),
        # Cross-company contractor engineer, exactly the seeded-demo shape:
        # project member, but a different company than the project's owner.
        "cross_company_engineer": user("CoCrossEngineer", UserRole.ENGINEER, contractor_co, "main_contractor"),
        # No company at all — company_id is nullable; must not crash or be
        # treated as "belongs to every company".
        "no_company_engineer": user("CoNoCompanyEngineer", UserRole.ENGINEER, None, "main_contractor"),
        # A different company's engineer who is NOT a member of this project —
        # must still be excluded, by membership, same as before this fix.
        "unrelated_outsider": user("CoOutsider", UserRole.ENGINEER, unrelated_co, "main_contractor"),
    }
    db.flush()

    project = Project(name=f"Company Scoping Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, company_id=owner_co.id)
    db.add(project)
    db.flush()
    for key in ("same_company_engineer", "cross_company_engineer", "no_company_engineer"):
        db.add(ProjectMember(project_id=project.id, user_id=people[key].id,
                             role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()

    people["project"] = project
    people["owner_co"] = owner_co
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id], user_ids, [owner_co.id, contractor_co.id, unrelated_co.id])


def _visible_ids(db, user, **kwargs):
    response = list_projects(db=db, current_user=user, **kwargs)
    return {project.id for project in response.data}


def test_a_same_company_member_sees_the_project(db, world):
    assert world["project"].id in _visible_ids(db, world["same_company_engineer"])


def test_a_cross_company_member_still_sees_the_project(db, world):
    """The bug this fix closes: membership used to lose to a company_id
    mismatch even though the person is genuinely assigned to the project."""
    assert world["project"].id in _visible_ids(db, world["cross_company_engineer"])


def test_a_member_with_no_company_sees_the_project(db, world):
    assert world["project"].id in _visible_ids(db, world["no_company_engineer"])


def test_a_non_member_from_an_unrelated_company_does_not_see_it(db, world):
    """Membership, not company, is still the boundary — this must not have
    become a blanket cross-company opt-in."""
    assert world["project"].id not in _visible_ids(db, world["unrelated_outsider"])


def test_an_administrator_sees_it_regardless_of_company(db, world):
    assert world["project"].id in _visible_ids(db, world["admin"])


def test_project_list_agrees_with_direct_project_access(db, world):
    """No divergence between the list endpoint and the direct-access check
    for the same person/project — the inconsistency this whole fix exists to
    remove."""
    from app.core.deps import user_has_project_access

    for key in ("same_company_engineer", "cross_company_engineer", "no_company_engineer"):
        listed = world["project"].id in _visible_ids(db, world[key])
        direct = user_has_project_access(db, world[key], world["project"].id)
        assert listed == direct is True, key

    listed = world["project"].id in _visible_ids(db, world["unrelated_outsider"])
    direct = user_has_project_access(db, world["unrelated_outsider"], world["project"].id)
    assert listed == direct is False
