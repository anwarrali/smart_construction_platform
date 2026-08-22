"""Push notifications: device registration, delivery, failure handling, isolation.

Two halves, deliberately separated:

  * The **provider** tests run with no database and no network. They pin the
    decisions that are easy to get wrong and expensive to get wrong — which FCM
    error means "retire this device" and which means "try again later" — by
    driving `FCMProvider` against a stub transport.
  * The **service** tests need PostgreSQL and skip without it, matching the
    convention in `test_smart_notifications.py`.

The load-bearing promise under test is that a push failure never costs the
database notification. Several tests therefore make delivery fail in a
different way each time and assert the row is still there afterwards.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.device_token import DeviceToken
from app.models.enums import (
    DevicePlatform, NotificationType, ProjectStatus, UserRole, UserStatus,
)
from app.models.notification import Notification
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services import device_token_service, notification_service
from app.services.push import dispatcher
from app.services.push.base import DeliveryStatus, PushMessage, PushResult
from app.services.push.fcm import FCMProvider


# --- fixtures ---------------------------------------------------------------


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
def people(db):
    """Two unrelated users. Isolation is only meaningful with a second person."""
    suffix = uuid.uuid4().hex[:10]

    def make(name):
        person = User(
            full_name=name,
            email=f"{name.lower()}.{suffix}@constro.io",
            hashed_password="x",
            role=UserRole.PROJECT_MANAGER,
            status=UserStatus.ACTIVE,
        )
        db.add(person)
        return person

    first, second = make("Rana"), make("Omar")
    db.flush()
    return first, second


# --- FCM provider: what counts as a dead token ------------------------------


class _StubTransport(httpx.BaseTransport):
    """Answers every send with a queued response; records what was sent."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, payload = self._responses.pop(0) if self._responses else (200, {})
        return httpx.Response(status, json=payload, request=request)


def _provider_with(responses) -> tuple[FCMProvider, _StubTransport]:
    """An FCMProvider that believes it is configured and never leaves the process."""
    provider = FCMProvider()
    provider._credentials = {
        "client_email": "svc@example.iam.gserviceaccount.com",
        "private_key": "unused-because-the-token-is-pre-seeded",
        "project_id": "test-project",
    }
    provider._project_id = "test-project"
    # Pre-seed the access token so no OAuth round trip is attempted.
    provider._access_token = "stub-access-token"
    provider._expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()

    return provider, _StubTransport(responses)


def _send_with_stub(monkeypatch, provider, transport, tokens, message):
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: original_client(*args, **{**kwargs, "transport": transport}),
    )
    return provider.send(tokens, message)


MESSAGE = PushMessage(title="Task assigned", body="Pour column C4", click_path="/notifications/x")


def test_unregistered_token_is_reported_as_dead(monkeypatch):
    """UNREGISTERED means the app was uninstalled: the row must be retired."""
    provider, transport = _provider_with([
        (404, {"error": {"status": "NOT_FOUND", "message": "Requested entity was not found.",
                         "details": [{"errorCode": "UNREGISTERED"}]}}),
    ])
    results = _send_with_stub(monkeypatch, provider, transport, ["dead-token"], MESSAGE)
    assert [r.status for r in results] == [DeliveryStatus.INVALID_TOKEN]
    assert results[0].should_deactivate is True


def test_server_error_is_transient_and_keeps_the_token(monkeypatch):
    """A 503 is FCM having a bad day. Deactivating here would unsubscribe a live device."""
    provider, transport = _provider_with([
        (503, {"error": {"status": "UNAVAILABLE", "message": "The service is unavailable."}}),
    ])
    results = _send_with_stub(monkeypatch, provider, transport, ["live-token"], MESSAGE)
    assert results[0].status is DeliveryStatus.TRANSIENT_FAILURE
    assert results[0].should_deactivate is False


