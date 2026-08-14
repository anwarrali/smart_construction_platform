"""The four AI-insight review actions, and the duplicate-card regression.

The reported defect: one finding ("N electrical installation task(s) exist, but
the IFC contains no electrical elements") behaved unlike the others. Resolving it
left an identical card in the queue and put another copy in the resolved view, so
it looked as though clicking Resolve created a new record.

It did not. Both insight engines fingerprint a finding per IFC revision, so every
uploaded revision re-detected the same condition and stored it again against the
new revision id. The queue listed the rows from every revision at once — several
cards with the same title, only one of which changed when it was reviewed.

These tests pin the query scope, the four transitions, and the idempotence of a
repeated Resolve.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.ai_intelligence import intelligence_overview, list_insights, review_insight
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.ifc import AIInsight, IFCModelGroup, IFCModelVersion
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.ai_insight import AIInsightReview


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
    """A project with a superseded and a current IFC revision, each carrying the
    same deterministic finding, exactly as an upload of a second revision leaves it."""
    suffix = uuid4().hex[:10]

    def user(name, role):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE)

    admin = user("InsightAdmin", UserRole.ADMIN)
    manager = user("InsightPm", UserRole.PROJECT_MANAGER)
    owner = user("InsightOwner", UserRole.OWNER)
    db.add_all([admin, manager, owner])
    db.flush()

    project = Project(name=f"Insight Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=manager.id,
                         role_on_project=UserRole.PROJECT_MANAGER, is_active=True))

    group = IFCModelGroup(project_id=project.id, name=f"Group {suffix}", created_by_id=manager.id)
    db.add(group)
    db.flush()

    def revision(number, active):
        return IFCModelVersion(project_id=project.id, model_group_id=group.id,
                               version_number=number, revision_code=f"R{number:02d}",
                               title=f"Revision {number}", processing_status="READY",
                               is_active=active, uploaded_by_id=manager.id,
                               original_filename=f"r{number}.ifc",
                               storage_key=f"{suffix}/r{number}.ifc",
                               file_hash=uuid4().hex, file_size=1024)

    old, current = revision(1, False), revision(2, True)
    db.add_all([old, current])
    db.flush()

    def finding(version):
        return AIInsight(
            project_id=project.id, model_revision_id=version.id, fingerprint=uuid4().hex,
            insight_type="DISCIPLINE_ELECTRICAL_NOT_IN_IFC", category="DISCIPLINE_MISMATCH",
            severity="CRITICAL", confidence=.97,
            title="4 electrical installation task(s) exist, but the IFC contains no electrical elements",
            description="Same condition, re-detected against a new revision.",
            reason="test", recommended_action="test",
            source_engine="IFC_COMPATIBILITY_RULES_V1", status="OPEN",
        )

    stale, live = finding(old), finding(current)
    db.add_all([stale, live])
    db.flush()
    try:
        yield {"admin": admin, "manager": manager, "project": project,
               "old": old, "current": current, "stale": stale, "live": live}
    finally:
        _purge(db, [project.id], [admin.id, manager.id, owner.id])


def _purge(db, project_ids, user_ids):
    """Remove what the fixture created.

    Several of these endpoints commit (`add_project_member`, `update_project`),
    so rolling the session back is not enough: without this the fixture would
    leave its people and projects behind on every run.
    """
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM consultant_engineer_scopes WHERE project_id = ANY(:projects) OR consultant_user_id = ANY(:users)",
        "DELETE FROM user_permission_overrides WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM role_permission_overrides WHERE updated_by_id = ANY(:users)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM ifc_model_versions WHERE project_id = ANY(:projects) OR uploaded_by_id = ANY(:users)",
        "DELETE FROM ifc_model_groups WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM project_consultant_reviewers WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM engineer_profiles WHERE user_id = ANY(:users)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


def _list(db, world, actor="manager", **kwargs):
    # Called directly rather than through FastAPI, so the paging defaults (which
    # are Query objects) have to be supplied explicitly.
    kwargs.setdefault("page", 1)
    kwargs.setdefault("page_size", 100)
    return list_insights(world["project"].id, db=db, current_user=world[actor], **kwargs)


# --- The regression -------------------------------------------------------

def test_review_queue_shows_only_the_current_revision(db, world):
    """Two rows exist; the reviewer sees the one that is still actionable."""
    ids = {item.id for item in _list(db, world)}
    assert world["live"].id in ids
    assert world["stale"].id not in ids


def test_resolving_the_visible_finding_empties_the_open_queue(db, world):
    """The reported symptom: after Resolve an identical card was still listed."""
    review_insight(world["project"].id, world["live"].id, AIInsightReview(status="RESOLVED"),
                   db=db, current_user=world["manager"])
    assert not [item for item in _list(db, world, status="OPEN")]
    resolved = _list(db, world, status="RESOLVED")
    assert [item.id for item in resolved] == [world["live"].id]


def test_superseded_findings_are_preserved_and_still_reachable(db, world):
    """Scoping the queue hides the old row; it must not delete or alter it."""
    assert db.get(AIInsight, world["stale"].id).status == "OPEN"
    ids = {item.id for item in _list(db, world, include_superseded=True)}
    assert {world["stale"].id, world["live"].id} <= ids
    by_revision = _list(db, world, model_revision_id=world["old"].id)
    assert [item.id for item in by_revision] == [world["stale"].id]


def test_overview_counts_match_the_listed_queue(db, world):
    overview = intelligence_overview(world["project"].id, db=db, current_user=world["manager"])
    assert overview["openInsights"] == len(_list(db, world))


# --- The four actions -----------------------------------------------------

def _review(db, world, status, note=None):
    return review_insight(world["project"].id, world["live"].id,
                          AIInsightReview(status=status, note=note),
                          db=db, current_user=world["manager"])


def test_acknowledge_keeps_the_insight_active_and_creates_no_issue(db, world):
    item = _review(db, world, "ACKNOWLEDGED")
    assert item.status == "ACKNOWLEDGED"
    assert item.applied_entity_id is None
    assert world["live"].id in {row.id for row in _list(db, world)}


def test_dismiss_moves_the_insight_out_of_the_active_workflow(db, world):
    item = _review(db, world, "DISMISSED")  # the UI's word for FALSE_POSITIVE
    assert item.status == "FALSE_POSITIVE"
    assert not [row for row in _list(db, world, status="OPEN")]


def test_resolve_closes_the_insight_and_stamps_resolved_at(db, world):
    item = _review(db, world, "RESOLVED")
    assert item.status == "RESOLVED"
    assert item.resolved_at is not None


def test_repeated_resolve_is_idempotent_and_records_one_event(db, world):
    def audit_count():
        return db.query(AuditLog).filter(
            AuditLog.action == "ai_insight_reviewed",
            AuditLog.entity_id == world["live"].id,
        ).count()

    first = _review(db, world, "RESOLVED")
    resolved_at = first.resolved_at
    after_first = audit_count()

    for _ in range(3):
        repeat = _review(db, world, "RESOLVED")
        assert repeat.status == "RESOLVED"

    assert audit_count() == after_first, "a repeated Resolve wrote another event"
    assert db.get(AIInsight, world["live"].id).resolved_at == resolved_at
    assert db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id,
        AIInsight.model_revision_id == world["current"].id,
    ).count() == 1, "a repeated Resolve created another insight row"


def test_unsupported_review_status_is_rejected(db, world):
    with pytest.raises(HTTPException) as error:
        _review(db, world, "ARCHIVED")
    assert error.value.status_code == 400
