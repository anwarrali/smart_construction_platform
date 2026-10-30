"""Regression tests for the browser QA findings of 2026-10-22.

Each section names the symptom reported from the browser and the root cause
found for it; the frontend half of each fix has its own tests.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.models.audit_log import AuditLog
from app.models.enums import UserStatus
from app.models.project import Project, ProjectMember
from app.models.rbac import Role
from app.models.user import User

from tests.test_task_update_reliability import (  # noqa: F401 - pytest fixtures
    PASSWORD, _auth, client, db, site,
)


@pytest.fixture()
def office_admin(db, site):
    """The office administrator, in the site's office, on no project team."""
    from app.core.security import hash_password
    from app.services import rbac

    role = rbac.seed_roles(db)["org_admin"]
    admin = User(full_name="QA Admin", email=f"qa.admin.{uuid.uuid4().hex[:10]}@constro.io",
                 hashed_password=hash_password(PASSWORD), status=UserStatus.ACTIVE,
                 company_id=site["office"].id, org_role_id=role.id, is_internal=True)
    db.add(admin)
    db.commit()
    created_projects: list[uuid.UUID] = []
    try:
        yield admin, created_projects
    finally:
        db.rollback()
        for project_id in created_projects:
            db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.project_id == project_id).delete(synchronize_session=False)
            db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.actor_id.in_(
            [admin.id, site["civil"].id])).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.user_id == admin.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == admin.id).delete(synchronize_session=False)
        # The office's copy of the Engineer template goes with the office in
        # the site teardown (roles.organization_id cascades).
        db.commit()


# --- H. An office edit of a shared role reached nobody ----------------------------
# Editing the Engineer template copies it into the office; accounts kept
# pointing at the template, so the copy's new `platform.create_project` had zero
# holders and "Add Project" never appeared for any engineer.


def _grant_to_engineers(client, db, admin, code):
    template = db.query(Role).filter(Role.code == "engineer", Role.organization_id.is_(None)).one()
    headers = _auth(client, admin)
    current = client.get("/api/v1/organization/roles", headers=headers).json()
    engineer = next(role for role in current if role["code"] == "engineer")
    response = client.put(f"/api/v1/organization/roles/{template.id}/permissions", headers=headers,
                          json={"permissions": sorted(set(engineer["permissions"]) | {code})})
    assert response.status_code == 200, response.text
    return response.json()


def test_an_office_edit_of_a_shared_role_reaches_the_people_holding_it(client, db, site, office_admin):
    admin, created = office_admin
    engineer = site["civil"]
    before = client.get("/api/v1/access-control/me", headers=_auth(client, engineer)).json()
    assert "platform.create_project" not in before

    _grant_to_engineers(client, db, admin, "platform.create_project")

    after = client.get("/api/v1/access-control/me", headers=_auth(client, engineer)).json()
    assert "platform.create_project" in after
    created_response = client.post("/api/v1/projects", headers=_auth(client, engineer),
                                   json={"name": f"Engineer project {uuid.uuid4().hex[:6]}"})
    assert created_response.status_code == 201, created_response.text
    created.append(uuid.UUID(created_response.json()["id"]))


def test_the_role_list_counts_the_people_a_copy_governs(client, db, site, office_admin):
    admin, _ = office_admin
    copy = _grant_to_engineers(client, db, admin, "platform.create_project")
    # civil and bim hold the Engineer template in this office.
    assert copy["memberCount"] >= 2


def test_an_engineer_without_the_grant_still_cannot_create_a_project(client, site):
    response = client.post("/api/v1/projects", headers=_auth(client, site["civil"]),
                           json={"name": "Not allowed"})
    assert response.status_code == 403


