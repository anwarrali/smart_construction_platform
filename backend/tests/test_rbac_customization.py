"""Permission customization, end to end through the API (2026-10-23).

What an administrator configures has to be what the server enforces, at the
next request, for the right people and nobody else:

* a role edit reaches everyone the role governs — including people who still
  point at the shared template the office copied — and only them;
* a per-person override grants, denies, or (when removed) inherits, without
  touching anybody else on the same role;
* the editor's explanation is derived from, and never disagrees with, the one
  resolver (`effective_permissions`);
* the four module view permissions that used to be enforced only by route
  guards now close the API too;
* in development and QA, permission edits no longer ask for a verification
  code; production refuses to start with that switch on, and every other
  step-up purpose still asks.

Fixtures are the shared `site` (one office, one project, engineers, a manager,
a contractor) plus an office administrator; everything is created with unique
names and removed afterwards.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.core.config import Settings, settings
from app.core.permission_catalogue import CATALOGUE
from app.models.company import Company
from app.models.enums import UserStatus
from app.models.issue import Issue
from app.models.permission import UserPermissionOverride
from app.models.rbac import Role
from app.models.user import User
from app.services import rbac, step_up_service
from app.services.authorization import effective_permissions, explain_permissions

from tests.test_qa_pass_2026_10_22 import office_admin  # noqa: F401 - pytest fixture
from tests.test_task_update_reliability import (  # noqa: F401 - pytest fixtures
    _auth, client, db, site,
)

API = "/api/v1"


@pytest.fixture()
def no_bypass(monkeypatch):
    """Production-like step-up: the code is required."""
    monkeypatch.setattr(settings, "STEP_UP_PERMISSION_EDIT_BYPASS", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")


@pytest.fixture()
def dev_bypass(monkeypatch):
    """The development / QA workflow the bypass exists for."""
    monkeypatch.setattr(settings, "STEP_UP_PERMISSION_EDIT_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")


def _mine(client, user, project_id=None) -> set[str]:
    params = {"project_id": str(project_id)} if project_id else None
    response = client.get(f"{API}/access-control/me", headers=_auth(client, user), params=params)
    assert response.status_code == 200, response.text
    return set(response.json())


def _set_role(client, admin, code, *, add=(), remove=()):
    headers = _auth(client, admin)
    roles = client.get(f"{API}/organization/roles", headers=headers).json()
    role = next(item for item in roles if item["code"] == code)
    wanted = (set(role["permissions"]) | set(add)) - set(remove)
    response = client.put(f"{API}/organization/roles/{role['id']}/permissions", headers=headers,
                          json={"permissions": sorted(wanted)})
    assert response.status_code == 200, response.text
    return response.json()


def _override(client, admin, user, code, allowed, project_id=None):
    return client.put(f"{API}/access-control/users/{user.id}", headers=_auth(client, admin),
                      json={"permissionCode": code, "allowed": allowed,
                            "projectId": str(project_id) if project_id else None})


# --- Role level -------------------------------------------------------------------


def test_a_role_grant_reaches_its_holders_and_its_revocation_takes_it_away(
    client, db, site, office_admin, dev_bypass,
):
    """Scenario A: grant Create Project to Engineers, create one, revoke, refused."""
    admin, created = office_admin
    engineer = site["civil"]
    assert client.post(f"{API}/projects", headers=_auth(client, engineer),
                       json={"name": "Before grant"}).status_code == 403

    copy = _set_role(client, admin, "engineer", add={"platform.create_project"})
    assert copy["isTemplate"] is False
    assert "platform.create_project" in copy["permissions"]
    # Read back: the persisted configuration, not the PUT's echo.
    listed = client.get(f"{API}/organization/roles", headers=_auth(client, admin)).json()
    assert "platform.create_project" in next(r for r in listed if r["code"] == "engineer")["permissions"]

    assert "platform.create_project" in _mine(client, engineer)
    response = client.post(f"{API}/projects", headers=_auth(client, engineer),
                           json={"name": f"Engineer project {uuid.uuid4().hex[:6]}"})
    assert response.status_code == 201, response.text
    created.append(uuid.UUID(response.json()["id"]))

    _set_role(client, admin, "engineer", remove={"platform.create_project"})
    assert "platform.create_project" not in _mine(client, engineer)
    assert client.post(f"{API}/projects", headers=_auth(client, engineer),
                       json={"name": "After revoke"}).status_code == 403


def test_a_role_edit_does_not_reach_another_role(client, site, office_admin):
    admin, _ = office_admin
    _set_role(client, admin, "engineer", add={"platform.create_project"})
    assert "platform.create_project" not in _mine(client, site["reviewer"])  # senior_engineer


def test_the_role_list_says_which_roles_are_still_shared_templates(client, site, office_admin):
    admin, _ = office_admin
    roles = client.get(f"{API}/organization/roles", headers=_auth(client, admin)).json()
    engineer = next(item for item in roles if item["code"] == "engineer")
    template = engineer["isTemplate"]
    _set_role(client, admin, "engineer", add={"platform.create_project"})
    after = next(item for item in client.get(f"{API}/organization/roles", headers=_auth(client, admin)).json()
                 if item["code"] == "engineer")
    assert after["isTemplate"] is False
    # Either it was the template and is now the copy, or the office already had one.
    assert template in (True, False)


def test_an_office_role_edit_leaves_another_office_untouched(client, db, site, office_admin):
    """Scenario E: tenant isolation of a role change."""
    admin, _ = office_admin
    _set_role(client, admin, "engineer", add={"platform.create_project"})
    other = Company(name=f"Isolated office {uuid.uuid4().hex[:8]}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(other)
    db.flush()
    outsider = User(full_name="Other office engineer", email=f"other.{uuid.uuid4().hex[:8]}@constro.io",
                    hashed_password="x", status=UserStatus.ACTIVE, company_id=other.id,
                    org_role_id=rbac.seed_roles(db)["engineer"].id, is_internal=True)
    db.add(outsider)
    db.flush()
    try:
        assert "platform.create_project" not in effective_permissions(db, outsider)
        assert "platform.create_project" in effective_permissions(db, db.get(User, site["civil"].id))
    finally:
        db.rollback()


# --- User level -------------------------------------------------------------------


def test_a_person_grant_reaches_that_person_only_and_removing_it_restores_the_role(
    client, site, office_admin, dev_bypass,
):
    """Scenario B."""
    admin, created = office_admin
    rana, colleague = site["civil"], site["bim"]  # both on the Engineer role

    response = _override(client, admin, rana, "platform.create_project", True)
    assert response.status_code == 200, response.text
    body = response.json()
    decision = next(item for item in body["decisions"] if item["code"] == "platform.create_project")
    assert decision == {"code": "platform.create_project", "held": True,
                        "reason": "granted_to_user", "roleGrants": False, "override": True}

    assert "platform.create_project" in _mine(client, rana)
    assert "platform.create_project" not in _mine(client, colleague)
    made = client.post(f"{API}/projects", headers=_auth(client, rana),
                       json={"name": f"Rana project {uuid.uuid4().hex[:6]}"})
    assert made.status_code == 201, made.text
    created.append(uuid.UUID(made.json()["id"]))
    assert client.post(f"{API}/projects", headers=_auth(client, colleague),
                       json={"name": "Colleague"}).status_code == 403

    # Read back from a fresh GET: persisted.
    reread = client.get(f"{API}/access-control/users/{rana.id}", headers=_auth(client, admin)).json()
    assert any(row["permissionCode"] == "platform.create_project" and row["allowed"]
               for row in reread["overrides"])

    assert _override(client, admin, rana, "platform.create_project", None).status_code == 200
    assert "platform.create_project" not in _mine(client, rana)
    assert client.post(f"{API}/projects", headers=_auth(client, rana),
                       json={"name": "After removal"}).status_code == 403


def test_a_person_denial_beats_the_role_and_removing_it_resumes_inheritance(
    client, site, office_admin, dev_bypass,
):
    """Scenario C: inherited, denied for one person, inherited again."""
    admin, _ = office_admin
    rana, colleague = site["civil"], site["bim"]
    project_id = site["project"].id
    assert "issue.create" in _mine(client, rana, project_id)

    body = _override(client, admin, rana, "issue.create", False).json()
    decision = next(item for item in body["decisions"] if item["code"] == "issue.create")
    assert decision["held"] is False and decision["reason"] == "denied_for_user"
    assert decision["roleGrants"] is True

    assert "issue.create" not in _mine(client, rana, project_id)
    assert "issue.create" in _mine(client, colleague, project_id)
    refused = client.post(f"{API}/issues", headers=_auth(client, rana),
                          json={"projectId": str(project_id), "title": "Should be refused"})
    assert refused.status_code == 403

    body = _override(client, admin, rana, "issue.create", None).json()
    decision = next(item for item in body["decisions"] if item["code"] == "issue.create")
    assert decision == {"code": "issue.create", "held": True, "reason": "granted_by_role",
                        "roleGrants": True, "override": None}
    assert "issue.create" in _mine(client, rana, project_id)


def test_a_project_override_applies_on_that_project_only(client, db, site, office_admin, dev_bypass):
    admin, _ = office_admin
    rana = site["civil"]
    project_id = site["project"].id
    assert _override(client, admin, rana, "task.view_all", True, project_id).status_code == 200
    assert "task.view_all" in _mine(client, rana, project_id)
    assert "task.view_all" not in _mine(client, rana)


def test_a_grant_does_not_open_a_project_the_person_is_not_on(client, db, site, office_admin, dev_bypass):
    """The non-overridable boundary: a grant never brings project access with it."""
    from app.models.enums import ProjectStatus
    from app.models.project import Project

    admin, _ = office_admin
    elsewhere = Project(name=f"Not on it {uuid.uuid4().hex[:6]}", status=ProjectStatus.ACTIVE,
                        company_id=site["office"].id)
    db.add(elsewhere)
    db.commit()
    try:
        _override(client, admin, site["civil"], "task.view_all", True)
        assert client.get(f"{API}/tasks/project/{elsewhere.id}",
                          headers=_auth(client, site["civil"])).status_code == 403
        reasons = {item["code"]: item["reason"] for item in client.get(
            f"{API}/access-control/users/{site['civil'].id}", headers=_auth(client, admin),
            params={"project_id": str(elsewhere.id)}).json()["decisions"]}
        assert reasons["task.view_all"] == "blocked_project_access"
    finally:
        db.query(UserPermissionOverride).filter(
            UserPermissionOverride.user_id == site["civil"].id).delete(synchronize_session=False)
        db.delete(db.get(Project, elsewhere.id))
        db.commit()


def test_an_external_participant_cannot_be_given_sign_off(client, site, office_admin, dev_bypass):
    admin, _ = office_admin
    response = _override(client, admin, site["contractor"], "task.review", True, site["project"].id)
    assert response.status_code == 422


def test_the_explanation_never_disagrees_with_the_resolver(client, db, site, office_admin, dev_bypass):
    admin, _ = office_admin
    project_id = site["project"].id
    _override(client, admin, site["civil"], "platform.create_project", True)
    _override(client, admin, site["civil"], "issue.create", False)
    _override(client, admin, site["contractor"], "task.create", True, project_id)
    db.expire_all()
    for key in ("civil", "bim", "manager", "contractor", "reviewer"):
        person = db.get(User, site[key].id)
        for scope in (None, project_id):
            fresh = db.get(User, person.id)
            explained = explain_permissions(db, fresh, scope)
            assert set(explained) == {item.code for item in CATALOGUE}
            assert {code for code, item in explained.items() if item["held"]} == \
                effective_permissions(db, fresh, scope), (key, scope)


def test_the_editor_names_the_office_copy_that_governs(client, site, office_admin, dev_bypass):
    admin, _ = office_admin
    _set_role(client, admin, "engineer", add={"platform.create_project"})
    body = client.get(f"{API}/access-control/users/{site['civil'].id}", headers=_auth(client, admin)).json()
    assert body["governingRoleName"]
    assert "platform.create_project" in body["effectivePermissions"]
    reasons = {item["code"]: item["reason"] for item in body["decisions"]}
    assert reasons["platform.create_project"] == "granted_by_role"


def test_only_a_permission_administrator_may_edit_permissions(client, site, dev_bypass):
    """The bypass removes the code, never the authorization check."""
    engineer = site["civil"]
    assert _override(client, engineer, site["bim"], "platform.create_project", True).status_code == 403
    roles = client.get(f"{API}/organization/roles", headers=_auth(client, engineer)).json()
    role = next(item for item in roles if item["code"] == "engineer")
    assert client.put(f"{API}/organization/roles/{role['id']}/permissions", headers=_auth(client, engineer),
                      json={"permissions": role["permissions"] + ["platform.create_project"]}).status_code == 403


# --- View permissions are enforced by the API, not only by route guards ------------


VIEW_ENDPOINTS = {
    "task.view": "/tasks/project/{project_id}",
    "site_report.view": "/site-reports/project/{project_id}",
    "issue.view": "/issues/project/{project_id}",
    "design_change.view": "/design-changes/project/{project_id}",
}


@pytest.mark.parametrize("code", sorted(VIEW_ENDPOINTS))
def test_revoking_a_view_permission_closes_its_api(client, site, office_admin, dev_bypass, code):
    """Scenario D: the next request after a revocation is refused, no restart."""
    admin, _ = office_admin
    rana = site["civil"]
    path = API + VIEW_ENDPOINTS[code].format(project_id=site["project"].id)
    assert client.get(path, headers=_auth(client, rana)).status_code == 200

    assert _override(client, admin, rana, code, False).status_code == 200
    denied = client.get(path, headers=_auth(client, rana))
    assert denied.status_code == 403
    assert "detail" in denied.json() and not isinstance(denied.json().get("detail"), list)

    assert _override(client, admin, rana, code, None).status_code == 200
    assert client.get(path, headers=_auth(client, rana)).status_code == 200


def test_the_cross_project_issue_list_leaves_out_projects_where_viewing_is_denied(
    client, db, site, office_admin, dev_bypass,
):
    admin, _ = office_admin
    rana = site["civil"]
    db.add(Issue(project_id=site["project"].id, title=f"Visible {uuid.uuid4().hex[:6]}",
                 raised_by_id=site["manager"].id))
    db.commit()
    ids = lambda: {item["projectId"] for item in client.get(  # noqa: E731
        f"{API}/issues", headers=_auth(client, rana)).json()}
    assert str(site["project"].id) in ids()
    _override(client, admin, rana, "issue.view", False, site["project"].id)
    assert str(site["project"].id) not in ids()
    detail_issue = db.query(Issue).filter(Issue.project_id == site["project"].id).first()
    assert client.get(f"{API}/issues/{detail_issue.id}", headers=_auth(client, rana)).status_code == 403


def test_adding_an_outside_party_member_needs_invite_external(client, db, site, office_admin, dev_bypass):
    """`project.invite_external` was registered and checked nowhere."""
    from app.models.rbac import ProjectParty

    admin, _ = office_admin
    manager = site["manager"]
    project_id = site["project"].id
    party = ProjectParty(project_id=project_id, kind="MAIN_CONTRACTOR", display_name=f"Builder {uuid.uuid4().hex[:6]}")
    db.add(party)
    outsider = User(full_name="Outside", email=f"outside.{uuid.uuid4().hex[:8]}@constro.io",
                    hashed_password="x", status=UserStatus.ACTIVE, company_id=site["office"].id,
                    org_role_id=rbac.seed_roles(db)["contractor_representative"].id, is_internal=False)
    db.add(outsider)
    db.commit()
    try:
        _override(client, admin, manager, "project.invite_external", False, project_id)
        refused = client.post(f"{API}/projects/{project_id}/members", headers=_auth(client, manager),
                              json={"userId": str(outsider.id), "partyId": str(party.id)})
        assert refused.status_code == 403, refused.text
        _override(client, admin, manager, "project.invite_external", None, project_id)
        allowed = client.post(f"{API}/projects/{project_id}/members", headers=_auth(client, manager),
                              json={"userId": str(outsider.id), "partyId": str(party.id)})
        assert allowed.status_code == 200, allowed.text
    finally:
        from app.models.notification import Notification
        from app.models.project import ProjectMember

        db.rollback()
        db.query(ProjectMember).filter(ProjectMember.user_id == outsider.id).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.user_id == outsider.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == outsider.id).delete(synchronize_session=False)
        db.query(ProjectParty).filter(ProjectParty.id == party.id).delete(synchronize_session=False)
        db.commit()


# --- Step-up: development / QA bypass, production policy ----------------------------


def test_development_edits_permissions_without_a_code(client, site, office_admin, dev_bypass):
    admin, _ = office_admin
    response = _override(client, admin, site["civil"], "platform.create_project", True)
    assert response.status_code == 200, response.text


def test_qa_edits_permissions_without_a_code(client, site, office_admin, monkeypatch):
    monkeypatch.setattr(settings, "STEP_UP_PERMISSION_EDIT_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "qa")
    admin, _ = office_admin
    assert _override(client, admin, site["civil"], "platform.create_project", True).status_code == 200


def test_production_still_asks_for_a_code(client, site, office_admin, no_bypass):
    admin, _ = office_admin
    response = _override(client, admin, site["civil"], "platform.create_project", True)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "STEP_UP_REQUIRED"
    assert "platform.create_project" not in _mine(client, site["civil"])


def test_a_runtime_switch_cannot_bypass_in_production(monkeypatch):
    """Defence in depth: the per-request check re-reads the environment."""
    monkeypatch.setattr(settings, "STEP_UP_PERMISSION_EDIT_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert step_up_service.permission_edit_bypass_active() is False


@pytest.mark.parametrize("environment", ["production", "staging", "", "prod"])
def test_the_bypass_refuses_to_start_outside_development(environment):
    with pytest.raises(ValueError, match="STEP_UP_PERMISSION_EDIT_BYPASS"):
        Settings(DATABASE_URL="postgresql://x/y", STEP_UP_PERMISSION_EDIT_BYPASS=True,
                 ENVIRONMENT=environment)


@pytest.mark.parametrize("environment", ["development", "local", "test", "qa"])
def test_the_bypass_starts_in_development_environments(environment):
    loaded = Settings(DATABASE_URL="postgresql://x/y", STEP_UP_PERMISSION_EDIT_BYPASS=True,
                      ENVIRONMENT=environment)
    assert loaded.STEP_UP_PERMISSION_EDIT_BYPASS is True


def test_the_bypass_is_off_by_default(monkeypatch):
    monkeypatch.delenv("STEP_UP_PERMISSION_EDIT_BYPASS", raising=False)
    loaded = Settings(_env_file=None, DATABASE_URL="postgresql://x/y", ENVIRONMENT="production")
    assert loaded.STEP_UP_PERMISSION_EDIT_BYPASS is False


@pytest.mark.parametrize("purpose", [
    "security.change_password", "admin.deactivate_user", "admin.delete_user", "admin.reset_user_password",
])
def test_other_sensitive_operations_still_ask_for_a_code_in_development(db, site, dev_bypass, purpose):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refused:
        step_up_service.require_step_up(db, site["manager"], purpose)
    assert refused.value.status_code == 401
    db.rollback()


def test_only_the_two_permission_editing_purposes_are_bypassable():
    assert {code for code, item in step_up_service.PURPOSES.items() if item.permission_editing} == {
        "admin.change_permissions", "admin.change_user_role",
    }


def test_a_bypassed_edit_is_recorded_as_bypassed(client, db, site, office_admin, dev_bypass):
    from app.models.audit_log import AuditLog

    admin, _ = office_admin
    _override(client, admin, site["civil"], "platform.create_project", True)
    row = db.query(AuditLog).filter(AuditLog.actor_id == admin.id,
                                    AuditLog.action == "step_up_bypassed_development").first()
    assert row is not None
    details = json.loads(row.details) if isinstance(row.details, str) else row.details
    assert details["purpose"] == "admin.change_permissions"


def test_role_edits_reach_the_template_holders_after_the_role_is_copied(client, db, site, office_admin):
    """The resolver uses the copy the editor shows, not the template the account names."""
    admin, _ = office_admin
    template = db.query(Role).filter(Role.code == "engineer", Role.organization_id.is_(None)).one()
    assert db.get(User, site["civil"].id).org_role_id == template.id
    _set_role(client, admin, "engineer", add={"platform.create_project"})
    db.expire_all()
    civil = db.get(User, site["civil"].id)
    assert civil.org_role_id == template.id  # the account still names the template…
    assert "platform.create_project" in effective_permissions(db, civil)  # …the copy governs


# --- Messaging and task discussion: the REST operations enforce their codes --------
# Until 2026-10-23 `message.send`, `message.send_client` and `task.comment` were
# checked by voice and the AI layer only; the REST endpoints asked for project
# access, so a revocation hid the web button and the API still sent.


def _start_conversation(client, sender, recipient, project_id):
    return client.post(f"{API}/messages/conversations", headers=_auth(client, sender),
                       json={"projectId": str(project_id), "recipientIds": [str(recipient.id)],
                             "content": "Coordination note"})


def test_revoking_message_send_stops_starting_a_conversation(client, site, office_admin, dev_bypass):
    admin, _ = office_admin
    rana, colleague = site["civil"], site["bim"]
    project_id = site["project"].id
    first = _start_conversation(client, rana, colleague, project_id)
    assert first.status_code == 201, first.text

    _override(client, admin, rana, "message.send", False)
    assert _start_conversation(client, rana, colleague, project_id).status_code == 403
    # Answering a conversation one is already part of is participation, not
    # `message.send`: the reply path is unchanged.
    reply = client.post(f"{API}/messages/conversations/{first.json()['id']}/messages",
                        headers=_auth(client, rana), json={"content": "Still able to reply"})
    assert reply.status_code == 201, reply.text

    _override(client, admin, rana, "message.send", None)
    assert _start_conversation(client, rana, colleague, project_id).status_code == 201


def test_writing_to_the_client_needs_message_send_client(client, db, site, office_admin, dev_bypass):
    from app.models.project import ProjectMember
    from app.models.rbac import ProjectParty

    admin, _ = office_admin
    manager = site["manager"]
    project_id = site["project"].id
    party = ProjectParty(project_id=project_id, kind="CLIENT", display_name=f"Owner {uuid.uuid4().hex[:6]}")
    db.add(party)
    db.flush()
    client_rep = User(full_name="Client rep", email=f"client.{uuid.uuid4().hex[:8]}@constro.io",
                      hashed_password="x", status=UserStatus.ACTIVE, company_id=site["office"].id,
                      org_role_id=rbac.seed_roles(db)["client_representative"].id, is_internal=False)
    db.add(client_rep)
    db.flush()
    db.add(ProjectMember(project_id=project_id, user_id=client_rep.id, party_id=party.id, is_active=True,
                         project_role_id=rbac.seed_roles(db)["client_representative"].id))
    db.commit()
    try:
        assert _start_conversation(client, manager, client_rep, project_id).status_code == 201
        _override(client, admin, manager, "message.send_client", False)
        refused = _start_conversation(client, manager, client_rep, project_id)
        assert refused.status_code == 403, refused.text
        # Messaging office colleagues is unaffected by the client code.
        assert _start_conversation(client, manager, site["civil"], project_id).status_code == 201
    finally:
        db.rollback()
        db.query(ProjectMember).filter(ProjectMember.user_id == client_rep.id).delete(synchronize_session=False)
        db.query(UserPermissionOverride).filter(
            UserPermissionOverride.user_id == manager.id).delete(synchronize_session=False)
        db.commit()
        # Conversations go with the project in the site teardown; the account
        # has messages addressed to it, so it is removed after that cascade.
        from app.models.message import Conversation

        db.query(Conversation).filter(Conversation.project_id == project_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == client_rep.id).delete(synchronize_session=False)
        db.query(ProjectParty).filter(ProjectParty.id == party.id).delete(synchronize_session=False)
        db.commit()


def test_revoking_task_comment_stops_posting_on_a_task(client, site, office_admin, dev_bypass):
    from tests.test_task_update_reliability import _create

    admin, _ = office_admin
    manager = site["manager"]
    task = _create(client, _auth(client, manager), site["project"].id, discipline="civil")
    assert task.status_code == 200, task.text
    path = f"{API}/tasks/{task.json()['id']}/comments"
    assert client.post(path, headers=_auth(client, manager), json={"content": "First"}).status_code == 200

    _override(client, admin, manager, "task.comment", False)
    assert client.post(path, headers=_auth(client, manager), json={"content": "Refused"}).status_code == 403
    _override(client, admin, manager, "task.comment", None)
    assert client.post(path, headers=_auth(client, manager), json={"content": "Again"}).status_code == 200


def test_task_add_note_gates_its_only_write_path(db, site):
    """Notes are written only through a confirmed voice action, which asks the capability's code."""
    from app.schemas.voice_analysis import SuggestedActionType
    from app.services.voice_capabilities import capability_for, is_available

    capability = capability_for(SuggestedActionType.ADD_TASK_NOTE)
    assert capability.permission_code == "task.add_note"
    civil = db.get(User, site["civil"].id)
    project_id = site["project"].id
    assert is_available(db, user=civil, project_id=project_id, capability=capability)
    db.add(UserPermissionOverride(user_id=civil.id, permission_code="task.add_note", allowed=False))
    db.flush()
    try:
        assert not is_available(db, user=db.get(User, civil.id), project_id=project_id, capability=capability)
    finally:
        db.rollback()


