"""The closed RBAC model, end to end: one source of authority and no other.

`User → org_role_id → Role → RolePermission → effective_permissions`. These
pin what the closure of the migration promised and nothing else pins
directly:

  * an account that is not active holds nothing, whatever its role;
  * a signed token carries identity only — no role claim to trust;
  * a role an office invented reaches the decisions that used to be
    "Project Manager or Admin" (photo categories, project principals);
  * the pickers' eligibility endpoints answer by the same rules the assigning
    endpoints apply, including the reviewer rule (`task.review`).

Everything runs in a transaction on the shared database and is rolled back.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.projects import get_eligible_members
from app.api.users import eligible_users
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.enums import ProjectStatus, UserStatus
from app.models.project import Project, ProjectMember
from app.models.rbac import Role, RolePermission
from app.models.user import User
from app.services import rbac
from app.services.authorization import effective_permissions, has_permission
from app.services.field_submission_authorization import can_manage_project_photo_categories


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
    roles = rbac.seed_roles(db)
    office = rbac.ensure_tenant_organization(db)

    def user(name, role, status=UserStatus.ACTIVE):
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@test.local",
            hashed_password="x", status=status, company_id=office.id,
            org_role_id=role.id, is_internal=role.is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    # A role in no template: what an office actually creates.
    lead = Role(organization_id=office.id, code=f"site_lead_{suffix}", name_en="Site Lead",
                scope="BOTH", is_internal_only=True, is_system=False, rank=70)
    db.add(lead)
    db.flush()
    for code in ("project.manage_members", "task.view", "task.view_all"):
        db.add(RolePermission(role_id=lead.id, permission_code=code, allowed=True))
    db.flush()

    manager = user("CloseManager", roles["project_manager"])
    site_lead = user("CloseSiteLead", lead)
    reviewer = user("CloseReviewer", roles["senior_engineer"])
    doer = user("CloseDoer", roles["engineer"])
    clerk = user("CloseClerk", roles["office_staff"])
    contractor = user("CloseContractor", roles["contractor_representative"])
    client = user("CloseClient", roles["client_representative"])

    project = Project(name=f"Closure {suffix}", status=ProjectStatus.ACTIVE, company_id=office.id,
                      owner_id=client.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    for person in (manager, site_lead, reviewer, doer, clerk, contractor, client):
        db.add(ProjectMember(project_id=project.id, user_id=person.id, is_active=True))
    db.flush()
    return {"db": db, "roles": roles, "lead": lead, "project": project, "manager": manager,
            "site_lead": site_lead, "reviewer": reviewer, "doer": doer, "clerk": clerk,
            "contractor": contractor, "client": client, "office": office, "suffix": suffix}


# --- inactive accounts ----------------------------------------------------------

@pytest.mark.parametrize("status", [UserStatus.PENDING, UserStatus.SUSPENDED, UserStatus.INACTIVE])
def test_an_account_that_is_not_active_holds_nothing(world, status):
    db, manager = world["db"], world["manager"]
    manager.status = status
    db.flush()
    assert effective_permissions(db, manager) == set()
    assert effective_permissions(db, manager, world["project"].id) == set()


# --- tokens -----------------------------------------------------------------------

def test_a_token_carries_identity_and_no_role():
    """Authorization is resolved from the database on every request; a token
    that named a role would be a second, stale source of it."""
    subject = {"sub": str(uuid4()), "email": "someone@example.com"}
    for token in (create_access_token(subject), create_refresh_token(subject)):
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert "role" not in claims
        assert not {key for key in claims if "role" in key.lower()}


# --- a role the office invented -----------------------------------------------------

def test_a_custom_role_manages_photo_categories_through_its_permission(world):
    """Was "Project Manager or Admin"; now whoever may staff the project."""
    db, project_id = world["db"], world["project"].id
    assert can_manage_project_photo_categories(db, world["site_lead"], project_id)
    assert not can_manage_project_photo_categories(db, world["doer"], project_id)

    # And the role, not the person, is the switch.
    db.query(RolePermission).filter(
        RolePermission.role_id == world["lead"].id,
        RolePermission.permission_code == "project.manage_members",
    ).delete()
    db.flush()
    assert not can_manage_project_photo_categories(db, world["site_lead"], project_id)


def test_a_custom_role_holds_exactly_what_the_office_gave_it(world):
    granted = effective_permissions(world["db"], world["site_lead"])
    assert granted == {"project.manage_members", "task.view", "task.view_all"}


# --- the project-principal picker -----------------------------------------------------

def test_eligible_principals_answer_by_the_project_rules(world):
    db = world["db"]
    owners = {user.id for user in eligible_users(purpose="project_owner", db=db, current_user=world["manager"])}
    managers = {user.id for user in eligible_users(purpose="project_manager", db=db, current_user=world["manager"])}
    assert world["client"].id in owners
    assert world["manager"].id not in owners, "office staff is not a client"
    assert world["manager"].id in managers
    assert world["client"].id not in managers
    assert world["contractor"].id not in managers


def test_the_principal_picker_is_refused_to_people_who_set_up_no_projects(world):
    with pytest.raises(HTTPException) as refusal:
        eligible_users(purpose="project_manager", db=world["db"], current_user=world["doer"])
    assert refusal.value.status_code == 403


def test_the_principal_picker_rejects_an_unknown_purpose(world):
    with pytest.raises(HTTPException) as refusal:
        eligible_users(purpose="admin", db=world["db"], current_user=world["manager"])
    assert refusal.value.status_code == 400


# --- the member pickers -------------------------------------------------------------------

def test_task_assignees_are_the_members_who_may_record_progress(world):
    db, project_id = world["db"], world["project"].id
    ids = set(get_eligible_members(project_id, purpose="task_assignee", db=db, current_user=world["manager"]))
    assert world["doer"].id in ids
    assert world["client"].id not in ids
    for key in ("doer", "client", "clerk"):
        expected = has_permission(db, world[key], "task.update_progress", project_id)
        assert (world[key].id in ids) is expected, key


def test_reviewers_must_hold_task_review_and_be_office_staff(world):
    db, project_id = world["db"], world["project"].id
    ids = set(get_eligible_members(project_id, purpose="reviewer", db=db, current_user=world["manager"]))
    assert world["reviewer"].id in ids
    assert world["contractor"].id not in ids, "an outside participant never reviews for the office"
    assert world["clerk"].id not in ids, "office staff without task.review is not a reviewer"


def test_naming_a_reviewer_without_task_review_is_refused(world):
    """The rule the setup endpoint used to state in a comment and not apply."""
    from app.api.projects import update_project_approval_workflow
    from app.schemas.project import ProjectApprovalConfigUpdate

    db, project_id = world["db"], world["project"].id
    admin = User(full_name="CloseAdmin", email=f"closeadmin-{world['suffix']}@test.local",
                 hashed_password="x", status=UserStatus.ACTIVE, company_id=world["office"].id,
                 org_role_id=world["roles"]["org_admin"].id, is_internal=True)
    db.add(admin)
    db.flush()
    with pytest.raises(HTTPException) as refusal:
        update_project_approval_workflow(
            project_id,
            ProjectApprovalConfigUpdate(mode="CENTRALIZED_REVIEW", centralized_reviewer_id=world["clerk"].id),
            db=db, current_user=admin,
        )
    assert refusal.value.status_code == 422


def test_member_pickers_are_closed_to_people_off_the_project(world):
    db = world["db"]
    stranger = User(full_name="CloseStranger", email=f"closestranger-{world['suffix']}@test.local",
                    hashed_password="x", status=UserStatus.ACTIVE, company_id=world["office"].id,
                    org_role_id=world["roles"]["engineer"].id, is_internal=True)
    db.add(stranger)
    db.flush()
    with pytest.raises(HTTPException) as refusal:
        get_eligible_members(world["project"].id, purpose="reviewer", db=db, current_user=stranger)
    assert refusal.value.status_code == 403