def test_bad_credentials_never_blame_the_device(monkeypatch):
    """A 401 is our configuration. Retiring tokens over it would empty the estate."""
    provider, transport = _provider_with([
        (401, {"error": {"status": "UNAUTHENTICATED", "message": "Invalid credentials"}}),
    ])
    results = _send_with_stub(monkeypatch, provider, transport, ["live-token"], MESSAGE)
    assert results[0].status is DeliveryStatus.NOT_CONFIGURED
    assert results[0].should_deactivate is False


def test_unconfigured_provider_reports_rather_than_raising():
    """With no credentials the provider must degrade, not explode."""
    provider = FCMProvider()
    provider._credentials = None
    provider._project_id = ""
    results = provider.send(["any-token"], MESSAGE)
    assert [r.status for r in results] == [DeliveryStatus.NOT_CONFIGURED]


def test_multiple_devices_each_get_their_own_request(monkeypatch):
    """One user, three devices, three sends — not one send to the newest."""
    provider, transport = _provider_with([(200, {"name": "ok"})] * 3)
    tokens = ["android-token", "ios-token", "web-token"]
    results = _send_with_stub(monkeypatch, provider, transport, tokens, MESSAGE)
    assert len(transport.requests) == 3
    assert all(r.status is DeliveryStatus.SENT for r in results)


def test_payload_carries_routing_information():
    """A tap can only navigate if the payload names the subject."""
    notification = Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Issue assigned to you",
        message="Cracking on level 3",
        type=NotificationType.TASK_ASSIGNED,
        category="WORKFLOW",
        priority="NORMAL",
        project_id=uuid.uuid4(),
        related_entity_type="ISSUE",
        related_entity_id=uuid.uuid4(),
    )
    message = notification_service.build_push_message(notification)
    payload = message.as_data_payload()
    assert payload["entityType"] == "ISSUE"
    assert payload["entityId"] == str(notification.related_entity_id)
    assert payload["projectId"] == str(notification.project_id)
    assert payload["notificationId"] == str(notification.id)
    assert message.click_path == f"/notifications/{notification.id}"


# --- device registration ----------------------------------------------------


def test_a_user_may_register_several_devices(db, people):
    """The whole point of the model: a phone, a tablet and a browser at once."""
    user, _ = people
    for platform, token in (
        (DevicePlatform.ANDROID, "tok-android"),
        (DevicePlatform.IOS, "tok-ios"),
        (DevicePlatform.WEB, "tok-web"),
    ):
        device_token_service.register_device(
            db, user_id=user.id, token=f"{token}-{user.id}", platform=platform
        )
    db.flush()
    tokens = dispatcher.active_tokens_for_users(db, [user.id])[user.id]
    assert len(tokens) == 3


def test_registering_twice_updates_rather_than_duplicates(db, people):
    """A device re-registers on every cold start; that must not grow the table."""
    user, _ = people
    token = f"tok-repeat-{user.id}"
    first = device_token_service.register_device(
        db, user_id=user.id, token=token, platform=DevicePlatform.ANDROID
    )
    second = device_token_service.register_device(
        db, user_id=user.id, token=token, platform=DevicePlatform.ANDROID
    )
    db.flush()
    assert first.id == second.id
    assert len(dispatcher.active_tokens_for_users(db, [user.id])[user.id]) == 1


def test_token_refresh_retires_the_previous_token_for_that_device(db, people):
    """FCM rotates tokens. The old one is dead but never reports itself so."""
    user, _ = people
    device_id = f"install-{uuid.uuid4().hex[:8]}"
    device_token_service.register_device(
        db, user_id=user.id, token=f"old-{device_id}",
        platform=DevicePlatform.ANDROID, device_id=device_id,
    )
    device_token_service.register_device(
        db, user_id=user.id, token=f"new-{device_id}",
        platform=DevicePlatform.ANDROID, device_id=device_id,
    )
    db.flush()
    active = dispatcher.active_tokens_for_users(db, [user.id])[user.id]
    assert active == [f"new-{device_id}"]


