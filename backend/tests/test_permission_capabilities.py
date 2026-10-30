"""Every granted permission performs its operation; every revoked one stops it (2026-10-23).

Two reports started this pass:

* **Add Task.** Rana was granted `task.create`; the button appeared and the
  request failed with "Only the assigned Project Manager can create project
  tasks". The task endpoints asked whether the caller *was*
  `project.project_manager_id`, with the permission as a second gate at most,
  so no grant to anybody else could ever take effect. The same identity test
  guarded editing, assigning, deleting, reordering, dependencies, review, the
  IFC-suggestion and insight task paths, and editing other people's issues.
* **Delete Project.** `DELETE /projects/{id}` existed behind `project.delete`
  and nothing in the web client called it. It also left no audit record.

Each case drives the API as the person concerned, on the shared `site`
fixture (an office, a project, its assigned manager, engineers Rana = civil
and Omar = bim, a contractor). Projects created for deletion are disposable
and made here; nothing touches data outside the fixture.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import DocumentType, ProjectStatus, UserStatus
from app.models.permission import UserPermissionOverride
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services import rbac

from tests.test_qa_pass_2026_10_22 import office_admin  # noqa: F401 - pytest fixture
from tests.test_task_update_reliability import (  # noqa: F401 - pytest fixtures
    PASSWORD, _auth, _create, client, db, site,
)

API = "/api/v1"


@pytest.fixture(autouse=True)
def _no_code_for_permission_edits(monkeypatch):
    monkeypatch.setattr(settings, "STEP_UP_PERMISSION_EDIT_BYPASS", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")


def _override(client, admin, user, code, allowed, project_id=None):
    response = client.put(f"{API}/access-control/users/{user.id}", headers=_auth(client, admin),
                          json={"permissionCode": code, "allowed": allowed,
                                "projectId": str(project_id) if project_id else None})
    assert response.status_code == 200, response.text
    return response.json()


def _set_role(client, admin, code, *, add=(), remove=()):
    headers = _auth(client, admin)
    role = next(r for r in client.get(f"{API}/organization/roles", headers=headers).json() if r["code"] == code)
    response = client.put(f"{API}/organization/roles/{role['id']}/permissions", headers=headers,
                          json={"permissions": sorted((set(role["permissions"]) | set(add)) - set(remove))})
    assert response.status_code == 200, response.text


def _task_count(db, project_id) -> int:
    db.expire_all()
    return db.query(Task).filter(Task.project_id == project_id).count()


# --- Defect A: Add Task -----------------------------------------------------------


def test_rana_granted_task_create_creates_a_task_and_loses_it_on_revoke(client, db, site, office_admin):
    admin, _ = office_admin
    rana = site["civil"]
    project_id = site["project"].id
    assert _create(client, _auth(client, rana), project_id, name="Before grant").status_code == 403
    before = _task_count(db, project_id)

    decision = next(d for d in _override(client, admin, rana, "task.create", True)["decisions"]
                    if d["code"] == "task.create")
    assert decision["held"] and decision["reason"] == "granted_to_user"

    created = _create(client, _auth(client, rana), project_id, name="Rana's task")
    assert created.status_code == 200, created.text
    assert _task_count(db, project_id) == before + 1
    row = db.get(Task, uuid.UUID(created.json()["id"]))
    assert row.name == "Rana's task" and row.created_by_id == rana.id

    _override(client, admin, rana, "task.create", None)
    refused = _create(client, _auth(client, rana), project_id, name="After revoke")
    assert refused.status_code == 403
    assert _task_count(db, project_id) == before + 1  # the refusal wrote nothing


def test_a_task_create_grant_does_not_reach_a_project_the_person_is_not_on(client, db, site, office_admin):
    admin, _ = office_admin
    elsewhere = Project(name=f"Not on it {uuid.uuid4().hex[:6]}", status=ProjectStatus.ACTIVE,
                        company_id=site["office"].id)
    db.add(elsewhere)
    db.commit()
    try:
        _override(client, admin, site["civil"], "task.create", True)
        assert _create(client, _auth(client, site["civil"]), elsewhere.id).status_code == 403
        assert _task_count(db, elsewhere.id) == 0
    finally:
        db.query(Project).filter(Project.id == elsewhere.id).delete(synchronize_session=False)
        db.commit()


def test_a_role_grant_of_task_create_reaches_every_engineer(client, site, office_admin):
    admin, _ = office_admin
    project_id = site["project"].id
    _set_role(client, admin, "engineer", add={"task.create"})
    for person in (site["civil"], site["bim"]):
        assert _create(client, _auth(client, person), project_id).status_code == 200
    _set_role(client, admin, "engineer", remove={"task.create"})
    for person in (site["civil"], site["bim"]):
        assert _create(client, _auth(client, person), project_id).status_code == 403


def test_a_person_grant_of_task_create_leaves_the_colleague_unchanged(client, site, office_admin):
    admin, _ = office_admin
    _override(client, admin, site["civil"], "task.create", True)
    assert _create(client, _auth(client, site["bim"]), site["project"].id).status_code == 403


def test_denying_task_create_to_the_assigned_manager_stops_them(client, db, site, office_admin):
    """The assigned manager no longer bypasses the permission by being assigned."""
    admin, _ = office_admin
    manager, project_id = site["manager"], site["project"].id
    assert _create(client, _auth(client, manager), project_id).status_code == 200
    _override(client, admin, manager, "task.create", False)
    assert _create(client, _auth(client, manager), project_id).status_code == 403
    _override(client, admin, manager, "task.create", None)
    assert _create(client, _auth(client, manager), project_id).status_code == 200


# --- The rest of the task lifecycle -----------------------------------------------


def test_task_edit_granted_to_an_engineer_edits_and_deletes(client, db, site, office_admin):
    admin, _ = office_admin
    rana, project_id = site["civil"], site["project"].id
    task_id = _create(client, _auth(client, site["manager"]), project_id, name="Editable").json()["id"]
    assert client.put(f"{API}/tasks/{task_id}", headers=_auth(client, rana),
                      json={"name": "Renamed"}).status_code == 403

    _override(client, admin, rana, "task.view_all", True)  # to see a task not assigned to her
    _override(client, admin, rana, "task.edit", True)
    renamed = client.put(f"{API}/tasks/{task_id}", headers=_auth(client, rana), json={"name": "Renamed"})
    assert renamed.status_code == 200, renamed.text
    db.expire_all()
    assert db.get(Task, uuid.UUID(task_id)).name == "Renamed"
    assert client.delete(f"{API}/tasks/{task_id}", headers=_auth(client, rana)).status_code == 200
    db.expire_all()
    assert db.get(Task, uuid.UUID(task_id)) is None


def test_revoking_task_edit_from_the_assigned_manager_stops_edits(client, db, site, office_admin):
    admin, _ = office_admin
    manager, project_id = site["manager"], site["project"].id
    task_id = _create(client, _auth(client, manager), project_id, name="Kept").json()["id"]
    _override(client, admin, manager, "task.edit", False)
    assert client.put(f"{API}/tasks/{task_id}", headers=_auth(client, manager),
                      json={"name": "Changed"}).status_code == 403
    assert client.delete(f"{API}/tasks/{task_id}", headers=_auth(client, manager)).status_code == 403
    db.expire_all()
    assert db.get(Task, uuid.UUID(task_id)).name == "Kept"


def test_revoking_update_progress_stops_the_assignee(client, db, site, office_admin):
    admin, _ = office_admin
    rana, project_id = site["civil"], site["project"].id
    task_id = _create(client, _auth(client, site["manager"]), project_id, status="todo",
                      assigneeIds=[str(rana.id)]).json()["id"]
    _override(client, admin, rana, "task.update_progress", False)
    refused = client.put(f"{API}/tasks/{task_id}/start", headers=_auth(client, rana))
    assert refused.status_code == 403, refused.text
    db.expire_all()
    assert db.get(Task, uuid.UUID(task_id)).status.value == "todo"
    _override(client, admin, rana, "task.update_progress", None)
    started = client.put(f"{API}/tasks/{task_id}/start", headers=_auth(client, rana))
    assert started.status_code == 200, started.text


def test_dependencies_follow_schedule_edit(client, site, office_admin):
    admin, _ = office_admin
    manager, project_id = site["manager"], site["project"].id
    headers = _auth(client, manager)
    first = _create(client, headers, project_id, name="First").json()["id"]
    second = _create(client, headers, project_id, name="Second").json()["id"]
    _override(client, admin, manager, "schedule.edit", False)
    assert client.post(f"{API}/tasks/{second}/dependencies", headers=_auth(client, manager),
                       json={"dependsOnTaskId": first}).status_code == 403
    _override(client, admin, manager, "schedule.edit", None)
    assert client.post(f"{API}/tasks/{second}/dependencies", headers=_auth(client, manager),
                       json={"dependsOnTaskId": first}).status_code == 200


def test_issue_resolve_lets_an_engineer_manage_somebody_elses_issue(client, db, site, office_admin):
    from app.models.issue import Issue

    admin, _ = office_admin
    rana, project_id = site["civil"], site["project"].id
    issue = Issue(project_id=project_id, title="Raised by Omar", raised_by_id=site["bim"].id)
    db.add(issue)
    db.commit()
    path = f"{API}/issues/{issue.id}"
    assert client.put(path, headers=_auth(client, rana), json={"title": "Edited"}).status_code == 403
    _override(client, admin, rana, "issue.resolve", True)
    assert client.put(path, headers=_auth(client, rana), json={"title": "Edited"}).status_code == 200
    db.expire_all()
    assert db.get(Issue, issue.id).title == "Edited"


# --- Defect B: Delete Project -------------------------------------------------------


@pytest.fixture()
def disposable_project(db, site):
    """A throwaway project with one task, Rana on its team."""
    project = Project(name=f"Disposable {uuid.uuid4().hex[:6]}", status=ProjectStatus.ACTIVE,
                      company_id=site["office"].id, project_manager_id=site["manager"].id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=site["civil"].id, is_active=True))
    db.add(ProjectMember(project_id=project.id, user_id=site["manager"].id, is_active=True))
    db.commit()
    project_id = project.id
    try:
        yield project
    finally:
        db.rollback()
        db.query(UserPermissionOverride).filter(
            UserPermissionOverride.project_id == project_id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.commit()


def _listed(client, user, project_id):
    body = client.get(f"{API}/projects", headers=_auth(client, user), params={"limit": 200}).json()
    return next((item for item in body["data"] if item["id"] == str(project_id)), None)


def test_without_project_delete_nobody_can_delete_and_nothing_changes(client, db, site, disposable_project):
    for person in (site["civil"], site["manager"]):  # the Project Manager role does not hold it
        assert _listed(client, person, disposable_project.id)["canDelete"] is False
        assert client.get(f"{API}/projects/{disposable_project.id}/deletion-impact",
                          headers=_auth(client, person)).status_code == 403
        assert client.delete(f"{API}/projects/{disposable_project.id}",
                             headers=_auth(client, person)).status_code == 403
    db.expire_all()
    assert db.get(Project, disposable_project.id) is not None


def test_rana_granted_project_delete_on_one_project_deletes_it(client, db, site, office_admin, disposable_project):
    admin, _ = office_admin
    rana = site["civil"]
    rana_id, other_id = rana.id, site["project"].id
    doomed_id, doomed_name = disposable_project.id, disposable_project.name
    _override(client, admin, rana, "project.delete", True, doomed_id)

    assert _listed(client, rana, doomed_id)["canDelete"] is True
    assert _listed(client, rana, other_id)["canDelete"] is False  # per project

    impact = client.get(f"{API}/projects/{doomed_id}/deletion-impact", headers=_auth(client, rana))
    assert impact.status_code == 200, impact.text
    assert impact.json()["members"] == 2 and impact.json()["name"] == doomed_name

    gone = client.delete(f"{API}/projects/{doomed_id}", headers=_auth(client, rana))
    assert gone.status_code == 200, gone.text
    db.expire_all()
    assert db.get(Project, doomed_id) is None
    assert db.get(Project, other_id) is not None  # nothing else went with it
    assert db.get(User, rana_id) is not None
    audit = db.query(AuditLog).filter(AuditLog.action == "project_deleted",
                                      AuditLog.entity_id == doomed_id).one()
    assert audit.actor_id == rana_id
    assert json.loads(audit.details)["name"] == doomed_name


def test_the_office_director_role_deletes_by_default(client, db, site, disposable_project):
    director = User(full_name="Director", email=f"director.{uuid.uuid4().hex[:8]}@constro.io",
                    hashed_password=__import__("app.core.security", fromlist=["hash_password"]).hash_password(PASSWORD),
                    status=UserStatus.ACTIVE, company_id=site["office"].id,
                    org_role_id=rbac.seed_roles(db)["office_director"].id, is_internal=True)
    db.add(director)
    db.commit()
    try:
        assert _listed(client, director, disposable_project.id)["canDelete"] is True
    finally:
        db.query(AuditLog).filter(AuditLog.actor_id == director.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == director.id).delete(synchronize_session=False)
        db.commit()


# --- document.share_external: the share now exists ----------------------------------


def test_sharing_a_document_with_a_party_opens_it_to_that_party_only(client, db, site, office_admin):
    from app.models.rbac import ProjectParty

    admin, _ = office_admin
    project_id = site["project"].id
    party = ProjectParty(project_id=project_id, kind="MAIN_CONTRACTOR", display_name=f"Builder {uuid.uuid4().hex[:6]}")
    db.add(party)
    db.flush()
    builder = User(full_name="Builder", email=f"builder.{uuid.uuid4().hex[:8]}@constro.io",
                   hashed_password=__import__("app.core.security", fromlist=["hash_password"]).hash_password(PASSWORD),
                   status=UserStatus.ACTIVE, company_id=site["office"].id,
                   org_role_id=rbac.seed_roles(db)["contractor_representative"].id, is_internal=False)
    db.add(builder)
    db.flush()
    db.add(ProjectMember(project_id=project_id, user_id=builder.id, party_id=party.id, is_active=True,
                         project_role_id=rbac.seed_roles(db)["contractor_representative"].id))
    doc = Document(project_id=project_id, uploaded_by_id=site["manager"].id, title="Drawing set",
                   document_type=list(DocumentType)[0], file_url="/uploads/none.pdf")
    db.add(doc)
    db.commit()
    shares = f"{API}/documents/{doc.id}/party-shares"
    try:
        assert client.get(f"{API}/documents/{doc.id}", headers=_auth(client, builder)).status_code == 403
        # Not for an engineer: the role does not hold `document.share_external`.
        assert client.post(shares, headers=_auth(client, site["civil"]),
                           json={"partyId": str(party.id)}).status_code == 403

        manager = _auth(client, site["manager"])
        made = client.post(shares, headers=manager, json={"partyId": str(party.id)})
        assert made.status_code == 201, made.text
        assert client.post(shares, headers=manager, json={"partyId": str(party.id)}).status_code == 409
        assert client.get(f"{API}/documents/{doc.id}", headers=_auth(client, builder)).status_code == 200

        assert client.delete(f"{shares}/{party.id}", headers=manager).status_code == 200
        assert client.get(f"{API}/documents/{doc.id}", headers=_auth(client, builder)).status_code == 403

        _override(client, admin, site["manager"], "document.share_external", False)
        assert client.post(shares, headers=_auth(client, site["manager"]),
                           json={"partyId": str(party.id)}).status_code == 403
        actions = {row.action for row in db.query(AuditLog).filter(AuditLog.entity_id == doc.id).all()}
        assert {"document_shared_with_party", "document_unshared_with_party"} <= actions
    finally:
        db.rollback()
        db.query(Document).filter(Document.id == doc.id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(ProjectMember.user_id == builder.id).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.actor_id == builder.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == builder.id).delete(synchronize_session=False)
        db.query(ProjectParty).filter(ProjectParty.id == party.id).delete(synchronize_session=False)
        db.commit()


def test_a_party_from_another_project_cannot_be_shared_with(client, db, site):
    from app.models.rbac import ProjectParty

    other = Project(name=f"Other {uuid.uuid4().hex[:6]}", status=ProjectStatus.ACTIVE, company_id=site["office"].id)
    db.add(other)
    db.flush()
    foreign = ProjectParty(project_id=other.id, kind="MAIN_CONTRACTOR", display_name="Elsewhere Ltd")
    db.add(foreign)
    doc = Document(project_id=site["project"].id, uploaded_by_id=site["manager"].id, title="Spec",
                   document_type=list(DocumentType)[0], file_url="/uploads/none.pdf")
    db.add(doc)
    db.commit()
    try:
        response = client.post(f"{API}/documents/{doc.id}/party-shares", headers=_auth(client, site["manager"]),
                               json={"partyId": str(foreign.id)})
        assert response.status_code == 400
    finally:
        db.query(Document).filter(Document.id == doc.id).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == other.id).delete(synchronize_session=False)
        db.commit()


# --- The editor states the prerequisites the server checks ---------------------------


def test_the_catalogue_names_prerequisites(client, office_admin):
    admin, _ = office_admin
    rows = {row["code"]: row for row in client.get(f"{API}/access-control/permissions",
                                                    headers=_auth(client, admin)).json()}
    assert "assigned" in rows["task.update_progress"]["prerequisite"]
    assert rows["task.create"]["scopeNote"]
    assert rows["platform.create_project"]["scopeNote"] is None
    from app.core.permission_catalogue import BY_CODE, PREREQUISITES
    assert set(PREREQUISITES) <= set(BY_CODE)


# --- The read side of the catalogue, one row per permission ------------------------
# For each code: the endpoint whose answer it decides, called as engineer Rana.
# If her role grants the code there, a person-level deny must close the
# endpoint at the next request and removing the deny must reopen it; if her
# role does not, a grant must open it and removing the grant must close it.
# `{project}` is a project she is on; `{elsewhere}` one she is not.

READ_MATRIX = [
    ("task.view", "/tasks/project/{project}", True),
    ("task.view_all", "/dashboard/projects/{project}", True),
    ("schedule.view", "/scheduling/{project}/gantt", True),
    ("project.manage_members", "/projects/{project}/members", True),
    ("document.view", "/projects/{project}/files", True),
    ("site_report.view", "/site-reports/project/{project}", True),
    ("issue.view", "/issues/project/{project}", True),
    ("design_change.view", "/design-changes/project/{project}", True),
    ("ai.view_insights", "/projects/{project}/ai-intelligence/insights", True),
    ("agents.view", "/projects/{project}/agents", True),
    ("ifc.view", "/projects/{project}/ifc/models", True),
    ("client_portal.view", "/projects/{project}/owner-dashboard", True),
    ("platform.manage_users", "/users", False),
    ("platform.manage_permissions", "/access-control/permissions", False),
    ("org.manage_settings", "/company/settings", False),
    ("project.manage_reminders", "/reminders/scheduler-status", False),
    ("platform.view_all_projects", "/projects/{elsewhere}", False),
    ("platform.work_in_all_projects", "/tasks/project/{elsewhere}", False),
]


@pytest.fixture()
def elsewhere(db, site):
    project = Project(name=f"Elsewhere {uuid.uuid4().hex[:6]}", status=ProjectStatus.ACTIVE,
                      company_id=site["office"].id)
    db.add(project)
    db.commit()
    project_id = project.id
    try:
        yield project
    finally:
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.commit()


@pytest.mark.parametrize("code,path,project_scoped", READ_MATRIX, ids=[row[0] for row in READ_MATRIX])
def test_each_permission_opens_and_closes_its_endpoint(client, db, site, office_admin, elsewhere,
                                                       code, path, project_scoped):
    from app.services.authorization import effective_permissions

    admin, _ = office_admin
    rana = site["civil"]
    project_id = site["project"].id
    url = API + path.format(project=project_id, elsewhere=elsewhere.id)
    scope = project_id if project_scoped else None
    status = lambda: client.get(url, headers=_auth(client, rana)).status_code  # noqa: E731

    db.expire_all()
    held = code in effective_permissions(db, db.get(User, rana.id), scope)
    if held:
        assert status() == 200, f"{code} held by the role but {url} refused"
        _override(client, admin, rana, code, False, scope)
        assert status() == 403, f"denying {code} did not close {url}"
        _override(client, admin, rana, code, None, scope)
        assert status() == 200
    else:
        assert status() == 403, f"{url} answered without {code}"
        _override(client, admin, rana, code, True, scope)
        assert status() == 200, f"granting {code} did not open {url}"
        _override(client, admin, rana, code, None, scope)
        assert status() == 403


# --- The write side: each permission performs its operation, and only with it ----------
# Same shape as the read matrix, for operations that create something. Every
# call creates a uniquely named row inside the fixture's project or office, so
# a success is a real write, and every row goes with the fixture.


def _unique() -> str:
    return uuid.uuid4().hex[:8]


WRITE_MATRIX = [
    ("design_change.propose", "post", "/design-changes", True, lambda p: {
        "projectId": p, "title": f"Change {_unique()}", "sourceDiscipline": "civil",
        "affectedDisciplines": ["structural"]}),
    ("site_visit.schedule", "post", "/site-visits", True, lambda p: {
        "projectId": p, "title": f"Visit {_unique()}", "visitType": "INSPECTION",
        "scheduledStart": "2031-03-01T08:00:00Z", "scheduledEnd": "2031-03-01T10:00:00Z",
        "allowConflict": True}),
    ("project.manage_parties", "post", "/projects/{project}/parties", True, lambda p: {
        "kind": "SUPPLIER", "displayName": f"Supplier {_unique()}"}),
    ("project.edit", "put", "/projects/{project}", True, lambda p: {"description": f"Edited {_unique()}"}),
    ("org.manage_disciplines", "post", "/organization/disciplines", False, lambda p: {
        "code": f"d_{_unique()}", "nameEn": "Test discipline"}),
    ("org.manage_roles", "post", "/organization/roles", False, lambda p: {
        "code": f"r_{_unique()}", "nameEn": "Test role", "permissions": []}),
    ("message.broadcast", "post", "/messages/announcements", True, lambda p: {
        "projectId": p, "content": f"Announcement {_unique()}"}),
    ("owner_request.create", "post", "/owner-requests", True, lambda p: {
        "projectId": p, "title": f"Request {_unique()}", "description": "Please confirm the finish.",
        "category": "GENERAL"}),
]


@pytest.mark.parametrize("code,method,path,project_scoped,body", WRITE_MATRIX, ids=[row[0] for row in WRITE_MATRIX])
def test_each_permission_performs_its_write_and_only_with_it(client, db, site, office_admin,
                                                            code, method, path, project_scoped, body):
    from app.services.authorization import effective_permissions

    admin, _ = office_admin
    rana = site["civil"]
    project_id = site["project"].id
    url = API + path.format(project=project_id)
    scope = project_id if project_scoped else None
    call = lambda: getattr(client, method)(url, headers=_auth(client, rana), json=body(str(project_id)))  # noqa: E731

    db.expire_all()
    held = code in effective_permissions(db, db.get(User, rana.id), scope)
    ok = lambda response: 200 <= response.status_code < 300  # noqa: E731
    if held:
        first = call()
        assert ok(first), f"{code} held but refused: {first.status_code} {first.text}"
        _override(client, admin, rana, code, False, scope)
        assert call().status_code == 403, f"denying {code} did not stop {method.upper()} {url}"
        _override(client, admin, rana, code, None, scope)
        assert ok(call())
    else:
        refused = call()
        assert refused.status_code == 403, f"{method.upper()} {url} answered {refused.status_code} without {code}"
        _override(client, admin, rana, code, True, scope)
        granted = call()
        assert ok(granted), f"granting {code} did not allow it: {granted.status_code} {granted.text}"
        _override(client, admin, rana, code, None, scope)
        assert call().status_code == 403


def test_a_site_visit_clash_is_a_409_with_readable_times(client, site):
    """Double-booking answered 500: the conflict detail carried raw datetimes."""
    body = {"projectId": str(site["project"].id), "title": "First visit", "visitType": "INSPECTION",
            "scheduledStart": "2031-04-01T08:00:00Z", "scheduledEnd": "2031-04-01T10:00:00Z"}
    headers = _auth(client, site["civil"])
    assert client.post(f"{API}/site-visits", headers=headers, json=body).status_code == 201
    clash = client.post(f"{API}/site-visits", headers=headers, json={**body, "title": "Second visit"})
    assert clash.status_code == 409, clash.text
    conflict = clash.json()["detail"]["conflicts"][0]
    assert conflict["scheduledStart"].startswith("2031-04-01T08:00")


def test_cost_validation_review_decides_who_sees_the_budget(client, db, site, office_admin):
    admin, _ = office_admin
    rana, project = site["civil"], site["project"]
    project.budget_total = 1_250_000
    db.commit()
    budget = lambda: client.get(f"{API}/projects/{project.id}", headers=_auth(client, rana)).json()["budgetTotal"]  # noqa: E731
    assert budget() == 1_250_000  # the Engineer role holds it
    _override(client, admin, rana, "cost_validation.review", False, project.id)
    assert budget() is None
    db.expire_all()
    assert db.get(Project, project.id).budget_total == 1_250_000  # hidden, never written
    _override(client, admin, rana, "cost_validation.review", None, project.id)
    assert budget() == 1_250_000


def test_project_view_all_disciplines_widens_the_discipline_narrowing(client, db, site, office_admin):
    """Without it, task-linked records outside the person's disciplines are left out."""
    from app.models.issue import Issue
    from app.models.rbac import ProjectMemberDiscipline

    admin, _ = office_admin
    rana, project_id = site["civil"], site["project"].id
    member = db.query(ProjectMember).filter(ProjectMember.project_id == project_id,
                                            ProjectMember.user_id == rana.id).one()
    civil = rbac.resolve_discipline(db, "civil")
    db.add(ProjectMemberDiscipline(project_member_id=member.id, discipline_id=civil.id))
    task_id = _create(client, _auth(client, site["manager"]), project_id, discipline="mechanical").json()["id"]
    issue = Issue(project_id=project_id, task_id=uuid.UUID(task_id), title="Mechanical clash",
                  raised_by_id=site["manager"].id)
    db.add(issue)
    db.commit()
    visible = lambda: {row["id"] for row in client.get(  # noqa: E731
        f"{API}/issues/project/{project_id}", headers=_auth(client, rana)).json()}
    try:
        assert str(issue.id) in visible()  # the Engineer role holds it
        _override(client, admin, rana, "project.view_all_disciplines", False, project_id)
        assert str(issue.id) not in visible()
        _override(client, admin, rana, "project.view_all_disciplines", None, project_id)
        assert str(issue.id) in visible()
    finally:
        db.query(ProjectMemberDiscipline).filter(
            ProjectMemberDiscipline.project_member_id == member.id).delete(synchronize_session=False)
        db.commit()
