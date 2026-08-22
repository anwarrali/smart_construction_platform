"""Realtime: tickets, authorization filtering, cross-worker delivery, cleanup.

The properties that matter here are security properties. A realtime layer is an
attractive place for an authorization bypass to hide, because the events it
leaks are invisible in the REST logs everyone audits. Most of this file is
therefore about what must *not* arrive.

The cross-process test is the one that justifies the whole `LISTEN`/`NOTIFY`
design: it publishes from a genuinely separate PostgreSQL connection — the
situation `--workers 2` creates on every request — and asserts the listener
still sees it. An in-memory event bus passes every other test in this file and
fails that one.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import SSE_TICKET_TYPE, create_access_token, create_sse_ticket, decode_token
from app.db.database import SessionLocal
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.realtime import (
    CHANNEL, EventType, RealtimeEvent, Subscriber, get_broker, get_listener, publish_event,
)
from app.services.realtime.broker import AuthorizationScope, RealtimeBroker
from app.services.realtime.publisher import MAX_PAYLOAD_BYTES, publish


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


@pytest.fixture(autouse=True)
def realtime_on(monkeypatch):
    """Realtime enabled regardless of the ambient environment."""
    monkeypatch.setattr(settings, "REALTIME_ENABLED", True)


@pytest.fixture()
def world(db):
    """Two projects; a member of one, and an outsider who is a member of neither."""
    suffix = uuid.uuid4().hex[:8]

    def user(name, role=UserRole.PROJECT_MANAGER):
        person = User(
            full_name=f"{name}{suffix}", email=f"{name.lower()}.{suffix}@constro.io",
            hashed_password="x", role=role, status=UserStatus.ACTIVE,
        )
        db.add(person)
        db.flush()
        return person

    owner = user("RtOwner")
    member = user("RtMember", UserRole.ENGINEER)
    outsider = user("RtOutsider", UserRole.ENGINEER)

    def project(name, manager):
        item = Project(
            name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
            owner_id=owner.id, project_manager_id=manager.id,
        )
        db.add(item)
        db.flush()
        return item

    project_a = project("RtAlpha", owner)
    project_b = project("RtBeta", owner)
    db.add(ProjectMember(
        project_id=project_a.id, user_id=member.id,
        role_on_project=UserRole.ENGINEER, is_active=True,
    ))
    db.commit()

    created = {
        "owner": owner, "member": member, "outsider": outsider,
        "project_a": project_a, "project_b": project_b,
    }
    try:
        yield created
    finally:
        db.rollback()
        db.query(ProjectMember).filter(ProjectMember.project_id.in_([project_a.id, project_b.id])).delete(synchronize_session=False)
        db.query(Project).filter(Project.id.in_([project_a.id, project_b.id])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([owner.id, member.id, outsider.id])).delete(synchronize_session=False)
        db.commit()


# --- tickets ----------------------------------------------------------------


def test_a_valid_ticket_decodes_to_its_user():
    user_id = uuid.uuid4()
    payload = decode_token(create_sse_ticket(str(user_id), timedelta(seconds=60)))
    assert payload["sub"] == str(user_id)
    assert payload["type"] == SSE_TICKET_TYPE


def test_an_expired_ticket_is_rejected():
    """Expiry is what bounds the exposure of a credential that rides in a URL."""
    expired = create_sse_ticket(str(uuid.uuid4()), timedelta(seconds=-1))
    assert decode_token(expired) is None


def test_a_tampered_ticket_is_rejected():
    ticket = create_sse_ticket(str(uuid.uuid4()), timedelta(seconds=60))
    assert decode_token(ticket + "x") is None


def test_an_access_token_is_not_usable_as_a_ticket():
    """Half of the separation: the stream refuses anything not a ticket."""
    access = create_access_token({"sub": str(uuid.uuid4())})
    assert decode_token(access)["type"] == "access" != SSE_TICKET_TYPE


def test_a_ticket_is_not_usable_as_an_access_token():
    """The other half: `get_current_user` refuses any non-"access" type."""
    ticket = create_sse_ticket(str(uuid.uuid4()), timedelta(seconds=60))
    assert decode_token(ticket)["type"] != "access"


# --- authorization scope ----------------------------------------------------


def _scope_for(user) -> AuthorizationScope:
    scope = AuthorizationScope(user.id)
    scope.refresh()
    return scope


def test_a_user_receives_their_own_targeted_events(world):
    scope = _scope_for(world["member"])
    event = RealtimeEvent(type=EventType.NOTIFICATION_CREATED, user_id=world["member"].id)
    assert scope.allows(event) is True


def test_a_user_never_receives_another_users_targeted_events(world):
    """The single most important assertion in this file."""
    scope = _scope_for(world["member"])
    event = RealtimeEvent(type=EventType.NOTIFICATION_CREATED, user_id=world["outsider"].id)
    assert scope.allows(event) is False


def test_a_member_receives_events_for_their_project(world):
    scope = _scope_for(world["member"])
    event = RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id)
    assert scope.allows(event) is True


def test_an_event_for_an_inaccessible_project_is_never_delivered(world):
    """Project B has no membership for this user; its events must not arrive."""
    scope = _scope_for(world["member"])
    event = RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_b"].id)
    assert scope.allows(event) is False


def test_an_outsider_receives_nothing_for_any_project(world):
    scope = _scope_for(world["outsider"])
    for project in ("project_a", "project_b"):
        event = RealtimeEvent(type=EventType.ISSUE_CREATED, project_id=world[project].id)
        assert scope.allows(event) is False


def test_a_deactivated_user_stops_receiving_events(db, world):
    """Access is re-resolved, not pinned at connect — so a revoke takes effect."""
    scope = _scope_for(world["member"])
    assert scope.allows(RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id))

    world["member"].status = UserStatus.SUSPENDED
    db.commit()
    scope.refresh()

    assert scope.is_active is False
    assert scope.allows(RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id)) is False
    assert scope.allows(RealtimeEvent(type=EventType.NOTIFICATION_CREATED, user_id=world["member"].id)) is False


def test_losing_project_membership_stops_its_events_at_the_next_refresh(db, world):
    scope = _scope_for(world["member"])
    event = RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id)
    assert scope.allows(event) is True

    db.query(ProjectMember).filter(
        ProjectMember.project_id == world["project_a"].id,
        ProjectMember.user_id == world["member"].id,
    ).delete(synchronize_session=False)
    db.commit()
    scope.refresh()

    assert scope.allows(event) is False


def test_an_unaddressed_event_reaches_nobody(world):
    """`publish` refuses these; the scope is the second door on the same room."""
    scope = _scope_for(world["owner"])
    assert scope.allows(RealtimeEvent(type=EventType.TASK_UPDATED)) is False


def test_authorization_refresh_is_time_bounded(world, monkeypatch):
    monkeypatch.setattr(settings, "REALTIME_AUTH_TTL_SECONDS", 3600)
    scope = _scope_for(world["member"])
    stamp = scope.refreshed_at
    scope.refresh_if_stale()
    assert scope.refreshed_at == stamp, "refreshed inside its own TTL"

    monkeypatch.setattr(settings, "REALTIME_AUTH_TTL_SECONDS", 0)
    scope.refresh_if_stale()
    assert scope.refreshed_at > stamp, "did not refresh once stale"


# --- subscriber narrowing ---------------------------------------------------


def test_a_client_filter_can_narrow_but_not_widen(world):
    """A subscription request must never be able to add permissions."""
    subscriber = Subscriber(world["member"].id, event_types={EventType.TASK_UPDATED})
    subscriber.scope.refresh()

    allowed_but_filtered = RealtimeEvent(type=EventType.ISSUE_CREATED, project_id=world["project_a"].id)
    assert subscriber.accepts(allowed_but_filtered) is False, "client narrowing ignored"

    # And asking for a type it is not authorized for still yields nothing.
    forbidden = RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_b"].id)
    assert subscriber.accepts(forbidden) is False, "client filter widened access"

    permitted = RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id)
    assert subscriber.accepts(permitted) is True


def test_an_unauthorized_event_is_never_queued(world):
    subscriber = Subscriber(world["member"].id)
    subscriber.scope.refresh()
    subscriber.offer(RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_b"].id))
    assert subscriber.queue.qsize() == 0


def test_a_slow_client_drops_events_rather_than_blocking(world, monkeypatch):
    """Bounded queues are safe *because* events are hints, not state."""
    monkeypatch.setattr(settings, "REALTIME_MAX_QUEUE", 5)
    subscriber = Subscriber(world["member"].id)
    subscriber.scope.refresh()

    for _ in range(20):
        subscriber.offer(RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id))

    assert subscriber.queue.qsize() == 5
    assert subscriber.dropped == 15


# --- broker -----------------------------------------------------------------


def test_the_broker_delivers_only_to_authorized_subscribers(world):
    broker = RealtimeBroker()
    insider = Subscriber(world["member"].id)
    insider.scope.refresh()
    outsider = Subscriber(world["outsider"].id)
    outsider.scope.refresh()
    broker.add(insider)
    broker.add(outsider)

    broker.dispatch(RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id))

    assert insider.queue.qsize() == 1
    assert outsider.queue.qsize() == 0, "an outsider received a project event"


def test_removing_a_subscriber_cleans_it_up(world):
    """A leaked subscriber would keep filling a dead connection's queue."""
    broker = RealtimeBroker()
    subscriber = Subscriber(world["member"].id)
    subscriber.scope.refresh()
    broker.add(subscriber)
    assert broker.connection_count == 1

    broker.remove(subscriber)
    assert broker.connection_count == 0

    broker.dispatch(RealtimeEvent(type=EventType.TASK_UPDATED, project_id=world["project_a"].id))
    assert subscriber.queue.qsize() == 0


