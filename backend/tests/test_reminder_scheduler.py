"""Reminder scheduling: does it actually run, and does it stop spamming?

The pure interval rules are covered in test_accountable_collaboration_policy.
These tests cover the evaluation service and the scheduler tick against the real
database, because "the model exists" is not evidence that reminders are sent.
"""

from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal, engine
from app.models.audit_log import AuditLog
from app.models.collaboration import OwnerRequest, ReminderEvent, ReminderRule
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.notification import Notification
from app.models.project import Project
from app.models.user import User
from app.services import scheduler
from app.services.reminder_service import (
    DEFAULT_INTERVALS,
    HANDLED_MESSAGE_STATUSES,
    collect_targets,
    effective_rule,
    evaluate_all_projects,
    evaluate_project_reminders,
)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only when no database is reachable
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def scenario(db):
    """A project with an owner request that has been waiting well past its interval.

    Committed rather than kept in a transaction because `evaluate_all_projects`
    commits per project, and the scheduler tick opens its own session.
    """
    suffix = uuid4().hex[:10]
    owner = User(full_name="Reminder Owner", email=f"owner-{suffix}@test.local",
                 hashed_password="x", role=UserRole.OWNER, status=UserStatus.ACTIVE)
    engineer = User(full_name="Reminder Engineer", email=f"eng-{suffix}@test.local",
                    hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE)
    db.add_all([owner, engineer])
    db.flush()
    project = Project(name=f"Reminder Test Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id)
    db.add(project)
    db.flush()
    request = OwnerRequest(
        project_id=project.id, created_by_id=owner.id, assigned_to_id=engineer.id,
        title="Check the basement waterproofing", description="Owner reported damp walls.",
        category="QUESTION", priority="CRITICAL", status="ASSIGNED",
    )
    db.add(request)
    db.flush()
    # Waiting since long before the CRITICAL first-reminder threshold.
    request.created_at = datetime.now(timezone.utc) - timedelta(days=3)
    db.commit()
    ids = {"project": project.id, "request": request.id, "owner": owner.id, "engineer": engineer.id}
    try:
        yield {"project": project, "request": request, "owner": owner, "engineer": engineer}
    finally:
        db.rollback()
        db.query(ReminderEvent).filter(ReminderEvent.project_id == ids["project"]).delete(synchronize_session=False)
        db.query(ReminderRule).filter(ReminderRule.project_id == ids["project"]).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.project_id == ids["project"]).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.project_id == ids["project"]).delete(synchronize_session=False)
        db.query(OwnerRequest).filter(OwnerRequest.id == ids["request"]).delete(synchronize_session=False)
        db.query(Project).filter(Project.id == ids["project"]).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([ids["owner"], ids["engineer"]])).delete(synchronize_session=False)
        db.commit()


def _reminders(db, request_id):
    return db.query(ReminderEvent).filter(ReminderEvent.target_id == request_id).all()


def _notifications(db, request_id):
    return db.query(Notification).filter(Notification.related_entity_id == request_id).all()


def test_effective_rule_falls_back_to_priority_defaults_without_persisting(db):
    rule = effective_rule(db, uuid4(), "CRITICAL")
    assert (rule.first_reminder_minutes, rule.repeat_interval_minutes) == DEFAULT_INTERVALS["CRITICAL"]
    assert rule.enabled is True
    assert rule.id is None, "a default rule must never be written to the database"


def test_waiting_owner_request_is_collected_as_a_reminder_target(db, scenario):
    targets = collect_targets(db, scenario["project"].id)
    assert [t[0] for t in targets] == ["OWNER_REQUEST"]
    assert targets[0][2] == scenario["engineer"].id


def test_evaluation_creates_one_reminder_and_notifies_the_assignee(db, scenario):
    result = evaluate_project_reminders(db, scenario["project"].id)
    db.flush()
    assert result["created"] == 1
    events = _reminders(db, scenario["request"].id)
    assert len(events) == 1
    assert events[0].sequence_number == 1
    assert events[0].recipient_id == scenario["engineer"].id
    assert events[0].event_type == "REMINDER"
    notifications = _notifications(db, scenario["request"].id)
    assert len(notifications) == 1
    assert notifications[0].user_id == scenario["engineer"].id
    assert notifications[0].requires_action is True


def test_second_immediate_evaluation_does_not_duplicate_the_reminder(db, scenario):
    evaluate_project_reminders(db, scenario["project"].id)
    db.flush()
    second = evaluate_project_reminders(db, scenario["project"].id)
    db.flush()
    assert second["created"] == 0, "repeat interval must suppress a same-minute second reminder"
    assert len(_reminders(db, scenario["request"].id)) == 1


def test_reminders_stop_at_the_configured_maximum(db, scenario):
    now = datetime.now(timezone.utc)
    for index in range(5):
        # Each sweep is a full repeat interval later than the previous one.
        evaluate_project_reminders(db, scenario["project"].id, now=now + timedelta(hours=3 * index))
        db.flush()
    assert len(_reminders(db, scenario["request"].id)) == 3, "default maximum is 3 reminders"


