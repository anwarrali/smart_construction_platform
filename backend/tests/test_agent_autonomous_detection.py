"""Analysis that starts because something happened.

Three things have to hold at once for this to be safe: it must trigger, it must
not be able to break the operation that triggered it, and it must never read or
notify beyond what a real accountable person is entitled to.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.agent_run import AgentRun as AgentRunRecord
from app.models.enums import ProjectStatus, TaskStatus, UserRole, UserStatus
from app.models.ifc import AIInsight
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.agents.event_subscriber import (
    SETTLED_STATUSES, _analysis_principal, handle_event, safe_handle_event,
)
from app.services.agents.notification_policy import (
    REVIEW_CONFIDENCE, URGENT_CONFIDENCE, decide_notification,
)
from app.services.domain_event_dispatcher import emit_domain_event


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
def world(db, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_AUTO_ANALYSIS_ENABLED", True)
    suffix = uuid4().hex[:10]

    def user(name, role):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE)

    manager = user("AutoPm", UserRole.PROJECT_MANAGER)
    worker = user("AutoWorker", UserRole.WORKER)
    owner = user("AutoOwner", UserRole.OWNER)
    db.add_all([manager, worker, owner])
    db.flush()
    project = Project(name=f"Auto {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    for person, role in ((manager, UserRole.PROJECT_MANAGER), (worker, UserRole.WORKER)):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=role, is_active=True))
    task = Task(project_id=project.id, task_code="T-001", name="Blocked work",
                status=TaskStatus.BLOCKED, progress_percentage=10, created_by_id=manager.id)
    db.add(task)
    db.commit()
    try:
        yield {"project": project, "manager": manager, "worker": worker, "task": task}
    finally:
        _purge(db, project.id, [manager.id, worker.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM agent_runs WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insight_sources WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM domain_events WHERE project_id = ANY(:projects)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        try:
            db.execute(text(statement), params)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    db.commit()


def emit(db, world, event_type="TASK_PROGRESS_CHANGED", actor=None):
    return emit_domain_event(
        db, project_id=world["project"].id, event_type=event_type,
        entity_type="TASK", entity_id=world["task"].id,
        actor_user_id=(actor or world["worker"]).id,
        idempotency_key=f"{event_type}:{uuid4().hex}",
    )


def notifications(db, world):
    return db.query(Notification).filter(
        Notification.project_id == world["project"].id
    ).all()


# --- It triggers ------------------------------------------------------------

def test_an_event_starts_an_analysis_pass(db, world):
    event = emit(db, world)
    db.commit()
    runs = db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id,
        AgentRunRecord.trigger_type == "EVENT",
    ).all()
    assert runs, "the event should have started at least one agent"
    assert all(run.trigger_event_id == event.id for run in runs)


def test_the_run_records_why_it_happened(db, world):
    emit(db, world)
    db.commit()
    run = db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id
    ).first()
    assert run.trigger_type == "EVENT"
    assert "TASK_PROGRESS_CHANGED" in (run.trigger_reason or "")


def test_only_subscribed_agents_are_woken(db, world):
    emit(db, world, "TASK_PROGRESS_CHANGED")
    db.commit()
    names = {run.agent_name for run in db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id).all()}
    assert names <= {"schedule_risk_agent"}


def test_nothing_runs_when_the_feature_is_off(db, world, monkeypatch):
    """Off by default; this proves the switch actually gates it."""
    monkeypatch.setattr(settings, "AGENT_AUTO_ANALYSIS_ENABLED", False)
    emit(db, world)
    db.commit()
    assert db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id).count() == 0


def test_the_feature_is_off_by_default():
    from app.core.config import Settings

    assert Settings.model_fields["AGENT_AUTO_ANALYSIS_ENABLED"].default is False


def test_an_event_nobody_subscribes_to_starts_nothing(db, world):
    result = handle_event(db, emit(db, world, "DOCUMENT_UPLOADED"))
    # Document Consistency subscribes to this, so use one that nobody wants.
    other = emit(db, world, "PROJECT_STRUCTURE_CHANGED")
    assert handle_event(db, other)["ran"] is False


# --- Authority --------------------------------------------------------------

def test_analysis_runs_as_the_accountable_project_manager(db, world):
    principal = _analysis_principal(db, world["project"].id)
    assert principal is not None
    assert principal.id == world["manager"].id


def test_it_does_not_run_as_whoever_happened_to_trigger_it(db, world):
    """A worker's action must not give a worker's narrow visibility to analysis."""
    emit(db, world, actor=world["worker"])
    db.commit()
    run = db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id).first()
    assert run.actor_user_id == world["manager"].id
    assert run.actor_user_id != world["worker"].id


def test_a_project_without_a_manager_is_skipped_rather_than_escalated(db, world):
    """No accountable person is a reason not to analyse, not to analyse harder."""
    world["project"].project_manager_id = None
    db.commit()
    result = handle_event(db, emit(db, world))
    assert result["ran"] is False
    assert "Project Manager" in result["reason"]
    assert db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id).count() == 0


def test_an_inactive_manager_does_not_lend_authority(db, world):
    world["manager"].status = UserStatus.SUSPENDED
    db.commit()
    assert _analysis_principal(db, world["project"].id) is None


# --- It cannot break what triggered it --------------------------------------

def test_an_analysis_failure_does_not_fail_the_originating_operation(db, world, monkeypatch):
    """An upload that succeeded must not fail because analysis of it did."""
    import app.services.agents.event_subscriber as subscriber

    def explode(*_args, **_kwargs):
        raise RuntimeError("analysis exploded")

    monkeypatch.setattr(subscriber, "handle_event", explode)
    event = emit(db, world)
    db.commit()
    # The event still processed; the exception was contained.
    assert event.status == "PROCESSED_RULES_ONLY"


def test_safe_handle_event_never_raises(db, world, monkeypatch):
    import app.services.agents.event_subscriber as subscriber

    monkeypatch.setattr(subscriber, "handle_event",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    safe_handle_event(db, emit(db, world))  # must not raise


# --- Notification policy ----------------------------------------------------

@pytest.mark.parametrize("certainty, confidence, severity, expected", [
    ("DETECTED", 0.9, "HIGH", "URGENT"),
    ("DETECTED", 0.9, "CRITICAL", "URGENT"),
    ("DETECTED", 0.9, "LOW", "REVIEW_RECOMMENDED"),
    ("DETECTED", 0.7, "HIGH", "REVIEW_RECOMMENDED"),
    ("FACT", 0.4, "HIGH", "INFORMATIONAL"),
    ("UNCERTAIN", 0.3, "INFO", "INFORMATIONAL"),
    ("RECOMMENDATION", 0.7, "LOW", "REVIEW_RECOMMENDED"),
])
def test_findings_fall_into_the_right_band(certainty, confidence, severity, expected):
    assert decide_notification(
        certainty=certainty, confidence=confidence, severity=severity).band == expected


def test_a_confident_finding_about_something_trivial_is_not_urgent():
    decision = decide_notification(certainty="DETECTED", confidence=0.95, severity="LOW")
    assert decision.band != "URGENT"


def test_an_uncertain_finding_is_never_pushed():
    """"I could not tell" must not arrive as an alert."""
    decision = decide_notification(certainty="UNCERTAIN", confidence=0.3, severity="CRITICAL")
    assert decision.notify is False
    assert "could not" in decision.reason


def test_a_low_confidence_finding_is_recorded_but_not_pushed():
    decision = decide_notification(certainty="DETECTED", confidence=0.5, severity="HIGH")
    assert decision.notify is False
    assert decision.band == "INFORMATIONAL"


def test_a_recommendation_always_reaches_a_person():
    decision = decide_notification(certainty="RECOMMENDATION", confidence=0.6, severity="LOW")
    assert decision.notify is True
    assert decision.requires_action is True


def test_every_decision_explains_itself():
    for certainty in ("FACT", "DETECTED", "INFERRED", "RECOMMENDATION", "UNCERTAIN"):
        assert decide_notification(certainty=certainty, confidence=0.7, severity="HIGH").reason


def test_the_thresholds_are_ordered():
    assert REVIEW_CONFIDENCE < URGENT_CONFIDENCE


# --- Notifications carry what a reader needs --------------------------------

def test_a_notification_is_sent_for_a_qualifying_finding(db, world):
    emit(db, world)
    db.commit()
    sent = notifications(db, world)
    assert sent, "a blocked task is a high-severity, high-confidence finding"


def test_the_notification_says_what_where_and_how_confident(db, world):
    emit(db, world)
    db.commit()
    message = notifications(db, world)[0].message
    assert "Severity" in message
    assert "confidence" in message
    assert "source record" in message
    assert "Detected by:" in message


def test_the_notification_links_to_the_finding_it_is_about(db, world):
    emit(db, world)
    db.commit()
    item = notifications(db, world)[0]
    assert item.related_entity_type == "AI_INSIGHT"
    assert db.get(AIInsight, item.related_entity_id) is not None
    assert "ai-intelligence" in (item.action_url or "")


def test_the_same_finding_never_notifies_twice(db, world):
    """Re-analysis refreshes a finding; it does not re-announce it."""
    emit(db, world)
    db.commit()
    first = len(notifications(db, world))
    assert first
    emit(db, world, "TASK_UPDATED")
    db.commit()
    assert len(notifications(db, world)) == first


def test_a_dismissed_finding_does_not_notify_again(db, world):
    """Being told twice about something you dismissed teaches people to ignore it."""
    emit(db, world)
    db.commit()
    before = len(notifications(db, world))
    for insight in db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id
    ).all():
        insight.status = "FALSE_POSITIVE"
    db.query(Notification).filter(Notification.project_id == world["project"].id).delete()
    db.commit()

    emit(db, world, "TASK_UPDATED")
    db.commit()
    assert notifications(db, world) == []
    assert before > 0


def test_settled_statuses_cover_the_review_outcomes():
    assert {"RESOLVED", "DISMISSED", "FALSE_POSITIVE"} <= SETTLED_STATUSES


# --- Still nothing is done to the project -----------------------------------

def test_automatic_analysis_changes_no_project_data(db, world):
    before = (
        db.query(Task).filter(Task.project_id == world["project"].id).count(),
        world["task"].progress_percentage,
        world["task"].status,
    )
    emit(db, world)
    db.commit()
    db.refresh(world["task"])
    assert (
        db.query(Task).filter(Task.project_id == world["project"].id).count(),
        world["task"].progress_percentage,
        world["task"].status,
    ) == before


def test_findings_still_arrive_as_reviewable_not_actioned(db, world):
    emit(db, world)
    db.commit()
    stored = db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id).all()
    assert stored
    assert all(item.status == "NEW" for item in stored)
    assert all(item.applied_entity_id is None for item in stored)