# --- publishing -------------------------------------------------------------


def test_publish_refuses_an_unaddressed_event(db):
    assert publish(db, RealtimeEvent(type=EventType.TASK_UPDATED)) is False


def test_publish_refuses_an_oversized_payload(db):
    huge = RealtimeEvent(type=EventType.TASK_UPDATED, entity_type="X" * (MAX_PAYLOAD_BYTES + 100),
                         project_id=uuid.uuid4())
    assert publish(db, huge) is False


def test_publish_is_a_no_op_when_realtime_is_disabled(db, monkeypatch):
    """Disabling realtime must not break the business write it rides on."""
    monkeypatch.setattr(settings, "REALTIME_ENABLED", False)
    assert publish_event(db, event_type=EventType.TASK_UPDATED, project_id=uuid.uuid4()) is False


def test_a_publish_failure_never_raises(db, monkeypatch):
    """Realtime is an enhancement; it must not roll back a business write."""
    def explode(*args, **kwargs):
        raise RuntimeError("connection gone")

    monkeypatch.setattr(db, "execute", explode)
    assert publish_event(db, event_type=EventType.TASK_UPDATED, project_id=uuid.uuid4()) is False


# --- envelope ---------------------------------------------------------------


def test_the_envelope_round_trips():
    original = RealtimeEvent(
        type=EventType.MESSAGE_CREATED, project_id=uuid.uuid4(), user_id=uuid.uuid4(),
        entity_type="CONVERSATION", entity_id=uuid.uuid4(),
    )
    restored = RealtimeEvent.from_payload(json.loads(json.dumps(original.to_payload())))
    assert restored.type == original.type
    assert restored.project_id == original.project_id
    assert restored.user_id == original.user_id
    assert restored.entity_id == original.entity_id
    assert restored.id == original.id


