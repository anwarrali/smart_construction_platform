"""Task disciplines, multiple assignees and the task 24 update failure.

Reproduced from the live project on 2026-10-14:

* **Task 24 ("Snagging and Final Handover")** could not be saved. Its Project
  Manager is also one of its assignees, and `update_task` classified anyone on
  the assignee list as an executing engineer — so every edit beyond status and
  progress was refused with 403 "Engineers can update execution status and
  progress only". Thirteen consecutive PUTs in the log, all 403.
* **The discipline dropdown offered four options** from a list hard-coded in
  the task form, while the office catalogue holds fifteen (and QA/QC was
  missing altogether). The API accepted any string at all.
* **Multiple assignees** were already stored correctly (seven live tasks have
  two); what is tested here is that they survive create, edit, replace and an
  unrelated update, and that the discipline rule reads a person's catalogue
  disciplines, not only the legacy four-value profile.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.company import Company
from app.models.enums import EngineerDiscipline, ProjectStatus, UserStatus
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.rbac import UserDiscipline
from app.models.task import Task, TaskDependency
from app.models.user import EngineerProfile, User
from app.services import rbac

PASSWORD = "Correct#12345"


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
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def site(db):
    """One project, its manager, and the people a handover task involves."""
    suffix = uuid.uuid4().hex[:10]
    disciplines = rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(name=f"Task Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    def person(name, role_code, *, profile=None, catalogue=()):
        role = roles[role_code]
        user = User(
            full_name=f"{name} {suffix}", email=f"{name.lower()}.{suffix}@constro.io",
            hashed_password=hash_password(PASSWORD), status=UserStatus.ACTIVE,
            company_id=office.id, org_role_id=role.id, is_internal=role.is_internal_only,
        )
        db.add(user)
        db.flush()
        if profile:
            db.add(EngineerProfile(user_id=user.id, discipline=profile))
        for code in catalogue:
            db.add(UserDiscipline(user_id=user.id, discipline_id=disciplines[code].id))
        db.flush()
        return user

    manager = person("Manager", "project_manager")
    civil = person("Civil", "engineer", profile=EngineerDiscipline.CIVIL)
    bim = person("Bim", "engineer", profile=EngineerDiscipline.ARCHITECTURAL, catalogue=("bim",))
    contractor = person("Contractor", "contractor_representative")
    reviewer = person("Reviewer", "senior_engineer")

    project = Project(name=f"Handover {suffix}", status=ProjectStatus.ACTIVE, company_id=office.id,
                      project_manager_id=manager.id)
    db.add(project)
    db.flush()
    for user, role_code in ((manager, "project_manager"), (civil, "engineer"), (bim, "engineer"),
                            (contractor, "contractor_representative"), (reviewer, "senior_engineer")):
        db.add(ProjectMember(project_id=project.id, user_id=user.id,
                             project_role_id=roles[role_code].id, is_active=True))
    db.commit()
    people = {"manager": manager, "civil": civil, "bim": bim, "contractor": contractor, "reviewer": reviewer}
    try:
        yield {"project": project, "office": office, **people}
    finally:
        db.rollback()
        user_ids = [user.id for user in people.values()]
        task_ids = [row[0] for row in db.query(Task.id).filter(Task.project_id == project.id).all()]
        if task_ids:
            db.query(TaskDependency).filter(TaskDependency.task_id.in_(task_ids)).delete(synchronize_session=False)
        for model, column in (
            (AuditLog, AuditLog.project_id == project.id),
            (Notification, Notification.project_id == project.id),
            (Task, Task.project_id == project.id),
            (ProjectMember, ProjectMember.project_id == project.id),
            (Project, Project.id == project.id),
            (UserDiscipline, UserDiscipline.user_id.in_(user_ids)),
            (EngineerProfile, EngineerProfile.user_id.in_(user_ids)),
            (User, User.id.in_(user_ids)),
            (Company, Company.id == office.id),
        ):
            db.query(model).filter(column).delete(synchronize_session=False)
        db.commit()


def _auth(client, user) -> dict:
    login = client.post("/api/v1/auth/login", data={"username": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create(client, headers, project_id, **fields):
    body = {"projectId": str(project_id), "name": fields.pop("name", "Snagging and Final Handover"),
            "status": "backlog", "priority": "medium", "reviewRequired": False, **fields}
    return client.post("/api/v1/tasks", headers=headers, json=body)


# --- disciplines ---------------------------------------------------------------


@pytest.mark.parametrize("code", ["architectural", "civil", "structural", "mechanical", "electrical", "bim", "qa_qc",
                                  "plumbing", "hvac", "fire_protection", "mep", "geotechnical", "survey",
                                  "quantity_surveying", "landscape", "infrastructure"])
def test_every_catalogue_discipline_can_be_filed(client, site, code):
    response = _create(client, _auth(client, site["manager"]), site["project"].id, discipline=code)
    assert response.status_code == 200, response.text
    assert response.json()["discipline"] == code


def test_qa_qc_is_in_the_catalogue_the_form_reads(client, site):
    codes = {item["code"] for item in client.get("/api/v1/organization/disciplines", headers=_auth(client, site["manager"])).json()}
    assert {"structural", "bim", "qa_qc", "architectural", "civil", "mechanical", "electrical"} <= codes


@pytest.mark.parametrize(("sent", "stored"), [("STRUCTURAL", "structural"), (" QA/QC ", "qa_qc"), ("Architecture", "architectural")])
def test_spelling_variants_are_stored_as_the_canonical_code(client, site, sent, stored):
    response = _create(client, _auth(client, site["manager"]), site["project"].id, discipline=sent)
    assert response.status_code == 200, response.text
    assert response.json()["discipline"] == stored


def test_an_unknown_discipline_is_refused_naming_the_field(client, site):
    response = _create(client, _auth(client, site["manager"]), site["project"].id, discipline="gb")
    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "discipline"


def test_a_task_under_a_retired_discipline_can_still_be_edited(client, site, db):
    headers = _auth(client, site["manager"])
    task_id = _create(client, headers, site["project"].id, discipline="civil").json()["id"]
    db.query(Task).filter(Task.id == task_id).update({Task.discipline: "legacy_trade"}, synchronize_session=False)
    db.commit()
    response = client.put(f"/api/v1/tasks/{task_id}", headers=headers,
                          json={"discipline": "legacy_trade", "name": "Renamed"})
    assert response.status_code == 200, response.text
    assert response.json()["discipline"] == "legacy_trade"


# --- assignees -------------------------------------------------------------------


def test_several_assignees_persist_through_create_edit_and_an_unrelated_update(client, site):
    headers = _auth(client, site["manager"])
    created = _create(client, headers, site["project"].id, discipline="civil",
                      assigneeIds=[str(site["civil"].id), str(site["contractor"].id)])
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    assert set(created.json()["assigneeIds"]) == {str(site["civil"].id), str(site["contractor"].id)}

    # An edit that does not mention assignees keeps them.
    kept = client.put(f"/api/v1/tasks/{task_id}", headers=headers, json={"name": "Handover walk-through"})
    assert set(kept.json()["assigneeIds"]) == {str(site["civil"].id), str(site["contractor"].id)}

    # Replace: add the BIM engineer on a BIM task, drop the contractor.
    replaced = client.put(f"/api/v1/tasks/{task_id}", headers=headers,
                          json={"discipline": "bim", "assigneeIds": [str(site["bim"].id)]})
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["assigneeIds"] == [str(site["bim"].id)]

    # Clear.
    cleared = client.put(f"/api/v1/tasks/{task_id}", headers=headers, json={"assigneeIds": []})
    assert cleared.json()["assigneeIds"] == []


def test_the_same_person_cannot_be_assigned_twice(client, site):
    response = _create(client, _auth(client, site["manager"]), site["project"].id,
                       assigneeIds=[str(site["contractor"].id), str(site["contractor"].id)])
    assert response.status_code in {409, 422}


def test_a_non_member_cannot_be_assigned(client, site):
    stranger = uuid.uuid4()
    response = _create(client, _auth(client, site["manager"]), site["project"].id, assigneeIds=[str(stranger)])
    assert response.status_code == 400


def test_an_assignee_cannot_reassign_the_task(client, site):
    manager = _auth(client, site["manager"])
    task_id = _create(client, manager, site["project"].id, assigneeIds=[str(site["contractor"].id)]).json()["id"]
    response = client.put(f"/api/v1/tasks/{task_id}", headers=_auth(client, site["contractor"]),
                          json={"assigneeIds": [str(site["contractor"].id), str(site["civil"].id)]})
    assert response.status_code == 403


def test_the_discipline_rule_reads_catalogue_disciplines_and_keeps_old_matches(client, site):
    headers = _auth(client, site["manager"])
    # A civil engineer still covers a structural task, as before.
    assert _create(client, headers, site["project"].id, discipline="structural",
                   assigneeIds=[str(site["civil"].id)]).status_code == 200
    # An engineer whose catalogue disciplines include BIM can take a BIM task…
    assert _create(client, headers, site["project"].id, discipline="bim",
                   assigneeIds=[str(site["bim"].id)]).status_code == 200
    # …and one who practises neither is refused, with the field named.
    refused = _create(client, headers, site["project"].id, discipline="bim", assigneeIds=[str(site["civil"].id)])
    assert refused.status_code == 400
    assert refused.json()["detail"]["field"] == "assignee_ids"


# --- task 24: a Project Manager on the assignee list --------------------------------


def _handover_task(client, site, *, review_required):
    """TSK-024's shape: the PM and an engineer assigned, a predecessor, review on or off."""
    headers = _auth(client, site["manager"])
    predecessor = _create(client, headers, site["project"].id, name="Commissioning",
                          plannedStartDate="2027-03-21", plannedEndDate="2027-03-27").json()["id"]
    task = _create(client, headers, site["project"].id, discipline="architectural", reviewRequired=review_required,
                   assigneeIds=[str(site["reviewer"].id), str(site["manager"].id)], dependencyIds=[predecessor])
    assert task.status_code == 200, task.text
    return headers, task.json()["id"], predecessor


