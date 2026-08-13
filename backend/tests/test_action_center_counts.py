"""The action centre must count real outstanding work and nothing else.

The original defect: "Needs My Response" counted every UNREAD or READ message
recipient state, with no check that anyone had actually asked for a response and
no project scoping. A manager with a quiet inbox still saw a non-zero number.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.collaboration import (
    ACKNOWLEDGEMENT_HANDLED_STATUSES,
    RESPONSE_HANDLED_STATUSES,
    actionable_message_states,
)
from app.db.database import SessionLocal
from app.models.collaboration import MessageRecipientState
from app.models.enums import ConversationType, ProjectStatus, UserRole, UserStatus
from app.models.message import Conversation, Message
from app.models.project import Project
from app.models.user import User


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
    """One project, one conversation, one recipient."""
    suffix = uuid4().hex[:10]
    sender = User(full_name="Sender", email=f"sender-{suffix}@test.local",
                  hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    recipient = User(full_name="Recipient", email=f"recipient-{suffix}@test.local",
                     hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    db.add_all([sender, recipient])
    db.flush()
    project = Project(name=f"Action Centre Project {suffix}", status=ProjectStatus.ACTIVE,
                      project_manager_id=sender.id)
    other_project = Project(name=f"Other Project {suffix}", status=ProjectStatus.ACTIVE,
                            project_manager_id=sender.id)
    db.add_all([project, other_project])
    db.flush()
    conversation = Conversation(project_id=project.id, title="Site coordination",
                                type=ConversationType.PROJECT_CHANNEL, created_by_id=sender.id)
    other_conversation = Conversation(project_id=other_project.id, title="Elsewhere",
                                      type=ConversationType.PROJECT_CHANNEL, created_by_id=sender.id)
    db.add_all([conversation, other_conversation])
    db.flush()
    yield {"db": db, "sender": sender, "recipient": recipient, "project": project,
           "other_project": other_project, "conversation": conversation,
           "other_conversation": other_conversation}
    db.rollback()


def add_message(world, *, requires_response=False, requires_acknowledgement=False,
                status="UNREAD", conversation=None):
    db = world["db"]
    message = Message(
        conversation_id=(conversation or world["conversation"]).id,
        sender_id=world["sender"].id, content="Please look at the Zone B detail.",
        requires_response=requires_response, requires_acknowledgement=requires_acknowledgement,
        priority="NORMAL",
    )
    db.add(message)
    db.flush()
    state = MessageRecipientState(message_id=message.id, user_id=world["recipient"].id,
                                  response_status=status, delivered_at=datetime.now(timezone.utc))
    db.add(state)
    db.flush()
    return message, state


def count(world, project_ids=None):
    return len(actionable_message_states(
        world["db"], user_id=world["recipient"].id,
        project_ids=[world["project"].id] if project_ids is None else project_ids,
    ))


def test_an_empty_inbox_counts_zero(world):
    assert count(world) == 0


def test_an_unread_ordinary_message_is_not_an_action(world):
    """The exact original bug: unread is not the same as owed a response."""
    add_message(world, status="UNREAD")
    assert count(world) == 0


def test_a_read_ordinary_message_is_not_an_action(world):
    add_message(world, status="READ")
    assert count(world) == 0


def test_many_ordinary_messages_still_count_zero(world):
    for status in ("UNREAD", "READ", "ACKNOWLEDGED", "RESPONDED"):
        add_message(world, status=status)
    assert count(world) == 0


def test_a_message_that_asks_for_a_response_counts(world):
    add_message(world, requires_response=True, status="UNREAD")
    assert count(world) == 1


def test_reading_a_response_request_does_not_clear_it(world):
    add_message(world, requires_response=True, status="READ")
    assert count(world) == 1, "opening a message is not answering it"


def test_acknowledging_a_response_request_does_not_clear_it(world):
    add_message(world, requires_response=True, status="ACKNOWLEDGED")
    assert count(world) == 1, "acknowledgement is not a response"


@pytest.mark.parametrize("status", RESPONSE_HANDLED_STATUSES)
def test_answering_clears_a_response_request(world, status):
    add_message(world, requires_response=True, status=status)
    assert count(world) == 0


def test_an_acknowledgement_request_counts_until_acknowledged(world):
    add_message(world, requires_acknowledgement=True, status="READ")
    assert count(world) == 1


@pytest.mark.parametrize("status", ACKNOWLEDGEMENT_HANDLED_STATUSES)
def test_acknowledging_clears_an_acknowledgement_request(world, status):
    add_message(world, requires_acknowledgement=True, status=status)
    assert count(world) == 0


def test_a_message_needing_both_stays_open_until_answered(world):
    add_message(world, requires_response=True, requires_acknowledgement=True, status="ACKNOWLEDGED")
    assert count(world) == 1


def test_only_the_addressed_recipient_is_counted(world):
    add_message(world, requires_response=True)
    others = actionable_message_states(world["db"], user_id=world["sender"].id,
                                       project_ids=[world["project"].id])
    assert others == [], "the sender does not owe themselves a response"


def test_another_projects_message_is_excluded_when_a_project_is_selected(world):
    add_message(world, requires_response=True, conversation=world["other_conversation"])
    assert count(world) == 0, "selecting a project must scope the count to it"


def test_both_projects_count_when_the_whole_portfolio_is_in_scope(world):
    add_message(world, requires_response=True)
    add_message(world, requires_response=True, conversation=world["other_conversation"])
    assert count(world, project_ids=[world["project"].id, world["other_project"].id]) == 2


def test_the_returned_list_matches_the_count_exactly(world):
    """The dashboard list must never disagree with the number above it."""
    add_message(world, requires_response=True)
    add_message(world, status="UNREAD")
    states = actionable_message_states(world["db"], user_id=world["recipient"].id,
                                       project_ids=[world["project"].id])
    assert len(states) == 1
    assert all(isinstance(item, MessageRecipientState) for item in states)