def test_a_shared_device_moves_to_whoever_signs_in(db, people):
    """A site tablet changes hands. Its pushes must follow the current user."""
    first, second = people
    token = f"tok-shared-{uuid.uuid4().hex[:8]}"
    device_token_service.register_device(
        db, user_id=first.id, token=token, platform=DevicePlatform.ANDROID
    )
    device_token_service.register_device(
        db, user_id=second.id, token=token, platform=DevicePlatform.ANDROID
    )
    db.flush()
    assert dispatcher.active_tokens_for_users(db, [first.id]).get(first.id, []) == []
    assert dispatcher.active_tokens_for_users(db, [second.id])[second.id] == [token]


def test_unregister_cannot_touch_another_users_device(db, people):
    """Guessing a token must not let anybody unsubscribe somebody else."""
    first, second = people
    token = f"tok-private-{uuid.uuid4().hex[:8]}"
    device_token_service.register_device(
        db, user_id=first.id, token=token, platform=DevicePlatform.ANDROID
    )
    db.flush()
    removed = device_token_service.unregister_device(db, user_id=second.id, token=token)
    db.flush()
    assert removed == 0
    assert dispatcher.active_tokens_for_users(db, [first.id])[first.id] == [token]


def test_unregister_deactivates_rather_than_deletes(db, people):
    """Keeping the row preserves the answer to 'was this ever registered'."""
    user, _ = people
    token = f"tok-signout-{uuid.uuid4().hex[:8]}"
    device_token_service.register_device(
        db, user_id=user.id, token=token, platform=DevicePlatform.WEB
    )
    db.flush()
    assert device_token_service.unregister_device(db, user_id=user.id, token=token) == 1
    db.flush()
    row = db.query(DeviceToken).filter(DeviceToken.token == token).one()
    assert row.is_active is False
    assert row.deactivated_reason == "signed out"


def test_invalid_tokens_are_deactivated_and_healthy_ones_are_touched(db, people):
    """The cleanup path: one dead device retired, the live one left alone."""
    user, _ = people
    dead = f"tok-dead-{uuid.uuid4().hex[:8]}"
    live = f"tok-live-{uuid.uuid4().hex[:8]}"
    for token in (dead, live):
        device_token_service.register_device(
            db, user_id=user.id, token=token, platform=DevicePlatform.ANDROID
        )
    db.flush()

    dispatcher.apply_results(db, [
        PushResult(dead, DeliveryStatus.INVALID_TOKEN, "UNREGISTERED"),
        PushResult(live, DeliveryStatus.SENT),
    ])
    db.flush()

    assert dispatcher.active_tokens_for_users(db, [user.id])[user.id] == [live]
    retired = db.query(DeviceToken).filter(DeviceToken.token == dead).one()
    assert retired.deactivated_reason == "UNREGISTERED"


def test_transient_failure_leaves_every_token_active(db, people):
    """An outage must not quietly unsubscribe the whole estate."""
    user, _ = people
    token = f"tok-flaky-{uuid.uuid4().hex[:8]}"
    device_token_service.register_device(
        db, user_id=user.id, token=token, platform=DevicePlatform.IOS
    )
    db.flush()
    dispatcher.apply_results(db, [PushResult(token, DeliveryStatus.TRANSIENT_FAILURE, "timeout")])
    db.flush()
    assert dispatcher.active_tokens_for_users(db, [user.id])[user.id] == [token]


# --- notification service ---------------------------------------------------


def test_push_failure_never_costs_the_database_notification(db, people, monkeypatch):
    """The core promise. Delivery explodes; the row survives regardless."""
    user, _ = people

    def explode(*args, **kwargs):
        raise RuntimeError("FCM is down")

    monkeypatch.setattr(dispatcher, "send_to_user", explode)

    created = notification_service.notify_user(
        db, user_id=user.id, title="Task assigned", message="Pour column C4",
        notification_type=NotificationType.TASK_ASSIGNED,
    )
    db.flush()

    assert created is not None
    assert db.query(Notification).filter(Notification.id == created.id).one()


