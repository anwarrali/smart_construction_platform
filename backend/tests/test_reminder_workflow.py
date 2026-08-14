"""Reminders must chase unanswered work without becoming notification spam.

The rules live in `collaboration_policy`; this exercises the whole loop against
the real database: an unanswered client request produces one reminder when it
is due, produces nothing on a repeat sweep, escalates on the configured
interval, stops at the maximum, and stops immediately once the request has been
handled.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.collaboration import OwnerRequest, ReminderEvent
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.reminder_service import evaluate_project_reminders


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

    def user(name, role):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE)

    owner = user("Client", UserRole.OWNER)
    manager = user("Lead", UserRole.PROJECT_MANAGER)
    engineer = user("Responsible", UserRole.ENGINEER)
    db.add_all([owner, manager, engineer])
    db.flush()

    project = Project(name=f"Reminder Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=engineer.id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()
    try:
        yield {"db": db, "project": project, "owner": owner, "manager": manager, "engineer": engineer}
    finally:
        _purge(db, project.id, [owner.id, manager.id, engineer.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    for statement in (
        "DELETE FROM reminder_events WHERE project_id = :project",
        "DELETE FROM notifications WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM owner_requests WHERE project_id = :project",
        "DELETE FROM audit_logs WHERE project_id = :project OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = :project",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), {"project": project_id, "users": list(user_ids)})
    db.commit()


SUBMITTED_AT = datetime.now(timezone.utc) - timedelta(days=10)


def _request(world, *, priority="NORMAL", status="ASSIGNED"):
    item = OwnerRequest(
        project_id=world["project"].id, created_by_id=world["owner"].id,
        assigned_to_id=world["engineer"].id, title="Kitchen window position",
        description="Client asks whether the window can move north.",
        category="DESIGN_MODIFICATION", discipline="civil",
        priority=priority, status=status,
    )
    world["db"].add(item)
    world["db"].flush()
    # created_at is server-defaulted; the waiting clock is what matters here.
    item.created_at = SUBMITTED_AT
    world["db"].flush()
    return item


def _sweep(world, minutes_after_submission):
    return evaluate_project_reminders(
        world["db"], world["project"].id,
        now=SUBMITTED_AT + timedelta(minutes=minutes_after_submission),
    )["created"]


def _reminders(world):
    # The session is configured with autoflush=False and the service leaves the
    # commit to its caller, so pending rows must be flushed to be counted.
    world["db"].flush()
    return world["db"].query(ReminderEvent).filter(
        ReminderEvent.project_id == world["project"].id).count()


def test_a_fresh_request_is_not_reminded(world):
    _request(world)
    # The NORMAL default waits a full day before the first nudge.
    assert _sweep(world, 30) == 0
    assert _reminders(world) == 0


def test_an_unanswered_request_is_reminded_once_it_is_due(world):
    _request(world)
    assert _sweep(world, 25 * 60) == 1
    assert _reminders(world) == 1


def test_the_reminder_reaches_the_assigned_person_only(world):
    _request(world)
    _sweep(world, 25 * 60)
    world["db"].flush()
    notified = {row.user_id for row in world["db"].query(Notification).filter(
        Notification.category == "REMINDERS",
        Notification.project_id == world["project"].id).all()}
    assert notified == {world["engineer"].id}, "only the person who owes the answer is chased"


def test_sweeping_again_immediately_does_not_send_a_second_reminder(world):
    """The exact spam case: the scheduler runs every few minutes."""
    _request(world)
    assert _sweep(world, 25 * 60) == 1
    assert _sweep(world, 25 * 60 + 5) == 0
    assert _sweep(world, 25 * 60 + 10) == 0
    assert _reminders(world) == 1


def test_a_second_reminder_waits_for_the_repeat_interval(world):
    _request(world)
    _sweep(world, 25 * 60)
    assert _sweep(world, 49 * 60) == 1
    assert _reminders(world) == 2


def test_reminders_stop_at_the_configured_maximum(world):
    _request(world)
    for hours in (25, 49, 73, 97, 121, 145):
        _sweep(world, hours * 60)
    assert _reminders(world) == 3, "the default maximum is three attempts"


def test_answering_the_request_stops_the_reminders(world):
    item = _request(world)
    assert _sweep(world, 25 * 60) == 1

    item.status = "COMPLETED"
    item.responded_at = datetime.now(timezone.utc)
    world["db"].flush()

    assert _sweep(world, 49 * 60) == 0, "a handled request must never be chased again"
    assert _reminders(world) == 1


def test_a_critical_request_is_chased_sooner_than_a_normal_one(world):
    _request(world, priority="CRITICAL")
    # CRITICAL defaults to two hours rather than a day.
    assert _sweep(world, 3 * 60) == 1
