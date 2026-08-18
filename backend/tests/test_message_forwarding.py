"""Message forwarding / consultation foundation (Task 2).

Calls the router's own endpoint functions directly — exactly as a crafted
HTTP request would reach them — against real DB rows, same shape as
`test_authorization_migrated_endpoints.py` and `test_site_report_verification.py`.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.messages import create_conversation, forward_message
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.message import Conversation, Message
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.message import ConversationCreate, ForwardMessageCreate


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
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@test.local",
                      hashed_password="x", role=role, status=UserStatus.ACTIVE,
                      engineer_affiliation=affiliation)
        db.add(person)
        return person

    people = {
        "manager": user("FwdPm", UserRole.PROJECT_MANAGER),
        "engineer_a": user("FwdEngineerA", UserRole.ENGINEER, "main_contractor"),
        "engineer_b": user("FwdEngineerB", UserRole.ENGINEER, "main_contractor"),
        "engineer_c": user("FwdEngineerC", UserRole.ENGINEER, "main_contractor"),
        "outsider": user("FwdOutsider", UserRole.ENGINEER, "main_contractor"),
        "other_project_engineer": user("FwdOtherProjEngineer", UserRole.ENGINEER, "main_contractor"),
    }
    db.flush()

    project = Project(name=f"Forwarding Project {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=people["manager"].id, project_manager_id=people["manager"].id)
    other_project = Project(name=f"Unrelated Project {suffix}", status=ProjectStatus.ACTIVE,
                            owner_id=people["manager"].id, project_manager_id=people["manager"].id)
    db.add_all([project, other_project])
    db.flush()
    for person in (people["manager"], people["engineer_a"], people["engineer_b"], people["engineer_c"]):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=person.role, is_active=True))
    db.add(ProjectMember(project_id=other_project.id, user_id=people["other_project_engineer"].id,
                         role_on_project=UserRole.ENGINEER, is_active=True))
    db.flush()
    people["project"] = project
    people["other_project"] = other_project
    people["db"] = db
    yield people
    _purge(db, [project.id, other_project.id], [p.id for p in people.values() if isinstance(p, User)])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM message_recipient_states WHERE user_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "UPDATE messages SET responded_to_message_id = NULL, forwarded_from_message_id = NULL, "
        "forward_origin_message_id = NULL WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE project_id = ANY(:projects))",
        "DELETE FROM messages WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE project_id = ANY(:projects))",
        "DELETE FROM conversation_participants WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE project_id = ANY(:projects))",
        "DELETE FROM conversations WHERE project_id = ANY(:projects)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), params)
    db.commit()


def _send(db, project_id, sender, recipient_id, content):
    """Compose a first message the way the UI does, and return the created Message row."""
    result = create_conversation(
        ConversationCreate(project_id=project_id, recipient_ids=[recipient_id], content=content),
        db=db, current_user=sender,
    )
    db.commit()
    message_id = result["last_message"]["id"]
    return db.get(Message, message_id)


# --- normal forwarding ---------------------------------------------------------

def test_forwarding_reaches_the_new_recipient_with_full_context(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id,
                     "There is a conflict between the ceiling and electrical routing.")

    result = forward_message(
        original.id,
        ForwardMessageCreate(recipient_ids=[world["manager"].id], note="Can you review this and give me your opinion?"),
        db=db, current_user=world["engineer_b"],
    )
    db.commit()

    forwarded = result["messages"][-1]
    assert forwarded["content"] == "Can you review this and give me your opinion?"
    assert forwarded["forwarded_from_message_id"] == original.id
    assert forwarded["forward_origin"]["message_id"] == original.id
    assert forwarded["forward_origin"]["sender"].id == world["engineer_a"].id
    assert forwarded["forward_origin"]["content"] == original.content

    notified = db.query(Notification).filter(
        Notification.user_id == world["manager"].id,
        Notification.related_entity_id == result["id"],
    ).first()
    assert notified is not None
    assert "forwarded" in notified.title.lower()
    assert world["engineer_a"].full_name in notified.message


def test_forwarding_without_a_note_still_uses_a_non_blank_message(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Please check this.")
    result = forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["manager"].id]),
                             db=db, current_user=world["engineer_b"])
    db.commit()
    forwarded = result["messages"][-1]
    assert forwarded["content"].strip()
    assert forwarded["forwarded_from_message_id"] == original.id


def test_forwarding_is_recorded_in_the_audit_log(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Please check this.")
    result = forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["manager"].id], note="FYI"),
                             db=db, current_user=world["engineer_b"])
    db.commit()
    audit = db.query(AuditLog).filter(
        AuditLog.entity_type == "conversation", AuditLog.entity_id == result["id"],
    ).first()
    assert audit is not None
    assert audit.action == "message_forwarded"
    assert audit.actor_id == world["engineer_b"].id


# --- multiple forwarding / chain -----------------------------------------------

def test_forwarding_a_forward_preserves_the_chain_to_the_true_original_sender(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Root cause looks structural.")
    first_hop = forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["manager"].id]),
                                db=db, current_user=world["engineer_b"])
    db.commit()
    forwarded_once_id = first_hop["messages"][-1]["id"]

    second_hop = forward_message(forwarded_once_id, ForwardMessageCreate(recipient_ids=[world["engineer_c"].id]),
                                 db=db, current_user=world["manager"])
    db.commit()
    forwarded_twice = second_hop["messages"][-1]

    # Immediate parent is the message the manager actually forwarded...
    assert forwarded_twice["forwarded_from_message_id"] == forwarded_once_id
    # ...but the origin always resolves to engineer_a's very first message,
    # not the intermediate hop.
    assert forwarded_twice["forward_origin"]["message_id"] == original.id
    assert forwarded_twice["forward_origin"]["sender"].id == world["engineer_a"].id


# --- ownership / non-mutation ---------------------------------------------------

def test_forwarding_does_not_alter_the_original_message_or_its_conversation(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Original content.")
    original_conversation_id = original.conversation_id
    forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["manager"].id], note="note"),
                    db=db, current_user=world["engineer_b"])
    db.commit()
    db.refresh(original)
    assert original.sender_id == world["engineer_a"].id
    assert original.conversation_id == original_conversation_id
    assert original.content == "Original content."
    assert original.forwarded_from_message_id is None


# --- permissions / project isolation --------------------------------------------

def test_cannot_forward_to_a_user_outside_the_project(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Please review.")
    with pytest.raises(HTTPException) as error:
        forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["outsider"].id]),
                        db=db, current_user=world["engineer_b"])
    assert error.value.status_code == 403


def test_cannot_use_forwarding_to_leak_into_an_unrelated_project(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Please review.")
    with pytest.raises(HTTPException) as error:
        forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["other_project_engineer"].id]),
                        db=db, current_user=world["engineer_b"])
    assert error.value.status_code == 403
    # And no conversation was created that would give the unrelated user any
    # trace of this project's content.
    leaked = db.query(Conversation).filter(
        Conversation.project_id == world["project"].id,
        Conversation.participants.any(user_id=world["other_project_engineer"].id),
    ).first()
    assert leaked is None


def test_a_user_without_access_to_the_source_message_cannot_forward_it(db, world):
    original = _send(db, world["project"].id, world["engineer_a"], world["engineer_b"].id, "Private to us two.")
    with pytest.raises(HTTPException) as error:
        forward_message(original.id, ForwardMessageCreate(recipient_ids=[world["manager"].id]),
                        db=db, current_user=world["outsider"])
    assert error.value.status_code == 403


def test_forwarding_requires_at_least_one_recipient(world):
    with pytest.raises(ValidationError):
        ForwardMessageCreate(recipient_ids=[], group_code=None, note="no one to send to")


def test_forwarding_an_unknown_message_is_a_404(db, world):
    with pytest.raises(HTTPException) as error:
        forward_message(uuid4(), ForwardMessageCreate(recipient_ids=[world["manager"].id]),
                        db=db, current_user=world["engineer_a"])
    assert error.value.status_code == 404