@pytest.mark.parametrize("review_required", [True, False])
def test_the_pm_can_schedule_a_task_they_are_also_assigned_to(client, site, db, review_required):
    headers, task_id, predecessor = _handover_task(client, site, review_required=review_required)
    # Exactly what the edit form sends on save: every field, assignees and
    # dependencies unchanged, the dates newly set.
    response = client.put(f"/api/v1/tasks/{task_id}", headers=headers, json={
        "projectId": str(site["project"].id), "name": "Snagging and Final Handover", "status": "backlog",
        "priority": "medium", "plannedStartDate": "2027-03-28", "plannedEndDate": "2027-04-05",
        "assigneeIds": [str(site["reviewer"].id), str(site["manager"].id)], "discipline": "architectural",
        "dependencyIds": [predecessor], "reviewRequired": review_required,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plannedStartDate"] == "2027-03-28" and body["plannedEndDate"] == "2027-04-05"
    assert body["durationDays"] == 9
    assert body["reviewRequired"] is review_required
    # Scheduling does not touch execution status.
    assert body["status"] == "backlog"
    db.expire_all()
    assert db.query(AuditLog).filter(AuditLog.entity_id == uuid.UUID(task_id), AuditLog.action == "updated").count() == 1


def test_the_pm_can_switch_consultant_review_on_while_scheduling(client, site):
    headers, task_id, _ = _handover_task(client, site, review_required=False)
    response = client.put(f"/api/v1/tasks/{task_id}", headers=headers, json={
        "reviewRequired": True, "reviewDueDate": "2027-04-10",
        "plannedStartDate": "2027-03-28", "plannedEndDate": "2027-04-05",
    })
    assert response.status_code == 200, response.text
    assert response.json()["reviewRequired"] is True
    assert response.json()["reviewDueDate"] == "2027-04-10"


def test_reversed_dates_are_a_validation_error_naming_the_rule(client, site):
    headers, task_id, _ = _handover_task(client, site, review_required=True)
    response = client.put(f"/api/v1/tasks/{task_id}", headers=headers,
                          json={"plannedStartDate": "2027-04-05", "plannedEndDate": "2027-03-28"})
    assert response.status_code == 422
    assert "End date must be on or after start date" in response.text


def test_a_malformed_date_is_a_validation_error(client, site):
    headers, task_id, _ = _handover_task(client, site, review_required=True)
    response = client.put(f"/api/v1/tasks/{task_id}", headers=headers, json={"plannedStartDate": "2027-13-40"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] in {"plannedStartDate", "planned_start_date"}


def test_a_circular_dependency_is_refused(client, site):
    headers, task_id, predecessor = _handover_task(client, site, review_required=False)
    response = client.put(f"/api/v1/tasks/{predecessor}", headers=headers, json={"dependencyIds": [task_id]})
    assert response.status_code == 400
    assert "circular" in response.json()["detail"]


def test_an_engineer_assignee_still_cannot_reschedule(client, site):
    _, task_id, _ = _handover_task(client, site, review_required=True)
    response = client.put(f"/api/v1/tasks/{task_id}", headers=_auth(client, site["reviewer"]),
                          json={"plannedStartDate": "2027-03-28", "plannedEndDate": "2027-04-05"})
    assert response.status_code == 403
    assert "execution status and progress" in response.json()["detail"]


def test_a_member_who_is_neither_pm_nor_assignee_cannot_edit(client, site):
    _, task_id, _ = _handover_task(client, site, review_required=True)
    response = client.put(f"/api/v1/tasks/{task_id}", headers=_auth(client, site["civil"]),
                          json={"plannedStartDate": "2027-03-28", "plannedEndDate": "2027-04-05"})
    assert response.status_code == 403


def test_the_live_task_24_shape_no_longer_returns_403(client, site):
    """The sequence from the log, end to end: PM-and-assignee saves the form twice."""
    headers, task_id, predecessor = _handover_task(client, site, review_required=True)
    payload = {"name": "Snagging and Final Handover", "status": "backlog", "priority": "medium",
               "plannedStartDate": str(date(2027, 3, 28)), "plannedEndDate": str(date(2027, 4, 5)),
               "assigneeIds": [str(site["reviewer"].id), str(site["manager"].id)],
               "discipline": "architectural", "dependencyIds": [predecessor], "reviewRequired": True}
    for _ in range(2):
        response = client.put(f"/api/v1/tasks/{task_id}", headers=headers, json=payload)
        assert response.status_code == 200, response.text