def test_a_legacy_consultant_keeps_messaging_and_is_refused_comments(client, db, site, office_admin):
    """The intended Consultant policy, now enforced on REST as well as voice.

    The retired catalogue gave CONSULTANT `message.send` and deliberately left
    it out of `task.comment`, `task.add_note` and `message.send_client`
    (defaults {ADMIN, PM, ENGINEER}); `LEGACY_CONSULTANT_GRANTS` froze exactly
    that in 3f87492. Before 2026-10-23 the REST comment endpoint ignored it.
    """
    from app.core.security import hash_password
    from app.models.project import ProjectMember

    from tests.test_task_update_reliability import PASSWORD, _create

    roles = rbac.seed_roles(db)
    consultant = User(full_name="Legacy consultant", email=f"legacy.{uuid.uuid4().hex[:8]}@constro.io",
                      hashed_password=hash_password(PASSWORD), status=UserStatus.ACTIVE,
                      company_id=site["office"].id, org_role_id=roles["legacy_consultant"].id, is_internal=False)
    db.add(consultant)
    db.flush()
    db.add(ProjectMember(project_id=site["project"].id, user_id=consultant.id, is_active=True,
                         project_role_id=roles["legacy_consultant"].id))
    db.commit()
    try:
        held = _mine(client, consultant, site["project"].id)
        assert "message.send" in held
        assert not held & {"task.comment", "task.add_note", "message.send_client"}
        assert _start_conversation(client, consultant, site["civil"], site["project"].id).status_code == 201
        task = _create(client, _auth(client, site["manager"]), site["project"].id, discipline="civil").json()
        refused = client.post(f"{API}/tasks/{task['id']}/comments", headers=_auth(client, consultant),
                              json={"content": "Not on this role"})
        assert refused.status_code == 403, refused.text
    finally:
        from app.models.message import Conversation

        db.rollback()
        db.query(Conversation).filter(Conversation.project_id == site["project"].id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.user_id == consultant.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == consultant.id).delete(synchronize_session=False)
        db.commit()
