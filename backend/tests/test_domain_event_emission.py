"""Every declared domain event must have a real emission path.

`IMPORTANT_EVENTS` declares fourteen event types and `emit_domain_event` refuses
anything outside that list — so the vocabulary was complete and enforced. What
was missing was the other half: seven of the fourteen were declared, subscribed
to by agents, and **never emitted anywhere in the codebase**. Four of the five
agents therefore had no automatic trigger at all, and the Document Consistency
Agent had none whatsoever.

The tests below assert the emissions exist, that they carry the project scope a
subscriber needs, and — the part that is easy to get wrong — that an operation
which *fails* announces nothing. An event emitted before its transaction commits
is a lie a subscriber cannot detect.

`PROJECT_STRUCTURE_CHANGED` is deliberately excluded from the "everything is
emitted" assertion. It is the one declared type with no subscriber and no
defined domain trigger, and `test_agent_autonomous_detection` uses it precisely
as its example of an event nobody listens to. Emitting it would mean inventing a
meaning for it; the exclusion is recorded here so the gap stays visible instead
of being quietly forgotten.
"""

from __future__ import annotations

import datetime
import re
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.ai_governance import DomainEvent
from app.models.company import Company
from app.models.design_change import DesignChange
from app.models.enums import (
    FieldSubmissionStatus, ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.field_submission import FieldSubmission
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services import rbac
# Imported at module scope, not inside the tests. `app.api.__init__` pulls in
# every router in the application (openai, fastapi.openapi, ifcopenshell and
# the rest), which costs minutes on a cold interpreter — and a function-level
# import charges all of it to whichever test happens to run first, which read
# as a 200-second test that was doing nothing of the sort.
from app.api.field_submissions import _emit_field_submission_event
from app.api.issues import create_issue
from app.schemas.issue import IssueCreate
from app.models.enums import IssueSeverity
from app.services.domain_event_dispatcher import (
    IMPORTANT_EVENTS, emit_domain_event,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent

#: Declared, but with no subscriber and no defined trigger. See the module
#: docstring — this is a known gap, not an oversight in these tests.
UNEMITTED_BY_DESIGN = {"PROJECT_STRUCTURE_CHANGED"}


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


# --- the static guarantee ---------------------------------------------------

def test_every_declared_event_has_an_emission_site():
    """A declared event nobody emits is a subscription that can never fire.

    Read out of the source rather than exercised, because several of these are
    emitted from paths that need an IFC file or a voice recording to reach. The
    behavioural tests below cover the ones this change added.
    """
    emitted: set[str] = set()
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if "emit_domain_event(" not in source and "event_type=event_type" not in source:
            continue
        # Both the literal form and the conditional form used by the IFC path.
        for match in re.finditer(r'event_type=\s*(.+)', source):
            emitted.update(re.findall(r'"(\w+)"', match.group(1)))
        # The two field-submission events travel through a helper that takes the
        # type as an argument, so pick up the call sites too.
        emitted.update(re.findall(r'_emit_field_submission_event\([^)]*"(\w+)"', source))

    missing = (set(IMPORTANT_EVENTS) - emitted) - UNEMITTED_BY_DESIGN
    assert not missing, (
        f"declared but never emitted: {sorted(missing)}. An agent subscribing to "
        "one of these can never be triggered by it."
    )


def test_the_known_gap_is_still_only_the_one():
    """Fail if a *new* event type is declared without an emission path.

    Without this, the exclusion above becomes a place to hide the next one.
    """
    assert UNEMITTED_BY_DESIGN <= set(IMPORTANT_EVENTS)
    assert len(IMPORTANT_EVENTS) == 14


# --- behaviour --------------------------------------------------------------

@pytest.fixture()
def world(db):
    suffix = uuid.uuid4().hex[:10]
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    role = roles["project_manager"]

    office = Company(name=f"Event Office {suffix}", kind="CONSULTING_OFFICE", is_active=True)
    db.add(office)
    db.flush()

    manager = User(
        full_name=f"EventPm{suffix}", email=f"eventpm.{suffix}@constro.io",
        hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE,
        company_id=office.id, org_role_id=role.id, is_internal=role.is_internal_only,
    )
    db.add(manager)
    db.flush()

    project = Project(
        name=f"Event Project {suffix}", status=ProjectStatus.ACTIVE,
        company_id=office.id, project_manager_id=manager.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id, user_id=manager.id, role_on_project=manager.role,
        project_role_id=role.id, is_active=True,
    ))
    db.flush()

    task = Task(
        project_id=project.id, name=f"Event task {suffix}",
        task_code=f"E-{suffix[:6].upper()}", status=TaskStatus.IN_PROGRESS,
        created_by_id=manager.id,
    )
    db.add(task)
    db.commit()

    created = {"office": office, "manager": manager, "project": project, "task": task}
    try:
        yield created
    finally:
        db.rollback()
        db.query(DomainEvent).filter(DomainEvent.project_id == project.id).delete(
            synchronize_session=False
        )
        for model in (Issue, DesignChange, FieldSubmission, Task, ProjectMember):
            db.query(model).filter(model.project_id == project.id).delete(
                synchronize_session=False
            )
        db.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
        db.query(User).filter(User.id == manager.id).delete(synchronize_session=False)
        db.query(Company).filter(Company.id == office.id).delete(synchronize_session=False)
        db.commit()


def _events(db, project_id, event_type: str) -> list[DomainEvent]:
    return (
        db.query(DomainEvent)
        .filter(DomainEvent.project_id == project_id, DomainEvent.event_type == event_type)
        .all()
    )


def test_creating_an_issue_emits_issue_created(db, world):
    issue = create_issue(
        issue_data=IssueCreate(
            project_id=world["project"].id, title="Event issue",
            description="Raised to check the event fires.",
            severity=IssueSeverity.HIGH,
        ),
        db=db, current_user=world["manager"],
    )
    events = _events(db, world["project"].id, "ISSUE_CREATED")
    assert len(events) == 1
    assert events[0].entity_id == issue.id
    assert events[0].entity_type == "ISSUE"
    assert events[0].actor_user_id == world["manager"].id
    assert events[0].payload_json["severity"] == "high"


def test_a_rejected_issue_emits_nothing(db, world):
    """A failed operation must not announce itself.

    The emission sits after every validation and before the commit, so a refusal
    leaves no event behind — checked by asking for a project the caller cannot
    reach, which raises before the row is written.
    """
    from fastapi import HTTPException
    stranger = User(
        full_name="EventStranger", email=f"stranger.{uuid.uuid4().hex[:8]}@constro.io",
        hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
    )
    db.add(stranger)
    db.flush()

    with pytest.raises(HTTPException):
        create_issue(
            issue_data=IssueCreate(
                project_id=world["project"].id, title="Refused issue",
                description="Should never be announced.", severity=IssueSeverity.LOW,
            ),
            db=db, current_user=stranger,
        )
    db.rollback()
    assert _events(db, world["project"].id, "ISSUE_CREATED") == []
    db.query(User).filter(User.id == stranger.id).delete(synchronize_session=False)
    db.commit()


def test_completing_a_task_emits_task_completed_once(db, world):
    """Two routes reach DONE; the stable key means one completion is one event."""
    task = world["task"]
    task.actual_end_date = datetime.date.today()
    db.flush()

    for _ in range(2):
        emit_domain_event(
            db, project_id=task.project_id, event_type="TASK_COMPLETED",
            entity_type="TASK", entity_id=task.id, actor_user_id=world["manager"].id,
            payload={"taskCode": task.task_code, "route": "EXECUTION_COMPLETED"},
            correlation_id=f"task:{task.id}",
            idempotency_key=f"TASK_COMPLETED:{task.id}",
        )
    assert len(_events(db, task.project_id, "TASK_COMPLETED")) == 1


def test_task_updated_is_not_collapsed_across_occurrences(db, world):
    """The opposite rule, and the reason each event chose its key deliberately.

    A task is updated many times and each is a real occurrence. Giving this the
    stable key that suits `TASK_COMPLETED` would mean the Schedule Risk Agent
    heard about the first update to a task and never another.
    """
    task = world["task"]
    for _ in range(2):
        emit_domain_event(
            db, project_id=task.project_id, event_type="TASK_UPDATED",
            entity_type="TASK", entity_id=task.id, actor_user_id=world["manager"].id,
            payload={"taskCode": task.task_code, "status": task.status.value},
            correlation_id=f"task:{task.id}",
        )
    assert len(_events(db, task.project_id, "TASK_UPDATED")) == 2


def test_verifying_field_evidence_emits_field_submission_verified(db, world):
    submission = FieldSubmission(
        project_id=world["project"].id, task_id=world["task"].id,
        submitted_by_id=world["manager"].id, status=FieldSubmissionStatus.VERIFIED,
    )
    db.add(submission)
    db.flush()

    _emit_field_submission_event(
        db, submission, world["manager"], "FIELD_SUBMISSION_VERIFIED"
    )
    events = _events(db, world["project"].id, "FIELD_SUBMISSION_VERIFIED")
    assert len(events) == 1
    assert events[0].entity_id == submission.id
    assert events[0].payload_json["taskId"] == str(world["task"].id)


def test_the_two_verification_routes_do_not_double_announce(db, world):
    """Verify and verify-and-apply end in the same state and share one key."""
    submission = FieldSubmission(
        project_id=world["project"].id, task_id=world["task"].id,
        submitted_by_id=world["manager"].id, status=FieldSubmissionStatus.VERIFIED,
    )
    db.add(submission)
    db.flush()

    for _ in range(2):
        _emit_field_submission_event(
            db, submission, world["manager"], "FIELD_SUBMISSION_VERIFIED"
        )
    assert len(_events(db, world["project"].id, "FIELD_SUBMISSION_VERIFIED")) == 1


def test_every_new_event_carries_the_project_it_belongs_to(db, world):
    """Project scope is what an event-driven agent run is authorized against.

    `event_subscriber` resolves the analysis principal from `event.project_id`;
    an event without it would either fail to run or, worse, run against the
    wrong project's manager.
    """
    for event_type, entity_type in (
        ("DOCUMENT_UPLOADED", "DOCUMENT"),
        ("DESIGN_CHANGE_CREATED", "DESIGN_CHANGE"),
        ("ISSUE_CREATED", "ISSUE"),
        ("TASK_UPDATED", "TASK"),
        ("TASK_COMPLETED", "TASK"),
        ("FIELD_SUBMISSION_VERIFIED", "FIELD_SUBMISSION"),
    ):
        event = emit_domain_event(
            db, project_id=world["project"].id, event_type=event_type,
            entity_type=entity_type, entity_id=world["task"].id,
            actor_user_id=world["manager"].id, payload={},
        )
        assert event.project_id == world["project"].id, event_type
        assert event.actor_user_id == world["manager"].id, event_type
        assert event.status in {"PROCESSED_RULES_ONLY", "RETRY", "FAILED"}, event_type