def test_notify_users_does_not_notify_anybody_twice(db, people):
    """Recipient lists are unions of overlapping roles; one event, one notice."""
    first, second = people
    created = notification_service.notify_users(
        db,
        user_ids=[first.id, second.id, first.id, None],
        title="Site report submitted",
        message="Awaiting your verification",
        notification_type=NotificationType.REPORT_READY,
    )
    db.flush()
    assert len(created) == 2
    assert {n.user_id for n in created} == {first.id, second.id}


def test_mark_as_read_refuses_another_users_notification(db, people):
    """Ownership lives in the WHERE clause; a foreign id is simply not found."""
    first, second = people
    notification = notification_service.notify_user(
        db, user_id=first.id, title="Private", message="For Rana only",
    )
    db.flush()

    assert notification_service.mark_as_read(
        db, notification_id=notification.id, user_id=second.id
    ) is False
    db.refresh(notification)
    assert notification.is_read is False

    assert notification_service.mark_as_read(
        db, notification_id=notification.id, user_id=first.id
    ) is True


def test_unread_count_is_scoped_to_the_user(db, people):
    """A count that leaked across users would be a data leak in miniature."""
    first, second = people
    before_first = notification_service.unread_count(db, user_id=first.id)
    before_second = notification_service.unread_count(db, user_id=second.id)

    for index in range(3):
        notification_service.notify_user(
            db, user_id=first.id, title=f"N{index}", message="body",
        )
    db.flush()

    assert notification_service.unread_count(db, user_id=first.id) == before_first + 3
    assert notification_service.unread_count(db, user_id=second.id) == before_second


def test_mark_all_as_read_stops_at_the_users_own_rows(db, people):
    first, second = people
    notification_service.notify_user(db, user_id=first.id, title="A", message="a")
    others = notification_service.notify_user(db, user_id=second.id, title="B", message="b")
    db.flush()

    notification_service.mark_all_as_read(db, user_id=first.id)
    db.flush()

    assert notification_service.unread_count(db, user_id=first.id) == 0
    db.refresh(others)
    assert others.is_read is False


def test_read_state_records_when_it_happened(db, people):
    user, _ = people
    notification = notification_service.notify_user(
        db, user_id=user.id, title="Timed", message="body"
    )
    db.flush()
    assert notification.read_at is None

    notification_service.mark_as_read(db, notification_id=notification.id, user_id=user.id)
    db.flush()
    db.refresh(notification)
    assert notification.read_at is not None


def test_project_notification_reaches_the_team_but_not_the_actor(db, people):
    """`exclude_user_id` is what stops telling somebody what they just did."""
    manager, member = people
    project = Project(
        name=f"Push test {uuid.uuid4().hex[:6]}",
        status=ProjectStatus.ACTIVE,
        owner_id=manager.id,
        project_manager_id=manager.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id,
        user_id=member.id,
        # NOT NULL, and there is no default: a membership without a role on the
        # project is not a membership.
        role_on_project=UserRole.PROJECT_MANAGER,
        is_active=True,
    ))
    db.flush()

    created = notification_service.notify_project_users(
        db,
        project_id=project.id,
        exclude_user_id=manager.id,
        title="Site report submitted",
        message="A site report is awaiting verification",
        notification_type=NotificationType.REPORT_READY,
    )
    db.flush()

    recipients = {n.user_id for n in created}
    assert member.id in recipients
    assert manager.id not in recipients
    assert all(n.project_id == project.id for n in created)