def test_quiet_hours_suppress_dispatch(db, scenario):
    db.add(ReminderRule(
        project_id=scenario["project"].id, target_type="IMPORTANT_COMMUNICATION", priority="CRITICAL",
        first_reminder_minutes=120, repeat_interval_minutes=120, maximum_reminders=3,
        quiet_hours_start=time(0, 0), quiet_hours_end=time(23, 59), enabled=True,
    ))
    db.flush()
    result = evaluate_project_reminders(
        db, scenario["project"].id, now=datetime(2026, 8, 13, 3, 0, tzinfo=timezone.utc),
    )
    assert result["created"] == 0
    assert not _reminders(db, scenario["request"].id)


def test_a_disabled_rule_stops_reminders_entirely(db, scenario):
    db.add(ReminderRule(
        project_id=scenario["project"].id, target_type="IMPORTANT_COMMUNICATION", priority="CRITICAL",
        first_reminder_minutes=1, repeat_interval_minutes=1, maximum_reminders=5, enabled=False,
    ))
    db.flush()
    assert evaluate_project_reminders(db, scenario["project"].id)["created"] == 0


def test_final_reminder_escalates_to_the_configured_recipient(db, scenario):
    db.add(ReminderRule(
        project_id=scenario["project"].id, target_type="IMPORTANT_COMMUNICATION", priority="CRITICAL",
        first_reminder_minutes=60, repeat_interval_minutes=60, maximum_reminders=2,
        escalation_recipient_id=scenario["owner"].id, enabled=True,
    ))
    db.flush()
    now = datetime.now(timezone.utc)
    evaluate_project_reminders(db, scenario["project"].id, now=now)
    db.flush()
    evaluate_project_reminders(db, scenario["project"].id, now=now + timedelta(hours=2))
    db.flush()
    events = sorted(_reminders(db, scenario["request"].id), key=lambda item: item.sequence_number)
    assert [item.event_type for item in events] == ["REMINDER", "ESCALATION"]
    assert events[1].recipient_id == scenario["owner"].id
    assert events[1].metadata_json["originalRecipientId"] == str(scenario["engineer"].id)


def test_handled_request_is_no_longer_a_target(db, scenario):
    scenario["request"].status = "COMPLETED"
    db.flush()
    assert collect_targets(db, scenario["project"].id) == []


def test_read_is_not_treated_as_handled():
    # READ deliberately stays actionable: only an answer or a resolution closes it.
    assert "READ" not in HANDLED_MESSAGE_STATUSES
    assert HANDLED_MESSAGE_STATUSES == ["RESPONDED", "RESOLVED"]


def test_dispatch_is_written_to_the_audit_trail(db, scenario):
    evaluate_project_reminders(db, scenario["project"].id)
    db.flush()
    entries = db.query(AuditLog).filter(
        AuditLog.project_id == scenario["project"].id,
        AuditLog.action == "reminders_dispatched",
    ).all()
    assert len(entries) == 1
    assert entries[0].actor_id is None, "a scheduler sweep has no human actor"
    assert '"trigger": "SCHEDULER"' in entries[0].details


def test_evaluation_is_scoped_to_one_project(db, scenario):
    other = uuid4()
    assert collect_targets(db, other) == []
    assert evaluate_project_reminders(db, other)["evaluated"] == 0


def test_scheduler_tick_runs_against_the_real_database_and_takes_the_lock():
    result = scheduler.run_reminder_tick()
    assert not result.get("skipped"), "the lock must be free in a single-process test run"
    assert {"projects", "created", "evaluated", "failed"} <= set(result)
    assert result["failed"] == 0


def test_a_second_worker_skips_the_sweep_while_the_lock_is_held():
    """Two uvicorn workers must not dispatch the same reminder twice."""
    holder = engine.connect()
    try:
        assert holder.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": scheduler.REMINDER_LOCK_KEY},
        ).scalar() is True
        result = scheduler.run_reminder_tick()
        assert result["skipped"] is True
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": scheduler.REMINDER_LOCK_KEY})
        holder.commit()
        holder.close()
    # The lock must be free again once the other worker finishes.
    assert not scheduler.run_reminder_tick().get("skipped")


def test_scheduler_status_reports_its_configuration():
    state = scheduler.status()
    assert set(state) == {"enabled", "intervalSeconds", "running", "lastRun"}
    assert state["intervalSeconds"] >= 1


def test_evaluate_all_projects_skips_completed_and_cancelled_projects(db, scenario):
    scenario["project"].status = ProjectStatus.COMPLETED
    db.commit()
    try:
        summary = evaluate_all_projects(db)
        assert summary["failed"] == 0
        assert not _reminders(db, scenario["request"].id)
    finally:
        scenario["project"].status = ProjectStatus.ACTIVE
        db.commit()
