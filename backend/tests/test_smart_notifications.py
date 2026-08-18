"""Smart notifications: priority, deduplication, state-awareness, escalation.

The load-bearing promise of this system is that repeated evaluation is safe.
Every reminder test therefore runs the sweep at least twice and asserts the
second run is a no-op, and every "stop" test changes the underlying object and
asserts the reminders genuinely cease.
"""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.collaboration import ReminderEvent
from app.models.enums import (
    IssueSeverity, IssueStatus, NotificationType, ProjectStatus,
    TaskStatus, UserRole, UserStatus,
)
from app.models.issue import Issue
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.services.notification_service import (
    PRIORITY_CRITICAL, PRIORITY_IMPORTANT, PRIORITY_NORMAL,
    deadline_stage, escalate_for_context, notify, priority_rank,
)
from app.services.reminder_service import (
    evaluate_project_reminders, evaluate_task_deadlines,
)


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

    def user(name, role, affiliation=None):
        person = User(full_name=name, email=f"{name.lower()}.{suffix}@constro.io",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      engineer_affiliation=affiliation)
        db.add(person)
        return person

    people = {
        "manager": user("SnPm", UserRole.PROJECT_MANAGER),
        "engineer": user("SnEngineer", UserRole.ENGINEER, "main_contractor"),
        "other": user("SnOther", UserRole.ENGINEER, "main_contractor"),
    }
    db.flush()
    project = Project(name=f"Smart Notify {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["manager"].id, project_manager_id=people["manager"].id)
    other_project = Project(name=f"Unrelated Notify {suffix}", status=ProjectStatus.ACTIVE,
                            owner_id=people["manager"].id, project_manager_id=people["manager"].id)
    db.add_all([project, other_project])
    db.flush()
    for person in (people["engineer"], people["other"]):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()
    people["project"] = project
    people["other_project"] = other_project
    people["suffix"] = suffix
    people["db"] = db
    yield people
    _purge(db, [project.id, other_project.id],
           [p.id for p in people.values() if isinstance(p, User)])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM reminder_events WHERE project_id = ANY(:projects) OR recipient_id = ANY(:users)",
        "DELETE FROM reminder_rules WHERE project_id = ANY(:projects)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM site_reports WHERE project_id = ANY(:projects)",
        "DELETE FROM issues WHERE project_id = ANY(:projects)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM task_dependencies WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


def _task(db, world, *, days_from_today, status=TaskStatus.IN_PROGRESS,
          assignee=None, critical=False, code=None):
    task = Task(
        project_id=world["project"].id,
        name=f"Task {code or uuid4().hex[:4]}",
        task_code=code or f"T-{uuid4().hex[:6]}",
        status=status,
        planned_end_date=date.today() + timedelta(days=days_from_today),
        is_critical_path=critical,
        created_by_id=world["manager"].id,
    )
    db.add(task)
    db.flush()
    task.assignees.append(assignee or world["engineer"])
    db.flush()
    return task


def _notifications(db, user_id, category=None):
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if category:
        query = query.filter(Notification.category == category)
    return query.all()


# --- deduplication: the core promise ----------------------------------------

def test_notify_without_a_dedupe_key_repeats(db, world):
    """One-off events (a new message) must arrive every time they happen."""
    for _ in range(2):
        notify(db, user_id=world["engineer"].id, title="New message", message="hi",
               project_id=world["project"].id)
    assert len(_notifications(db, world["engineer"].id)) == 2


def test_notify_with_a_dedupe_key_fires_once(db, world):
    first = notify(db, user_id=world["engineer"].id, title="Due", message="x",
                   project_id=world["project"].id, dedupe_key="k1")
    second = notify(db, user_id=world["engineer"].id, title="Due", message="x",
                    project_id=world["project"].id, dedupe_key="k1")
    assert first is not None and second is None
    assert len(_notifications(db, world["engineer"].id)) == 1


def test_the_same_dedupe_key_still_reaches_a_different_user(db, world):
    notify(db, user_id=world["engineer"].id, title="Due", message="x", dedupe_key="shared")
    notify(db, user_id=world["other"].id, title="Due", message="x", dedupe_key="shared")
    assert len(_notifications(db, world["engineer"].id)) == 1
    assert len(_notifications(db, world["other"].id)) == 1


# --- deadline stages and time boundaries ------------------------------------

@pytest.mark.parametrize("days,expected", [
    (5, None), (3, None), (2, None),
    (1, "DUE_TOMORROW"), (0, "DUE_TODAY"),
    (-1, "OVERDUE"), (-3, "OVERDUE_SEVERAL"), (-8, "OVERDUE_WEEK"),
])
def test_deadline_stage_boundaries(db, world, days, expected):
    task = _task(db, world, days_from_today=days)
    stage = deadline_stage(task, date.today())
    assert (stage[0] if stage else None) == expected


def test_a_completed_task_has_no_deadline_stage(db, world):
    task = _task(db, world, days_from_today=-5, status=TaskStatus.DONE)
    assert deadline_stage(task, date.today()) is None


def test_a_cancelled_task_has_no_deadline_stage(db, world):
    task = _task(db, world, days_from_today=0, status=TaskStatus.CANCELLED)
    assert deadline_stage(task, date.today()) is None


def test_priority_rises_with_the_deadline_stage(db, world):
    tomorrow = deadline_stage(_task(db, world, days_from_today=1), date.today())
    today = deadline_stage(_task(db, world, days_from_today=0), date.today())
    week = deadline_stage(_task(db, world, days_from_today=-9), date.today())
    assert priority_rank(tomorrow[1]) < priority_rank(today[1]) <= priority_rank(week[1])
    assert week[1] == PRIORITY_CRITICAL


def test_an_overdue_critical_path_task_escalates_to_critical(db, world):
    task = _task(db, world, days_from_today=-1, critical=True)
    stage, priority = deadline_stage(task, date.today())
    assert escalate_for_context(task, stage, priority) == PRIORITY_CRITICAL


def test_an_upcoming_task_never_escalates_on_context(db, world):
    """Only a missed date is worth shouting about; a critical-path task that is
    merely due tomorrow is still just due tomorrow."""
    task = _task(db, world, days_from_today=1, critical=True)
    stage, priority = deadline_stage(task, date.today())
    assert escalate_for_context(task, stage, priority) == PRIORITY_NORMAL


# --- deadline sweep: idempotent, state-aware --------------------------------

def test_the_deadline_sweep_notifies_the_assignee_once(db, world):
    _task(db, world, days_from_today=1)
    assert evaluate_task_deadlines(db, world["project"].id) == 1
    # Running again observes the same state and must add nothing.
    assert evaluate_task_deadlines(db, world["project"].id) == 0
    notifications = _notifications(db, world["engineer"].id, category="DEADLINE")
    assert len(notifications) == 1
    assert notifications[0].priority == PRIORITY_NORMAL
    assert notifications[0].message_key == "taskDeadline.DUE_TOMORROW"


def test_a_task_progresses_from_due_tomorrow_to_due_today_to_overdue(db, world):
    """Each stage is its own notification — the old implementation deduped on
    title, so a task could only ever warn once and its text then froze."""
    task = _task(db, world, days_from_today=1)
    evaluate_task_deadlines(db, world["project"].id)

    task.planned_end_date = date.today()
    db.flush()
    evaluate_task_deadlines(db, world["project"].id)

    task.planned_end_date = date.today() - timedelta(days=1)
    db.flush()
    evaluate_task_deadlines(db, world["project"].id)

    stages = {n.message_key for n in _notifications(db, world["engineer"].id, category="DEADLINE")}
    assert stages == {
        "taskDeadline.DUE_TOMORROW", "taskDeadline.DUE_TODAY", "taskDeadline.OVERDUE",
    }


def test_completing_a_task_stops_further_deadline_notifications(db, world):
    task = _task(db, world, days_from_today=1)
    evaluate_task_deadlines(db, world["project"].id)
    before = len(_notifications(db, world["engineer"].id, category="DEADLINE"))

    task.status = TaskStatus.DONE
    task.planned_end_date = date.today() - timedelta(days=2)
    db.flush()
    assert evaluate_task_deadlines(db, world["project"].id) == 0
    assert len(_notifications(db, world["engineer"].id, category="DEADLINE")) == before


def test_an_overdue_task_also_reaches_the_project_manager(db, world):
    _task(db, world, days_from_today=-1)
    evaluate_task_deadlines(db, world["project"].id)
    assert _notifications(db, world["manager"].id, category="DEADLINE")


def test_an_upcoming_deadline_does_not_disturb_the_manager(db, world):
    _task(db, world, days_from_today=1)
    evaluate_task_deadlines(db, world["project"].id)
    assert not _notifications(db, world["manager"].id, category="DEADLINE")


def test_deadline_evaluation_uses_the_calendar_date_not_the_utc_instant(db, world):
    """Regression: the sweep first derived "today" from `datetime.now(utc).date()`.

    For any server whose local date is ahead of UTC, that is a different day
    for part of every day — so a task due tomorrow was silently seen as two
    days out and "due today" could fire a day late. Passing an explicit
    calendar date must select exactly the stage that date implies.
    """
    task = _task(db, world, days_from_today=1)
    # Evaluated as if it were already tomorrow: the task is then due *today*.
    assert evaluate_task_deadlines(db, world["project"].id,
                                   today=date.today() + timedelta(days=1)) == 1
    keys = {n.message_key for n in _notifications(db, world["engineer"].id, category="DEADLINE")}
    assert keys == {"taskDeadline.DUE_TODAY"}


def test_deadline_notifications_do_not_leak_across_projects(db, world):
    _task(db, world, days_from_today=0)
    evaluate_task_deadlines(db, world["other_project"].id)
    assert not _notifications(db, world["engineer"].id, category="DEADLINE")


# --- site report verification reminders -------------------------------------

def _submitted_report(db, world, *, age_days=0):
    report = SiteReport(
        project_id=world["project"].id, submitted_by_id=world["engineer"].id,
        report_date=date.today(), summary_text="Slab poured.", review_status="submitted",
    )
    db.add(report)
    db.flush()
    if age_days:
        report.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
        db.flush()
    return report


def test_a_fresh_site_report_is_not_reminded_immediately(db, world):
    _submitted_report(db, world)
    evaluate_project_reminders(db, world["project"].id)
    assert not _notifications(db, world["manager"].id, category="REMINDERS")


def test_an_unverified_site_report_reminds_the_manager_once_due(db, world):
    _submitted_report(db, world, age_days=3)
    evaluate_project_reminders(db, world["project"].id)
    reminders = _notifications(db, world["manager"].id, category="REMINDERS")
    assert len(reminders) == 1
    # A second sweep at the same moment must not repeat it.
    evaluate_project_reminders(db, world["project"].id)
    assert len(_notifications(db, world["manager"].id, category="REMINDERS")) == 1


def test_verifying_a_site_report_stops_its_reminders(db, world):
    report = _submitted_report(db, world, age_days=3)
    evaluate_project_reminders(db, world["project"].id)
    before = len(_notifications(db, world["manager"].id, category="REMINDERS"))

    report.review_status = "approved"
    db.flush()
    # Far enough in the future that another reminder would certainly be due.
    evaluate_project_reminders(db, world["project"].id,
                              now=datetime.now(timezone.utc) + timedelta(days=30))
    assert len(_notifications(db, world["manager"].id, category="REMINDERS")) == before


def test_a_manager_is_not_reminded_about_their_own_report(db, world):
    report = SiteReport(project_id=world["project"].id, submitted_by_id=world["manager"].id,
                        report_date=date.today(), summary_text="Own report",
                        review_status="submitted")
    db.add(report)
    db.flush()
    report.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    db.flush()
    evaluate_project_reminders(db, world["project"].id)
    assert not _notifications(db, world["manager"].id, category="REMINDERS")


# --- issue reminders ---------------------------------------------------------

def _issue(db, world, severity, *, age_days=5, status=IssueStatus.OPEN, assignee=None):
    issue = Issue(project_id=world["project"].id, title=f"Issue {uuid4().hex[:4]}",
                  description="x", severity=severity, status=status,
                  raised_by_id=world["engineer"].id,
                  assigned_to_id=assignee.id if assignee else None)
    db.add(issue)
    db.flush()
    issue.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    db.flush()
    return issue


def test_a_high_severity_unresolved_issue_is_reminded(db, world):
    _issue(db, world, IssueSeverity.HIGH)
    evaluate_project_reminders(db, world["project"].id)
    assert _notifications(db, world["manager"].id, category="REMINDERS")


def test_a_low_severity_issue_is_never_chased(db, world):
    """Nudging about every minor open issue is the spam this system avoids."""
    _issue(db, world, IssueSeverity.LOW, age_days=90)
    evaluate_project_reminders(db, world["project"].id)
    assert not _notifications(db, world["manager"].id, category="REMINDERS")


def test_resolving_an_issue_stops_its_reminders(db, world):
    issue = _issue(db, world, IssueSeverity.CRITICAL)
    evaluate_project_reminders(db, world["project"].id)
    before = len(_notifications(db, world["manager"].id, category="REMINDERS"))

    issue.status = IssueStatus.RESOLVED
    db.flush()
    evaluate_project_reminders(db, world["project"].id,
                              now=datetime.now(timezone.utc) + timedelta(days=30))
    assert len(_notifications(db, world["manager"].id, category="REMINDERS")) == before


def test_a_critical_issue_reminder_carries_critical_priority(db, world):
    _issue(db, world, IssueSeverity.CRITICAL)
    evaluate_project_reminders(db, world["project"].id)
    reminders = _notifications(db, world["manager"].id, category="REMINDERS")
    assert reminders and reminders[0].priority == PRIORITY_CRITICAL


def test_an_assigned_issue_reminds_the_assignee_not_the_manager(db, world):
    _issue(db, world, IssueSeverity.HIGH, assignee=world["engineer"])
    evaluate_project_reminders(db, world["project"].id)
    assert _notifications(db, world["engineer"].id, category="REMINDERS")
    assert not _notifications(db, world["manager"].id, category="REMINDERS")


# --- escalation over repeated sweeps ----------------------------------------

def test_reminders_stop_at_the_configured_maximum_and_escalate_in_priority(db, world):
    """Repeated sweeps must chase, get louder, then fall silent — never loop."""
    _submitted_report(db, world, age_days=3)
    now = datetime.now(timezone.utc)
    for step in range(6):
        evaluate_project_reminders(db, world["project"].id, now=now + timedelta(days=step * 2))

    reminders = _notifications(db, world["manager"].id, category="REMINDERS")
    events = db.query(ReminderEvent).filter(
        ReminderEvent.target_type == "SITE_REPORT",
        ReminderEvent.recipient_id == world["manager"].id,
    ).all()
    # The default rule permits three nudges; the loop ran six times.
    assert len(reminders) == 3 == len(events)
    priorities = [priority_rank(item.priority) for item in
                  sorted(reminders, key=lambda value: value.created_at)]
    assert priorities == sorted(priorities), "priority must never decrease"
    assert priorities[-1] > priorities[0], "the final nudge must be louder than the first"
