"""Scheduling a site visit must persist, notify the right people, and fail loudly.

The reported defect was "the schedule button does nothing": no visit, no success
state, no error. The largest part of that was a missing toast host in the web
client, but the API also returned a conflict payload the client could not
render, and it never notified the engineer the visit was booked for.

These tests exercise the real endpoint functions against the real database.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.collaboration import create_site_visit, list_site_visits
from app.db.database import SessionLocal
from app.models.collaboration import SiteVisit
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.collaboration import SiteVisitCreate


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
    """A project with a manager, the engineer the visit is for, and a bystander."""
    suffix = uuid4().hex[:10]

    def user(name, role):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE)

    manager = user("Manager", UserRole.PROJECT_MANAGER)
    engineer = user("Engineer", UserRole.ENGINEER)
    invited = user("Invited", UserRole.ENGINEER)
    bystander = user("Bystander", UserRole.ENGINEER)
    db.add_all([manager, engineer, invited, bystander])
    db.flush()

    project = Project(name=f"Visit Project {suffix}", status=ProjectStatus.ACTIVE,
                      project_manager_id=manager.id, location="Site A")
    db.add(project)
    db.flush()
    for person in (engineer, invited, bystander):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()
    try:
        yield {"db": db, "project": project, "manager": manager, "engineer": engineer,
               "invited": invited, "bystander": bystander}
    finally:
        # The endpoint commits, so a rollback alone would leave this fixture's
        # rows behind in whatever database the suite was pointed at.
        _purge(db, project.id, [manager.id, engineer.id, invited.id, bystander.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    for statement in (
        "DELETE FROM site_visit_participants WHERE site_visit_id IN"
        " (SELECT id FROM site_visits WHERE project_id = :project)",
        "DELETE FROM site_visits WHERE project_id = :project",
        "DELETE FROM notifications WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = :project OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = :project OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = :project",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), {"project": project_id, "users": list(user_ids)})
    db.commit()


def _payload(world, *, start, hours=2, participants=None, engineer_id=None, allow_conflict=False):
    return SiteVisitCreate(
        projectId=world["project"].id,
        engineerId=engineer_id or world["engineer"].id,
        title="Second floor formwork inspection",
        scheduledStart=start,
        scheduledEnd=start + timedelta(hours=hours),
        visitType="ROUTINE_INSPECTION",
        participantIds=[p.id for p in (participants or [])],
        allowConflict=allow_conflict,
    )


def _schedule(world, payload):
    return create_site_visit(payload, db=world["db"], current_user=world["manager"])


def _notified(world, visit_id):
    return {row.user_id for row in world["db"].query(Notification).filter(
        Notification.related_entity_id == visit_id).all()}


TOMORROW = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)


def test_a_scheduled_visit_is_persisted_and_returned(world):
    result = _schedule(world, _payload(world, start=TOMORROW, participants=[world["invited"]]))

    stored = world["db"].get(SiteVisit, result["id"])
    assert stored is not None, "the visit must exist in the database, not just in the response"
    assert stored.status == "SCHEDULED"
    assert stored.engineer_id == world["engineer"].id
    assert result["participant_ids"] == [world["invited"].id]
    # Location falls back to the project site rather than being left blank.
    assert stored.location == "Site A"


def test_a_scheduled_visit_appears_in_the_schedule_listing(world):
    result = _schedule(world, _payload(world, start=TOMORROW))
    world["db"].flush()

    listed = list_site_visits(project_id=world["project"].id, db=world["db"], current_user=world["manager"])
    assert result["id"] in {item["id"] for item in listed}


def test_only_the_participants_and_the_engineer_are_notified(world):
    result = _schedule(world, _payload(world, start=TOMORROW, participants=[world["invited"]]))

    notified = _notified(world, result["id"])
    assert world["invited"].id in notified, "an invited participant must be told"
    assert world["engineer"].id in notified, "the engineer the visit is booked for must be told"
    assert world["bystander"].id not in notified, "the rest of the project must not be spammed"
    assert world["manager"].id not in notified, "the scheduler does not notify themselves"


def test_an_overlapping_visit_is_blocked_with_a_readable_conflict(world):
    _schedule(world, _payload(world, start=TOMORROW))
    world["db"].flush()

    with pytest.raises(HTTPException) as raised:
        _schedule(world, _payload(world, start=TOMORROW + timedelta(minutes=30)))

    assert raised.value.status_code == 409
    conflict = raised.value.detail["conflicts"][0]
    # The client renders this directly; ids alone were not enough to show.
    assert conflict["title"] == "Second floor formwork inspection"
    assert conflict["projectName"] == world["project"].name
    assert conflict["scheduledStart"] and conflict["scheduledEnd"]


def test_a_conflict_can_be_accepted_deliberately(world):
    _schedule(world, _payload(world, start=TOMORROW))
    world["db"].flush()

    result = _schedule(world, _payload(world, start=TOMORROW + timedelta(minutes=30), allow_conflict=True))
    assert world["db"].get(SiteVisit, result["id"]) is not None


def test_a_back_to_back_visit_is_not_a_conflict(world):
    first = _schedule(world, _payload(world, start=TOMORROW, hours=2))
    world["db"].flush()

    second = _schedule(world, _payload(world, start=TOMORROW + timedelta(hours=2)))
    assert first["id"] != second["id"]


def test_a_participant_outside_the_project_is_rejected(world):
    outsider = User(full_name="Outsider", email=f"outsider-{uuid4().hex[:8]}@test.local",
                    hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE)
    world["db"].add(outsider)
    world["db"].flush()

    with pytest.raises(HTTPException) as raised:
        _schedule(world, _payload(world, start=TOMORROW, participants=[outsider]))
    assert raised.value.status_code == 400


def test_an_end_before_the_start_is_rejected_by_the_schema(world):
    with pytest.raises(ValueError):
        SiteVisitCreate(
            projectId=world["project"].id, title="Backwards visit",
            scheduledStart=TOMORROW, scheduledEnd=TOMORROW - timedelta(hours=1),
            visitType="ROUTINE_INSPECTION",
        )
