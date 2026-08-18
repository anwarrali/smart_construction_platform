"""Regression coverage for a class of bug found while browser/API-testing the
Consultant role: `User.role` can never literally equal `UserRole.CONSULTANT`.

`UserCreateByAdmin` (app.schemas.user) explicitly converts any request for the
legacy CONSULTANT role into `role=ENGINEER, engineer_affiliation=
"external_consultant"` before it is ever persisted ("Accept the legacy
Consultant form value, but persist the unified Engineer role"). Confirmed live
against the real API: posting `{"role": "consultant", ...}` to `/users` comes
back with `"role": "engineer", "engineerAffiliation": "external_consultant"`.

Several endpoints had not been updated to match that unification and still
compared `current_user.role == UserRole.CONSULTANT` / `!= UserRole.CONSULTANT`
directly — a comparison that can never be true for any account that can
actually be created, so the check always failed shut:

  * `design_change.approve` defaulted to `{CONSULTANT}` alone in the
    catalogue, with no `admin_locked` bypass, so `require()` rejected
    everyone, including Administrator.
  * `approve_design_change` / `reject_design_change` (app.api.design_changes)
    additionally hardcoded `current_user.role == / != UserRole.CONSULTANT` as
    their actual gate.
  * `review_cost_validation` (app.api.cost_validations) hardcoded the same
    always-false comparison.
  * `list_design_changes` / `get_design_change_by_id` used the same dead
    comparison to auto-scope a Consultant Engineer's discipline, so it simply
    never applied.

Net effect before the fix: nobody, ever, through any real account, could
approve or reject a design change, or certify a cost-validation payment claim
— and a Consultant Engineer's discipline scoping on the design-change list/
detail endpoints silently never took effect. `is_consultant_engineer` (role
ENGINEER + affiliation "external_consultant" + active) is the correct check,
matching the pattern already used correctly elsewhere (e.g.
app.services.consultant_approval_service, app.api.photo_archive).

A sibling, unrelated bug found in the same pass: `app.api.cost_validations`
was a complete, tested-shape module that was never `include_router`'d in
`app.api.__init__` at all, so every route in it 404'd for every role
regardless of permissions — `test_the_router_is_actually_mounted` pins that.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.cost_validations import review_cost_validation
from app.api.design_changes import approve_design_change, get_design_change_by_id, reject_design_change
from app.db.database import SessionLocal
from app.models.cost_validation import CostValidation
from app.models.design_change import DesignChange
from app.models.enums import CostValidationStatus, DesignChangeStatus, EngineerDiscipline, ProjectStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import EngineerProfile, User
from app.schemas.cost_validation import CostValidationReview


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
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM cost_validations WHERE project_id = ANY(:projects)",
        "DELETE FROM design_changes WHERE project_id = ANY(:projects)",
        "DELETE FROM engineer_profiles WHERE user_id = ANY(:users)",
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
        "manager": user("DeadRolePm", UserRole.PROJECT_MANAGER),
        "owner": user("DeadRoleOwner", UserRole.OWNER),
        # The real shape of "Consultant" today: ENGINEER + external_consultant.
        "consultant": user("DeadRoleConsultant", UserRole.ENGINEER, "external_consultant"),
        # A Main Contractor Engineer must not gain approval rights just
        # because the catalogue default widened from {CONSULTANT} to
        # {ENGINEER} — the endpoint-level `is_consultant_engineer` gate is
        # what has to keep this excluded.
        "contractor_engineer": user("DeadRoleContractor", UserRole.ENGINEER, "main_contractor"),
    }
    db.flush()
    db.add(EngineerProfile(user_id=people["consultant"].id, discipline=EngineerDiscipline.CIVIL))
    db.add(EngineerProfile(user_id=people["contractor_engineer"].id, discipline=EngineerDiscipline.CIVIL))
    db.flush()

    project = Project(name=f"Dead Role Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["owner"].id, project_manager_id=people["manager"].id)
    db.add(project)
    db.flush()
    for key in ("manager", "consultant", "contractor_engineer"):
        db.add(ProjectMember(project_id=project.id, user_id=people[key].id,
                             role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()

    change = DesignChange(project_id=project.id, task_id=None, title="Rework the footing detail",
                          description="d", reason="r", source_discipline="civil",
                          proposed_by_id=people["manager"].id, status=DesignChangeStatus.PROPOSED)
    claim = CostValidation(project_id=project.id, requested_by_id=people["manager"].id,
                           material_name="Rebar", quantity=10, unit="ton", location="Site A",
                           requested_cost=5000, status=CostValidationStatus.PENDING)
    db.add_all([change, claim])
    db.flush()

    people["project"] = project
    people["change"] = change
    people["claim"] = claim
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id], user_ids)


def _reset_change(db, change):
    change.status = DesignChangeStatus.PROPOSED
    change.approved_by_id = None
    db.flush()


# --- the sibling routing bug --------------------------------------------------

def test_the_cost_validations_router_is_actually_mounted():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/cost-validations" in paths, (
        "app.api.cost_validations existed but was never include_router'd — "
        "every route in it 404'd regardless of role"
    )


# --- design_change.approve / reject -------------------------------------------

def test_a_consultant_engineer_can_approve_a_matching_discipline_change(db, world):
    result = approve_design_change(world["change"].id, db=db, current_user=world["consultant"])
    assert result.status == DesignChangeStatus.APPROVED
    assert result.approved_by_id == world["consultant"].id


def test_a_main_contractor_engineer_cannot_approve(db, world):
    with pytest.raises(HTTPException) as error:
        approve_design_change(world["change"].id, db=db, current_user=world["contractor_engineer"])
    assert error.value.status_code == 403


def test_a_consultant_engineer_can_reject_a_matching_discipline_change(db, world):
    result = reject_design_change(world["change"].id, {"reviewNotes": "no"}, db=db, current_user=world["consultant"])
    assert result.status == DesignChangeStatus.REJECTED


def test_a_main_contractor_engineer_cannot_reject(db, world):
    with pytest.raises(HTTPException) as error:
        reject_design_change(world["change"].id, {}, db=db, current_user=world["contractor_engineer"])
    assert error.value.status_code == 403


def test_a_consultant_engineer_outside_their_discipline_is_still_blocked(db, world):
    """The catalogue-level widening to ENGINEER must not swallow the existing
    per-discipline restriction."""
    world["change"].source_discipline = "electrical"
    db.flush()
    with pytest.raises(HTTPException) as error:
        approve_design_change(world["change"].id, db=db, current_user=world["consultant"])
    assert error.value.status_code == 403


def test_consultant_discipline_scoping_on_the_design_change_list_and_detail_endpoints(db, world):
    """`list_design_changes` / `get_design_change_by_id` silently never
    auto-scoped a Consultant Engineer to their own discipline before this fix
    (the same dead `role == UserRole.CONSULTANT` comparison)."""
    result = get_design_change_by_id(world["change"].id, db=db, current_user=world["consultant"])
    assert result.id == world["change"].id

    world["change"].source_discipline = "electrical"
    db.flush()
    with pytest.raises(HTTPException) as error:
        get_design_change_by_id(world["change"].id, db=db, current_user=world["consultant"])
    assert error.value.status_code == 403


# --- cost_validations review --------------------------------------------------

def test_a_consultant_engineer_can_certify_a_payment_claim(db, world):
    result = review_cost_validation(
        world["claim"].id,
        CostValidationReview(status=CostValidationStatus.APPROVED, certified_amount=4800),
        db=db, current_user=world["consultant"],
    )
    assert result.status == CostValidationStatus.APPROVED
    assert result.reviewed_by_id == world["consultant"].id


def test_a_main_contractor_engineer_cannot_certify_a_payment_claim(db, world):
    with pytest.raises(HTTPException) as error:
        review_cost_validation(
            world["claim"].id,
            CostValidationReview(status=CostValidationStatus.APPROVED, certified_amount=4800),
            db=db, current_user=world["contractor_engineer"],
        )
    assert error.value.status_code == 403
