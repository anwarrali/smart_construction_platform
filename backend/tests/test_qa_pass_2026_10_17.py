"""Regression tests for the QA pass of 2026-10-17.

Each section names the defect it covers and the evidence it was reproduced
from (database rows and request logs of the live QA project).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.ai.transcription_service import TranscriptionService
from app.ai.construction_analysis_service import _SYSTEM_PROMPT_TEMPLATE
from app.models.enums import IssueStatus, TaskStatus, VoiceAnalysisStatus
from app.models.issue import Issue
from app.models.permission import UserPermissionOverride
from app.models.task import Task
from app.models.voice_action import VoiceActionDraft
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_command import VoiceDraftUpdate
from app.services import voice_rules_engine
from app.services.voice_command_service import update_draft
from app.services.voice_language import reply_language

from tests.test_task_update_reliability import (  # noqa: F401 - pytest fixtures
    _auth, _create, client, db, site,
)


# --- Task filtering (QA-02) ------------------------------------------------------
# `GET /tasks/project/{id}` accepted no query parameters, so the project Tasks
# page's filters were dropped and every task came back whatever was selected.


def _seed_tasks(client, db, site):
    headers = _auth(client, site["manager"])
    plan = [
        ("Excavation", "todo", "high"),
        ("Formwork", "in_progress", "medium"),
        ("Rebar inspection", "under_review", "high"),
        ("Pour slab", "under_review", "low"),
        ("Handover", "done", "medium"),
    ]
    ids = {}
    for name, status, priority in plan:
        created = _create(client, headers, site["project"].id, name=name, priority=priority, status="todo")
        assert created.status_code == 200, created.text
        ids[name] = created.json()["id"]
        db.query(Task).filter(Task.id == ids[name]).update({Task.status: TaskStatus(status)}, synchronize_session=False)
        # Committed before the next API call: an open row lock here would make
        # the API's critical-path refresh wait on this session forever.
        db.commit()
    return headers, ids


def _listed(client, headers, project_id, **params):
    response = client.get(f"/api/v1/tasks/project/{project_id}", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {item["name"] for item in response.json()}


@pytest.mark.parametrize(("status", "expected"), [
    ("todo", {"Excavation"}),
    ("in_progress", {"Formwork"}),
    ("under_review", {"Rebar inspection", "Pour slab"}),
    ("done", {"Handover"}),
])
def test_each_status_filter_returns_exactly_its_tasks(client, db, site, status, expected):
    headers, _ = _seed_tasks(client, db, site)
    assert _listed(client, headers, site["project"].id, status=status) == expected


def test_a_status_with_no_tasks_returns_none(client, db, site):
    headers, _ = _seed_tasks(client, db, site)
    assert _listed(client, headers, site["project"].id, status="blocked") == set()


def test_clearing_the_filter_returns_every_task(client, db, site):
    headers, ids = _seed_tasks(client, db, site)
    assert _listed(client, headers, site["project"].id) == set(ids)


def test_status_combines_with_priority_and_search(client, db, site):
    headers, _ = _seed_tasks(client, db, site)
    assert _listed(client, headers, site["project"].id, status="under_review", priority="high") == {"Rebar inspection"}
    assert _listed(client, headers, site["project"].id, status="under_review", search="slab") == {"Pour slab"}


def test_filtered_results_follow_a_data_change(client, db, site):
    headers, ids = _seed_tasks(client, db, site)
    db.query(Task).filter(Task.id == ids["Excavation"]).update({Task.status: TaskStatus.UNDER_REVIEW}, synchronize_session=False)
    db.commit()
    assert "Excavation" in _listed(client, headers, site["project"].id, status="under_review")
    assert _listed(client, headers, site["project"].id, status="todo") == set()


# --- Standalone issue updates through voice (QA-05) ------------------------------
# Re-saving an issue draft validated its target against the *task* list and
# failed with "Selected task is outside the allowed task list".


def _voice_command(db, site, *, status=VoiceAnalysisStatus.READY_FOR_CONFIRMATION):
    command = VoiceAnalysis(
        project_id=site["project"].id, user_id=site["manager"].id, status=status,
        idempotency_key=f"qa-{uuid.uuid4().hex}", raw_transcript="المشكلة انحلت",
    )
    db.add(command)
    db.flush()
    return command


def _issue(db, site, title="6 structural works task(s) exist, but the IFC contains no structural elements"):
    issue = Issue(project_id=site["project"].id, title=title, description="Raised by AI analysis",
                  raised_by_id=site["manager"].id, status=IssueStatus.OPEN, task_id=None)
    db.add(issue)
    db.flush()
    return issue


def _issue_draft(db, command, issue):
    draft = VoiceActionDraft(
        voice_analysis_id=command.id, client_action_id="a1", sequence=0,
        action_type="UPDATE_ISSUE_STATUS", target_entity_type="ISSUE", target_entity_id=issue.id,
        extracted_payload={"issueStatus": "resolved"}, confidence=0.9, missing_fields=[], warnings=[],
        risk_level="MEDIUM", required_evidence=[], selected_for_execution=True, execution_status="PENDING",
    )
    db.add(draft)
    db.flush()
    return draft


@pytest.fixture()
def voice_cleanup(db):
    yield
    db.rollback()


def test_a_standalone_issue_draft_can_be_resaved_without_a_task(db, site, voice_cleanup):
    command = _voice_command(db, site)
    issue = _issue(db, site)
    draft = _issue_draft(db, command, issue)
    updated = update_draft(db, command=command, draft=draft, user=site["manager"], update=VoiceDraftUpdate(
        target_id=issue.id, payload={"issueStatus": "resolved", "resolutionNotes": "Model re-exported"},
        row_version=command.row_version,
    ))
    assert updated.target_entity_type == "ISSUE"
    assert updated.target_entity_id == issue.id
    assert db.get(Issue, issue.id).task_id is None  # nobody invented a task link


def test_an_issue_draft_cannot_be_pointed_at_a_task(db, client, site, voice_cleanup):
    task_id = _create(client, _auth(client, site["manager"]), site["project"].id).json()["id"]
    command = _voice_command(db, site)
    issue = _issue(db, site)
    draft = _issue_draft(db, command, issue)
    with pytest.raises(HTTPException) as refused:
        update_draft(db, command=command, draft=draft, user=site["manager"], update=VoiceDraftUpdate(
            target_id=uuid.UUID(task_id), payload={}, row_version=command.row_version,
        ))
    assert refused.value.status_code == 422


def test_another_projects_issue_cannot_be_targeted(db, site, voice_cleanup):
    command = _voice_command(db, site)
    issue = _issue(db, site)
    draft = _issue_draft(db, command, issue)
    with pytest.raises(HTTPException) as refused:
        update_draft(db, command=command, draft=draft, user=site["manager"], update=VoiceDraftUpdate(
            target_id=uuid.uuid4(), payload={}, row_version=command.row_version,
        ))
    assert refused.value.status_code == 422


# --- Dependent voice steps (QA-08) -----------------------------------------------
# Seen live: START_TASK rejected for the manager, UPDATE_TASK_PROGRESS then
# committed — a task at 30% its engineer had never started.


def test_a_refused_step_stops_the_later_steps_on_the_same_record(db, site, monkeypatch, voice_cleanup):
    command = _voice_command(db, site, status=VoiceAnalysisStatus.CONFIRMED)
    target = uuid.uuid4()
    other = uuid.uuid4()
    for sequence, (action, entity) in enumerate([("START_TASK", target), ("UPDATE_TASK_PROGRESS", target),
                                                 ("UPDATE_TASK_PROGRESS", other)]):
        db.add(VoiceActionDraft(
            voice_analysis_id=command.id, client_action_id=f"a{sequence}", sequence=sequence,
            action_type=action, target_entity_type="TASK", target_entity_id=entity,
            extracted_payload={"progressPercentage": 30}, confidence=0.9, missing_fields=[], warnings=[],
            risk_level="LOW", required_evidence=[], selected_for_execution=True, execution_status="PENDING",
        ))
    db.commit()

    executed: list[tuple[str, uuid.UUID]] = []

    def fake_validate(self, db, *, command, draft, actor):
        return SimpleNamespace(type=draft.action_type, target_id=draft.target_entity_id)

    def fake_execute(db, *, analysis, current_user, action, action_index):
        if action.type == "START_TASK":
            raise HTTPException(status_code=403, detail="Only an assigned Main Contractor Engineer can start this task")
        executed.append((action.type, action.target_id))
        return SimpleNamespace(entity_id=None, success=True,
                               model_copy=lambda update: SimpleNamespace(model_dump=lambda **_: {"success": True}))

    monkeypatch.setattr(voice_rules_engine.VoiceRulesEngine, "validate", fake_validate)
    monkeypatch.setattr(voice_rules_engine, "_execute_one", fake_execute)
    monkeypatch.setattr(voice_rules_engine.VoiceRulesEngine, "_task_state", staticmethod(lambda db, task_id: None))

    results = voice_rules_engine.VoiceRulesEngine().execute(db, command=command, actor=site["manager"])
    statuses = [item.get("status") for item in results]
    assert "REJECTED" in statuses and "SKIPPED" in statuses
    # The progress on the refused task never ran; the unrelated one did.
    assert executed == [("UPDATE_TASK_PROGRESS", other)]
    db.expire_all()
    assert db.get(VoiceAnalysis, command.id).status == VoiceAnalysisStatus.PARTIALLY_EXECUTED


# --- Agents page (QA-07) ---------------------------------------------------------


def _agents(client, user, project_id):
    return client.get(f"/api/v1/projects/{project_id}/agents", headers=_auth(client, user))


def test_an_engineer_without_the_permission_cannot_reach_the_agents_api(client, site):
    project_id = site["project"].id
    assert _agents(client, site["civil"], project_id).status_code == 403
    for path in ("/runs", "/subscriptions"):
        response = client.get(f"/api/v1/projects/{project_id}/agents{path}", headers=_auth(client, site["civil"]))
        assert response.status_code == 403, path
    run = client.post(f"/api/v1/projects/{project_id}/agents/run", headers=_auth(client, site["civil"]))
    assert run.status_code == 403


def test_the_project_manager_needs_an_explicit_grant_too(client, site):
    assert _agents(client, site["manager"], site["project"].id).status_code == 403


def test_an_explicit_grant_opens_the_page_and_revoking_closes_it(client, db, site):
    grant = UserPermissionOverride(user_id=site["civil"].id, project_id=None,
                                   permission_code="agents.view", allowed=True)
    db.add(grant)
    db.commit()
    try:
        assert _agents(client, site["civil"], site["project"].id).status_code == 200
        grant.allowed = False
        db.commit()
        assert _agents(client, site["civil"], site["project"].id).status_code == 403
    finally:
        db.delete(grant)
        db.commit()


def test_the_permission_is_in_the_catalogue_and_on_the_administrator_template():
    from app.core.permission_catalogue import BY_CODE
    from app.core.role_templates import TEMPLATES

    assert "agents.view" in BY_CODE
    holders = {template.code for template in TEMPLATES if "agents.view" in template.permissions()}
    assert holders == {"org_admin"}


# --- Mixed Arabic-English voice (QA-04) -------------------------------------------
# The server transcribes and interprets without a locale hint; these pin that,
# and the reply-language rule, with deterministic transcripts.

MIXED = "حلينا مشكلة في الـ structure elements، وبدي أعدل عليها."


@pytest.mark.parametrize(("transcript", "language"), [
    (MIXED, "ar"),
    ("اليوم خلصنا مشكلات الـstructural elements اللي في الـIFC", "ar"),
    ("بلشنا في المهمة TSK-001، بنسبة 30% خلصنا", "ar"),
    ("The structural elements issue in the IFC file is resolved", "en"),
    ("خلصنا الصب", "ar"),
    ("Update TSK-003 to 40 percent", "en"),
])
def test_the_reply_language_follows_the_speech_not_the_interface(transcript, language):
    assert reply_language(transcript) == language


def test_transcription_sends_no_language_hint():
    captured = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=MIXED, language="ar")

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions()))
    m4a = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64
    result = TranscriptionService(client=client).transcribe(filename="voice.m4a", content_type="audio/mp4", content=m4a)
    assert result.transcript == MIXED
    assert "language" not in captured  # never pinned to the UI's language
    assert "mixed Arabic-English" in captured["prompt"]


def test_the_interpretation_prompt_keeps_english_terms_and_identifiers():
    prompt = _SYSTEM_PROMPT_TEMPLATE
    assert "MIXED LANGUAGE" in prompt
    assert "do NOT translate" in prompt
    assert "TSK-001" in prompt


# --- System administration is not project access (QA-06B) ------------------------
# The Office Administrator held `platform.view_all_projects`, which opened every
# project's work, plus every execution permission. It now opens the registry —
# list, details, team, parties — and the work only on projects they are on.
# Office leadership keeps working everywhere through
# `platform.work_in_all_projects`.


@pytest.fixture()
def office_admin(db, site):
    from app.core.security import hash_password
    from app.models.audit_log import AuditLog
    from app.models.user import User
    from app.models.enums import UserStatus
    from app.services import rbac
    from tests.test_task_update_reliability import PASSWORD

    role = rbac.seed_roles(db)["org_admin"]
    admin = User(full_name="QA Admin", email=f"qa.admin.{uuid.uuid4().hex[:10]}@constro.io",
                 hashed_password=hash_password(PASSWORD), status=UserStatus.ACTIVE,
                 company_id=site["office"].id, org_role_id=role.id, is_internal=True)
    db.add(admin)
    db.commit()
    try:
        yield admin
    finally:
        db.rollback()
        from app.models.project import ProjectMember
        db.query(ProjectMember).filter(ProjectMember.user_id == admin.id).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.actor_id == admin.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == admin.id).delete(synchronize_session=False)
        db.commit()


def test_the_administrator_still_lists_and_staffs_a_project_they_are_not_on(client, site, office_admin):
    headers = _auth(client, office_admin)
    project_id = site["project"].id
    listed = client.get("/api/v1/projects", headers=headers, params={"limit": 200})
    assert listed.status_code == 200, listed.text
    for path in ("", "/members", "/parties", "/approval-workflow"):
        response = client.get(f"/api/v1/projects/{project_id}{path}", headers=headers)
        assert response.status_code == 200, (path, response.text)


def test_the_administrator_does_not_open_the_work_of_a_project_they_are_not_on(client, site, office_admin):
    headers = _auth(client, office_admin)
    project_id = site["project"].id
    for path in (f"/api/v1/tasks/project/{project_id}", f"/api/v1/dashboard/projects/{project_id}",
                 f"/api/v1/issues?project_id={project_id}"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.status_code, response.text)


def test_the_interface_is_told_only_the_registry_side_on_such_a_project(client, site, office_admin):
    headers = _auth(client, office_admin)
    codes = client.get("/api/v1/access-control/me", headers=headers,
                       params={"project_id": str(site["project"].id)}).json()
    assert "project.manage_members" in codes and "project.manage_parties" in codes
    assert "task.view" not in codes and "document.view" not in codes and "ifc.view" not in codes
    # Office-wide administration is untouched.
    assert "platform.manage_users" in codes


def test_joining_the_team_gives_the_administrator_the_work(client, db, site, office_admin):
    headers = _auth(client, office_admin)
    project_id = site["project"].id
    added = client.post(f"/api/v1/projects/{project_id}/members", headers=headers,
                        json={"userId": str(office_admin.id)})
    assert added.status_code == 200, added.text
    assert client.get(f"/api/v1/tasks/project/{project_id}", headers=headers).status_code == 200


def test_the_split_is_in_the_catalogue_and_on_the_leadership_templates():
    from app.core.permission_catalogue import BY_CODE
    from app.core.role_templates import TEMPLATES

    assert BY_CODE["platform.work_in_all_projects"].project_scoped is False
    holders = {t.code for t in TEMPLATES if "platform.work_in_all_projects" in t.permissions()}
    assert holders == {"office_director", "technical_director"}
    assert {code for code, p in BY_CODE.items() if p.registry} == {
        "project.manage_members", "project.edit", "project.delete",
        "project.manage_parties", "project.invite_external",
    }