def test_another_offices_edit_does_not_reach_this_office(client, db, site, office_admin):
    """The copy belongs to one office; somebody elsewhere keeps the template."""
    from app.services import rbac
    from app.services.authorization import effective_permissions

    from app.models.company import Company

    admin, _ = office_admin
    _grant_to_engineers(client, db, admin, "platform.create_project")
    other_office = Company(name=f"Other office {uuid.uuid4().hex[:8]}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(other_office)
    db.flush()
    elsewhere = User(full_name="Elsewhere", email=f"elsewhere.{uuid.uuid4().hex[:8]}@constro.io",
                     hashed_password="x", status=UserStatus.ACTIVE, company_id=other_office.id,
                     org_role_id=rbac.seed_roles(db)["engineer"].id, is_internal=True)
    db.add(elsewhere)
    db.flush()
    try:
        assert "platform.create_project" not in effective_permissions(db, elsewhere)
        # …while an engineer in the office that made the edit holds it.
        assert "platform.create_project" in effective_permissions(db, db.get(User, site["civil"].id))
    finally:
        db.rollback()


# --- E. The team leaked through the project payload ------------------------------
# `GET /projects/{id}/members` refused an engineer, but the list and detail
# payloads carried every assignment, discipline and party anyway — and the
# Projects page fell back to them after the refusal.


def _project_from_list(client, user, project_id):
    body = client.get("/api/v1/projects", headers=_auth(client, user), params={"limit": 200}).json()
    return next(item for item in body["data"] if item["id"] == str(project_id))


def test_an_engineer_gets_no_team_in_the_project_payloads(client, site):
    project_id = site["project"].id
    engineer = site["civil"]
    assert client.get(f"/api/v1/projects/{project_id}/members",
                      headers=_auth(client, engineer)).status_code == 403
    assert _project_from_list(client, engineer, project_id)["members"] == []
    detail = client.get(f"/api/v1/projects/{project_id}", headers=_auth(client, engineer)).json()
    assert detail["members"] == []


def test_whoever_staffs_the_project_still_gets_the_team(client, site):
    project_id = site["project"].id
    manager = site["manager"]
    assert len(_project_from_list(client, manager, project_id)["members"]) >= 5
    detail = client.get(f"/api/v1/projects/{project_id}", headers=_auth(client, manager)).json()
    assert len(detail["members"]) >= 5


# --- A/B. Which projects' work the caller can open ------------------------------


def test_the_list_says_which_projects_work_can_be_opened(client, site, office_admin):
    admin, _ = office_admin
    project_id = site["project"].id
    assert _project_from_list(client, admin, project_id)["canOpenWork"] is False
    assert _project_from_list(client, site["manager"], project_id)["canOpenWork"] is True
    assert _project_from_list(client, site["civil"], project_id)["canOpenWork"] is True
    detail = client.get(f"/api/v1/projects/{project_id}", headers=_auth(client, admin)).json()
    assert detail["canOpenWork"] is False


# --- I. The development code echo cannot be turned on in production -------------


@pytest.mark.parametrize("environment", ["production", "staging", "", "prod"])
def test_the_code_echo_refuses_anything_not_declared_development(environment):
    with pytest.raises(ValueError, match="OTP_DEV_ECHO_ENABLED"):
        Settings(DATABASE_URL="postgresql://x/y", OTP_DEV_ECHO_ENABLED=True, ENVIRONMENT=environment)


@pytest.mark.parametrize("environment", ["development", "local", "test"])
def test_the_code_echo_is_allowed_in_a_declared_development_environment(environment):
    settings = Settings(DATABASE_URL="postgresql://x/y", OTP_DEV_ECHO_ENABLED=True, ENVIRONMENT=environment)
    assert settings.OTP_DEV_ECHO_ENABLED is True


def test_production_without_the_echo_is_unaffected(monkeypatch):
    # A developer's backend/.env may enable development-only switches, which
    # production rightly refuses; this test is about the echo. Both routes in:
    # the file itself, and `app.db.database`'s `load_dotenv()` into os.environ.
    monkeypatch.delenv("STEP_UP_PERMISSION_EDIT_BYPASS", raising=False)
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://x/y", OTP_DEV_ECHO_ENABLED=False,
                        ENVIRONMENT="production")
    assert settings.OTP_DEV_ECHO_ENABLED is False