def test_the_envelope_carries_no_business_content():
    """The core privacy property: identifiers and a type, nothing else."""
    event = RealtimeEvent(
        type=EventType.MESSAGE_CREATED, user_id=uuid.uuid4(),
        entity_type="CONVERSATION", entity_id=uuid.uuid4(),
    )
    assert set(event.to_payload()) <= {"id", "type", "ts", "projectId", "userId", "entityType", "entityId"}


# --- cross-worker delivery --------------------------------------------------


def test_an_event_published_on_another_connection_reaches_the_listener(db):
    """The test that justifies LISTEN/NOTIFY over an in-memory bus.

    The publish happens on a *separate* PostgreSQL connection — exactly what a
    second uvicorn worker is. An in-process event bus passes every other test
    in this file and fails this one.
    """
    listener = get_listener()
    loop = asyncio.new_event_loop()
    received: list[RealtimeEvent] = []
    seen = threading.Event()

    def handler(event: RealtimeEvent) -> None:
        received.append(event)
        seen.set()

    listener.add_handler(handler)
    listener.start(loop)
    try:
        # Give the listener thread time to connect and issue LISTEN.
        deadline = time.monotonic() + 10
        while not listener.is_connected and time.monotonic() < deadline:
            time.sleep(0.05)
        if not listener.is_connected:
            pytest.skip("realtime listener could not connect to PostgreSQL")

        marker = uuid.uuid4()
        other_connection = SessionLocal()  # a different connection from `db`
        try:
            publish_event(
                other_connection, event_type=EventType.TASK_UPDATED,
                project_id=marker, entity_type="TASK", entity_id=marker,
            )
            other_connection.commit()  # NOTIFY is delivered on commit
        finally:
            other_connection.close()

        # The handler is scheduled on the loop, so pump it until it runs.
        deadline = time.monotonic() + 10
        while not seen.is_set() and time.monotonic() < deadline:
            loop.call_soon_threadsafe(lambda: None)
            loop.run_until_complete(asyncio.sleep(0.05))

        assert seen.is_set(), "an event published on another connection never arrived"
        assert any(e.project_id == marker for e in received)
    finally:
        listener.remove_handler(handler)
        listener.stop()
        loop.close()


