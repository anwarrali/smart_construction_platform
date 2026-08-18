"""Regression coverage for `DELETE /users/{id}` (`permanently_delete_user`,
app.api.users).

Root cause, not the symptom: the endpoint's `blockers` dict is meant to be a
complete, hand-maintained mirror of every `ondelete="RESTRICT"` foreign key
onto `users.id` — the set of tables the database itself will never let this
DELETE silently orphan or cascade away, because it is project history that
must survive the person who made it. Two things were wrong with it:

1. `Message.receiver_id` does not exist. This app's messaging is
   conversation-based (`Conversation` / `ConversationParticipant` / `Message`)
   — a `Message` only has `sender_id`. The direct-message-shaped check was
   stale, and referencing a nonexistent attribute raised `AttributeError`
   before the query ever ran, turning every delete attempt into an
   unhandled 500 regardless of whether the target user had any real history.

2. The dict was also missing eleven other tables that carry the same
   `ondelete="RESTRICT"` constraint (confirmed against the live schema via
   `information_schema`, not guessed): `conversations.created_by_id`,
   `field_submissions.worker_id`, `ifc_comparisons.created_by_id`,
   `ifc_model_groups.created_by_id`, `ifc_model_versions.uploaded_by_id`,
   `owner_requests.created_by_id`, `site_visits.created_by_id`,
   `site_visits.engineer_id`, `voice_analyses.user_id`,
   `voice_execution_logs.actor_user_id`, `ai_action_versions.actor_user_id`.
   Deleting a user linked only through one of those would have skipped the
   409 entirely and hit the same class of crash one level down, as a raw
   `IntegrityError` from Postgres instead of a clean response.

`test_every_restrict_foreign_key_to_users_has_a_blocker_check` is the
durable fix: it re-derives the RESTRICT set from `information_schema` on
every run and fails if the endpoint's blockers dict (introspected from its
own source, not re-typed here) has fallen out of sync — so a new RESTRICT
column added later fails a test instead of silently reintroducing this bug.
"""

import inspect
import re
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.api.users as users_module
from app.api.users import permanently_delete_user
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import (
    ConversationType,
    EngineerDiscipline,
    ProjectStatus,
    UserRole,
    UserStatus,
)
from app.models.message import Conversation, Message
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.step_up import StepUpGrant
from app.models.user import EngineerProfile, User
from app.models.collaboration import SiteVisit
from datetime import datetime, timedelta, timezone


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


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM messages WHERE sender_id = ANY(:users)",
        "DELETE FROM conversation_participants WHERE user_id = ANY(:users)",
        "DELETE FROM conversations WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM site_visit_participants WHERE user_id = ANY(:users)",
        "DELETE FROM site_visits WHERE project_id = ANY(:projects)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM engineer_profiles WHERE user_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