def test_pagination_returns_a_stable_newest_first_window(db, people):
    """Page 2 must not repeat page 1; ordering is by created_at DESC."""
    user, _ = people
    for index in range(7):
        notification_service.notify_user(
            db, user_id=user.id, title=f"Paged {index}", message="body",
        )
    db.flush()

    query = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    page_one = query.limit(3).all()
    page_two = query.offset(3).limit(3).all()

    assert len(page_one) == 3 and len(page_two) == 3
    assert not {n.id for n in page_one} & {n.id for n in page_two}


# --- the commit boundary ----------------------------------------------------
#
# The claim this system rests on is that push is queued during the caller's
# transaction and only released once that transaction commits. These two tests
# are the ones that prove it against a real database rather than a stub, so
# they commit for real and clean up after themselves.


@pytest.fixture()
def committed_user(db):
    """A user that genuinely exists in the database, removed afterwards."""
    person = User(
        full_name="PushBoundary",
        email=f"pushboundary.{uuid.uuid4().hex[:10]}@constro.io",
        hashed_password="x",
        role=UserRole.PROJECT_MANAGER,
        status=UserStatus.ACTIVE,
    )
    db.add(person)
    db.commit()
    try:
        yield person
    finally:
        db.query(Notification).filter(Notification.user_id == person.id).delete()
        db.query(DeviceToken).filter(DeviceToken.user_id == person.id).delete()
        db.query(User).filter(User.id == person.id).delete()
        db.commit()


class _RecordingProvider:
    """Stands in for FCM. Records what it was asked to deliver."""

    def __init__(self):
        self.calls: list[tuple[list[str], PushMessage]] = []

    @property
    def is_configured(self):
        return True

    def send(self, tokens, message):
        self.calls.append((list(tokens), message))
        return [PushResult(token, DeliveryStatus.SENT) for token in tokens]


@pytest.fixture()
def recording_push(monkeypatch):
    """Push switched on, delivered inline, and pointed at a recorder."""
    provider = _RecordingProvider()
    monkeypatch.setattr(dispatcher.settings, "PUSH_ENABLED", True)
    # Inline, so the assertion does not race a background thread.
    monkeypatch.setattr(dispatcher.settings, "PUSH_SYNCHRONOUS", True)
    monkeypatch.setattr(dispatcher, "get_provider", lambda: provider)
    return provider


def test_a_committed_notification_is_pushed_to_every_registered_device(
    db, committed_user, recording_push
):
    for platform, suffix in ((DevicePlatform.ANDROID, "phone"), (DevicePlatform.WEB, "browser")):
        device_token_service.register_device(
            db, user_id=committed_user.id,
            token=f"tok-{suffix}-{uuid.uuid4().hex[:8]}", platform=platform,
        )
    db.commit()

    notification = notification_service.notify_user(
        db, user_id=committed_user.id, title="Task assigned", message="Pour column C4",
        notification_type=NotificationType.TASK_ASSIGNED,
    )
    # Nothing may have been delivered yet: the row is not committed.
    assert recording_push.calls == [], "push escaped before the commit"

    db.commit()

    assert len(recording_push.calls) == 1, "the commit must release exactly one push"
    tokens, message = recording_push.calls[0]
    assert len(tokens) == 2, "both devices, not just the most recent one"
    assert message.title == "Task assigned"
    assert message.as_data_payload()["notificationId"] == str(notification.id)


def test_a_rolled_back_notification_is_never_pushed(db, committed_user, recording_push):
    """A doorbell must not ring for something that did not happen."""
    device_token_service.register_device(
        db, user_id=committed_user.id,
        token=f"tok-rollback-{uuid.uuid4().hex[:8]}", platform=DevicePlatform.ANDROID,
    )
    db.commit()

    notification_service.notify_user(
        db, user_id=committed_user.id, title="Never happened", message="rolled back",
    )
    db.rollback()

    assert recording_push.calls == []
    # And a later, unrelated commit must not flush the discarded queue either.
    db.commit()
    assert recording_push.calls == []