def test_a_rolled_back_publish_announces_nothing(db):
    """pg_notify is transactional, so a rollback cannot ring a false alarm."""
    listener = get_listener()
    loop = asyncio.new_event_loop()
    received: list[RealtimeEvent] = []
    listener.add_handler(received.append)
    listener.start(loop)
    try:
        deadline = time.monotonic() + 10
        while not listener.is_connected and time.monotonic() < deadline:
            time.sleep(0.05)
        if not listener.is_connected:
            pytest.skip("realtime listener could not connect to PostgreSQL")

        marker = uuid.uuid4()
        session = SessionLocal()
        try:
            publish_event(session, event_type=EventType.TASK_UPDATED, project_id=marker)
            session.rollback()
        finally:
            session.close()

        # Give any (incorrect) delivery a generous chance to arrive.
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            loop.run_until_complete(asyncio.sleep(0.05))

        assert not any(e.project_id == marker for e in received), "a rolled-back event was delivered"
    finally:
        listener.remove_handler(received.append)
        listener.stop()
        loop.close()


def test_a_malformed_payload_does_not_kill_the_listener():
    """One bad message must not take realtime down for every client."""
    listener = get_listener()
    loop = asyncio.new_event_loop()
    received: list[RealtimeEvent] = []
    listener.add_handler(received.append)
    listener._loop = loop
    try:
        listener._dispatch("this is not json")
        listener._dispatch(json.dumps({"no_type_field": True}))
        assert received == []

        good = RealtimeEvent(type=EventType.TASK_UPDATED, project_id=uuid.uuid4())
        listener._dispatch(json.dumps(good.to_payload()))
        loop.run_until_complete(asyncio.sleep(0.05))
        assert len(received) == 1, "the listener stopped working after bad input"
    finally:
        listener.remove_handler(received.append)
        loop.close()


def test_the_listener_stops_without_hanging():
    """A listener that blocked shutdown would stall every container stop."""
    listener = get_listener()
    loop = asyncio.new_event_loop()
    try:
        listener.start(loop)
        time.sleep(0.5)
        started = time.monotonic()
        listener.stop()
        assert time.monotonic() - started < 6, "stop() did not return promptly"
        assert listener.is_connected is False
    finally:
        loop.close()