@pytest.fixture()
def world(db):
    suffix = uuid4().hex[:10]

    def user(name, role=UserRole.ENGINEER, affiliation="main_contractor"):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      engineer_affiliation=affiliation if role == UserRole.ENGINEER else None)
        db.add(person)
        return person

    people = {
        "admin": user("DeleteAdmin", UserRole.ADMIN, None),
        "other_admin": user("DeleteOtherAdmin", UserRole.ADMIN, None),
        # One dependent record per category the endpoint has to get right.
        "clean": user("DeleteClean"),
        "messenger": user("DeleteMessenger"),
        "convo_creator": user("DeleteConvoCreator"),
        "visit_engineer": user("DeleteVisitEngineer"),
        "notified": user("DeleteNotified"),
        "member": user("DeleteMember"),
        "has_profile": user("DeleteHasProfile"),
        "assignee": user("DeleteAssignee"),
        "audited": user("DeleteAudited"),
        "reviewer": user("DeleteReviewer"),
    }
    db.flush()

    project = Project(name=f"Delete User Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["admin"].id)
    db.add(project)
    db.flush()

    # messages -> RESTRICT (blocker)
    convo = Conversation(project_id=project.id, type=ConversationType.PROJECT_CHANNEL,
                         created_by_id=people["admin"].id, title="General")
    db.add(convo)
    db.flush()
    db.add(Message(conversation_id=convo.id, sender_id=people["messenger"].id, content="hello"))

    # conversations.created_by_id -> RESTRICT (blocker) — the fix's new coverage
    db.add(Conversation(project_id=project.id, type=ConversationType.PROJECT_CHANNEL,
                        created_by_id=people["convo_creator"].id, title="Created by target"))

    # site_visits.engineer_id -> RESTRICT (blocker) — the fix's new coverage
    now = datetime.now(timezone.utc)
    db.add(SiteVisit(project_id=project.id, engineer_id=people["visit_engineer"].id,
                     created_by_id=people["admin"].id, title="Foundation check",
                     scheduled_start=now, scheduled_end=now + timedelta(hours=1),
                     visit_type="inspection"))

    # notifications.user_id -> CASCADE (not a blocker)
    db.add(Notification(user_id=people["notified"].id, title="Hi", message="body"))

    # project_members.user_id -> CASCADE (not a blocker)
    db.add(ProjectMember(project_id=project.id, user_id=people["member"].id,
                         role_on_project=UserRole.ENGINEER, is_active=True))

    # engineer_profiles.user_id -> CASCADE (not a blocker)
    db.add(EngineerProfile(user_id=people["has_profile"].id, discipline=EngineerDiscipline.CIVIL))

    # task_assignees.user_id -> CASCADE (not a blocker); tasks.reviewed_by_id -> SET NULL (not a blocker)
    task = Task(project_id=project.id, task_code=f"T-{suffix}", name="Task",
               discipline="civil", created_by_id=people["admin"].id,
               reviewed_by_id=people["reviewer"].id)
    task.assignees = [people["assignee"]]
    db.add(task)

    # audit_logs.actor_id -> SET NULL (not a blocker); the row itself is history, kept
    db.add(AuditLog(actor_id=people["audited"].id, action="created", entity_type="project",
                    entity_id=project.id, project_id=project.id))
    db.flush()

    people["project"] = project
    people["task"] = task
    user_ids = [person.id for person in people.values() if isinstance(person, User)]
    try:
        yield people
    finally:
        _purge(db, [project.id], user_ids)


def _delete(db, target, actor):
    """Delete as the endpoint does, including the step-up it now requires.

    Permanent deletion is gated on step-up verification (Task 4). These tests
    are about the *deletion* rules, so they satisfy that gate directly with a
    grant rather than driving the whole OTP exchange — the OTP mechanics
    themselves are covered by test_step_up_security.py, which includes a test
    that this endpoint refuses without one.
    """
    db.add(StepUpGrant(
        user_id=actor.id, purpose="admin.delete_user",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    ))
    db.flush()
    return permanently_delete_user(target.id, db=db, current_user=actor)


# --- the bug this file exists to pin ------------------------------------------

def test_every_restrict_foreign_key_to_users_has_a_blocker_check(db):
    """Re-derives the ground truth from the live schema on every run, rather
    than hand-copying a snapshot of it, so a RESTRICT column added later
    fails this test instead of a real delete request.

    Table-qualified, not just column-name-qualified: several RESTRICT
    columns share a name with an unrelated SET NULL column on a different
    table (e.g. `created_by_id` is RESTRICT on `conversations` but SET NULL
    on `milestones`), so matching on column name alone would pass even if a
    specific table's check were the one silently dropped. Each
    `ClassName.column_id ==` comparison found in the endpoint's own source is
    resolved back to its real table via the model class actually imported
    into `app.api.users` (`ClassName.__tablename__`), then compared against
    the schema as a (table, column) pair.
    """
    rows = db.execute(text("""
        select tc.table_name, kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
        join information_schema.constraint_column_usage ccu
          on tc.constraint_name = ccu.constraint_name and tc.table_schema = ccu.table_schema
        join information_schema.referential_constraints rc
          on tc.constraint_name = rc.constraint_name and tc.table_schema = rc.constraint_schema
        where tc.constraint_type = 'FOREIGN KEY' and ccu.table_name = 'users' and rc.delete_rule = 'RESTRICT'
    """)).all()
    restrict_fks = {(row[0], row[1]) for row in rows}
    assert restrict_fks, "expected at least the known RESTRICT foreign keys onto users.id"

    source = inspect.getsource(permanently_delete_user)
    checked_table_columns = set()
    unresolved_classes = set()
    for class_name, column in re.findall(r"(\w+)\.(\w+_id)\s*==", source):
        model = getattr(users_module, class_name, None)
        table = getattr(model, "__tablename__", None)
        if table:
            checked_table_columns.add((table, column))
        else:
            unresolved_classes.add(class_name)

    # `User.id` itself doesn't match (`id` isn't a `*_id` column), but the
    # Core-style `task_assignees.c.user_id` access captures "c" as the
    # "class name" (the `.c` column collection accessor, not a mapped class)
    # — expected, not a gap.
    unresolved_classes -= {"c"}
    assert not unresolved_classes, (
        f"could not resolve these classes referenced in permanently_delete_user "
        f"to an imported model's table (add the import or extend this test's "
        f"allowlist if this is intentional): {unresolved_classes}"
    )

    missing = sorted(f"{table}.{column}" for table, column in restrict_fks
                     if (table, column) not in checked_table_columns)
    assert missing == [], f"blockers dict is missing RESTRICT-linked columns: {missing}"


def test_message_sender_is_not_a_real_attribute_error(db, world):
    """The literal bug: this used to raise AttributeError before the 409 was
    ever reached, for every delete request regardless of target."""
    with pytest.raises(HTTPException) as error:
        _delete(db, world["messenger"], world["admin"])
    assert error.value.status_code == 409
    assert "messages" in error.value.detail


def test_a_conversation_creator_is_blocked(db, world):
    """Previously-missing check: conversations.created_by_id is RESTRICT."""
    with pytest.raises(HTTPException) as error:
        _delete(db, world["convo_creator"], world["admin"])
    assert error.value.status_code == 409
    assert "conversations created" in error.value.detail


def test_a_site_visit_engineer_is_blocked(db, world):
    """Previously-missing check: site_visits.engineer_id is RESTRICT."""
    with pytest.raises(HTTPException) as error:
        _delete(db, world["visit_engineer"], world["admin"])
    assert error.value.status_code == 409
    assert "site visits" in error.value.detail


# --- CASCADE / SET NULL links must NOT block deletion --------------------------

def test_a_user_with_only_notifications_can_be_deleted(db, world):
    target_id = world["notified"].id
    result = _delete(db, world["notified"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None
    assert db.query(Notification).filter(Notification.user_id == target_id).first() is None


def test_a_user_with_only_project_membership_can_be_deleted(db, world):
    target_id = world["member"].id
    result = _delete(db, world["member"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None
    assert db.query(ProjectMember).filter(ProjectMember.user_id == target_id).first() is None


def test_a_user_with_an_engineer_profile_can_be_deleted(db, world):
    target_id = world["has_profile"].id
    result = _delete(db, world["has_profile"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None
    assert db.query(EngineerProfile).filter(EngineerProfile.user_id == target_id).first() is None


def test_a_user_with_only_a_task_assignment_can_be_deleted(db, world):
    target_id = world["assignee"].id
    task_id = world["task"].id
    result = _delete(db, world["assignee"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None
    # The task itself is untouched — only the assignment link is gone.
    db.expire_all()
    assert db.get(Task, task_id) is not None


def test_a_user_named_as_an_old_audit_actor_can_be_deleted_and_history_survives(db, world):
    """`audit_logs.actor_id` is SET NULL: preserve the row, blank the actor —
    this is the schema's own explicit choice, not something this endpoint
    should second-guess by refusing to delete or by deleting the log."""
    target_id = world["audited"].id
    old_audit_id = db.query(AuditLog.id).filter(AuditLog.actor_id == target_id).scalar()
    assert old_audit_id is not None

    result = _delete(db, world["audited"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None

    db.expire_all()
    preserved = db.get(AuditLog, old_audit_id)
    assert preserved is not None, "the historical audit row must survive the actor's deletion"
    assert preserved.actor_id is None

    deletion_audit = db.query(AuditLog).filter(
        AuditLog.entity_id == target_id, AuditLog.action == "permanently_deleted",
    ).first()
    assert deletion_audit is not None, "the deletion itself must be recorded"


def test_a_user_named_as_a_task_reviewer_can_be_deleted(db, world):
    """`tasks.reviewed_by_id` is SET NULL — an optional attribution column,
    not a blocker."""
    target_id = world["reviewer"].id
    task_id = world["task"].id
    result = _delete(db, world["reviewer"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None

    db.expire_all()
    task = db.get(Task, task_id)
    assert task is not None
    assert task.reviewed_by_id is None


# --- edges ---------------------------------------------------------------------

def test_a_clean_user_can_be_deleted(db, world):
    target_id = world["clean"].id
    result = _delete(db, world["clean"], world["admin"])
    assert result == {"message": "User permanently deleted"}
    assert db.get(User, target_id) is None


def test_deleting_the_same_user_twice_is_a_404_not_a_second_500(db, world):
    _delete(db, world["clean"], world["admin"])
    with pytest.raises(HTTPException) as error:
        _delete(db, world["clean"], world["admin"])
    assert error.value.status_code == 404


def test_an_administrator_cannot_delete_their_own_account(db, world):
    with pytest.raises(HTTPException) as error:
        _delete(db, world["admin"], world["admin"])
    assert error.value.status_code == 400


def test_deleting_a_blocked_user_does_not_touch_unrelated_real_data(db, world):
    """The 409 path must be side-effect free: no partial delete, no
    unrelated row touched, nothing written before the blocker check raises."""
    project_id = world["project"].id
    target_id = world["messenger"].id
    with pytest.raises(HTTPException) as error:
        _delete(db, world["messenger"], world["admin"])
    assert error.value.status_code == 409
    # No rollback: the 409 path never reaches `record_audit`/`db.commit()`,
    # so there is nothing to undo — asserting straight against the session
    # confirms the endpoint itself made no writes, without conflating that
    # with whether the test fixture's own setup is still pending.
    assert db.get(Project, project_id) is not None
    assert db.get(User, target_id) is not None
