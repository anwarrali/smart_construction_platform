"""The notification HTTP surface, exercised through the real app.

These go through `TestClient` rather than calling the endpoint functions
directly, because the security properties under test live in the dependency
layer: calling a handler directly bypasses `Depends(get_current_user)` entirely
and would make an unprotected endpoint look protected. The same reasoning as
the note in `test_step_up_security.py`.

What is being pinned here is mostly *isolation*: that one user's notifications,
unread count, read state and registered devices are unreachable from another
user's session, no matter which endpoint is asked.
"""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.device_token import DeviceToken
from app.models.enums import NotificationType, UserRole, UserStatus
from app.models.notification import Notification
from app.models.user import User
from app.services import notification_service

PASSWORD = "Correct#12345"


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
    """Two active users. Isolation is only testable with a second person."""
    suffix = uuid4().hex[:10]

    def user(name):
        person = User(
            full_name=name,
            email=f"{name.lower()}.{suffix}@constro.io",
            hashed_password=hash_password(PASSWORD),
            role=UserRole.PROJECT_MANAGER,
            status=UserStatus.ACTIVE,
        )
        db.add(person)
        return person

    first, second = user("NotifyOne"), user("NotifyTwo")
    db.commit()
    try:
        yield first, second
    finally:
        # Deleting the users cascades their notifications and device tokens,
        # so this leaves no residue in a shared development database.
        for person in (first, second):
            db.query(Notification).filter(Notification.user_id == person.id).delete()
            db.query(DeviceToken).filter(DeviceToken.user_id == person.id).delete()
        db.query(User).filter(User.id.in_([first.id, second.id])).delete(
            synchronize_session=False
        )
        db.commit()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


def _auth(client, user) -> dict:
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _make_notification(db, user, title="Task assigned", **kwargs):
    notification = notification_service.notify_user(
        db,
        user_id=user.id,
        title=title,
        message="Pour column C4",
        notification_type=NotificationType.TASK_ASSIGNED,
        **kwargs,
    )
    db.commit()
    return notification


# --- authentication ---------------------------------------------------------


def test_every_notification_route_refuses_an_anonymous_caller(client):
    """The whole surface, not a sample: an unauthenticated route is a leak."""
    for method, path in (
        ("get", "/api/v1/notifications"),
        ("get", "/api/v1/notifications/unread-count"),
        ("get", "/api/v1/notifications/devices"),
        ("post", "/api/v1/notifications/devices"),
        ("delete", "/api/v1/notifications/devices"),
        ("patch", "/api/v1/notifications/read-all"),
        ("post", "/api/v1/notifications/dev/test-notification"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 401, f"{method.upper()} {path} → {response.status_code}"


# --- reading ----------------------------------------------------------------


def test_history_is_paginated_and_newest_first(db, client, people):
    user, _ = people
    for index in range(5):
        _make_notification(db, user, title=f"Paged {index}")

    headers = _auth(client, user)
    page_one = client.get("/api/v1/notifications?page=1&limit=2", headers=headers).json()
    page_two = client.get("/api/v1/notifications?page=2&limit=2", headers=headers).json()

    assert page_one["total"] == 5
    assert page_one["totalPages"] == 3
    assert len(page_one["items"]) == 2
    # Newest first, and page 2 continues rather than repeating page 1.
    assert page_one["items"][0]["title"] == "Paged 4"
    assert not {n["id"] for n in page_one["items"]} & {n["id"] for n in page_two["items"]}


def test_the_list_never_includes_another_users_notifications(db, client, people):
    first, second = people
    _make_notification(db, first, title="For NotifyOne only")

    items = client.get("/api/v1/notifications", headers=_auth(client, second)).json()["items"]
    assert all(n["title"] != "For NotifyOne only" for n in items)


def test_unread_count_is_per_user(db, client, people):
    first, second = people
    before = client.get(
        "/api/v1/notifications/unread-count", headers=_auth(client, second)
    ).json()["count"]

    for _ in range(3):
        _make_notification(db, first)

    assert client.get(
        "/api/v1/notifications/unread-count", headers=_auth(client, first)
    ).json()["count"] == 3
    assert client.get(
        "/api/v1/notifications/unread-count", headers=_auth(client, second)
    ).json()["count"] == before


def test_fetching_one_notification_that_is_not_yours_is_a_404(db, client, people):
    """404, not 403 — a foreign id must not be confirmed to exist."""
    first, second = people
    notification = _make_notification(db, first)

    assert client.get(
        f"/api/v1/notifications/{notification.id}", headers=_auth(client, second)
    ).status_code == 404
    assert client.get(
        f"/api/v1/notifications/{notification.id}", headers=_auth(client, first)
    ).status_code == 200


# --- read state -------------------------------------------------------------


def test_marking_read_works_through_both_patch_and_put(db, client, people):
    """PATCH is correct; PUT is kept because shipped clients call it."""
    user, _ = people
    headers = _auth(client, user)

    for method in ("patch", "put"):
        notification = _make_notification(db, user)
        response = getattr(client, method)(
            f"/api/v1/notifications/{notification.id}/read", headers=headers
        )
        assert response.status_code == 200, response.text
        db.refresh(notification)
        assert notification.is_read is True
        assert notification.read_at is not None, "read_at must record when"


def test_another_user_cannot_mark_your_notification_read(db, client, people):
    first, second = people
    notification = _make_notification(db, first)

    assert client.patch(
        f"/api/v1/notifications/{notification.id}/read", headers=_auth(client, second)
    ).status_code == 404

    db.refresh(notification)
    assert notification.is_read is False, "it must be genuinely untouched"


def test_read_all_stops_at_the_callers_own_rows(db, client, people):
    first, second = people
    _make_notification(db, first)
    theirs = _make_notification(db, second)

    response = client.patch("/api/v1/notifications/read-all", headers=_auth(client, first))
    assert response.status_code == 200

    assert client.get(
        "/api/v1/notifications/unread-count", headers=_auth(client, first)
    ).json()["count"] == 0
    db.refresh(theirs)
    assert theirs.is_read is False


# --- devices ----------------------------------------------------------------


def _register(client, headers, token, platform="android", **extra):
    return client.post(
        "/api/v1/notifications/devices",
        headers=headers,
        json={"token": token, "platform": platform, **extra},
    )


def test_registering_a_device_never_echoes_the_token_back(client, people):
    """The token is a delivery address; the API describes the device instead."""
    user, _ = people
    headers = _auth(client, user)
    token = f"tok-{uuid4().hex}"

    response = _register(client, headers, token, deviceName="Pixel 8")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["deviceName"] == "Pixel 8"
    assert body["isActive"] is True
    assert token not in response.text


def test_a_user_can_register_several_devices_and_sees_only_their_own(client, people):
    first, second = people
    mine, theirs = _auth(client, first), _auth(client, second)

    for platform in ("android", "ios", "web"):
        assert _register(client, mine, f"tok-{platform}-{uuid4().hex}", platform).status_code == 201
    _register(client, theirs, f"tok-other-{uuid4().hex}")

    listed = client.get("/api/v1/notifications/devices", headers=mine).json()
    assert len(listed) == 3
    assert {device["platform"] for device in listed} == {"android", "ios", "web"}

    assert len(client.get("/api/v1/notifications/devices", headers=theirs).json()) == 1


def test_registering_the_same_device_twice_is_idempotent(client, people):
    """Clients re-register on every app start; that must not grow the table."""
    user, _ = people
    headers = _auth(client, user)
    token = f"tok-{uuid4().hex}"

    first = _register(client, headers, token)
    second = _register(client, headers, token)
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/v1/notifications/devices", headers=headers).json()) == 1


def test_a_shared_handset_follows_whoever_signed_in(client, people):
    """A site tablet changes hands; its pushes must not follow the old user."""
    first, second = people
    token = f"tok-shared-{uuid4().hex}"

    _register(client, _auth(client, first), token)
    _register(client, _auth(client, second), token)

    assert client.get(
        "/api/v1/notifications/devices", headers=_auth(client, first)
    ).json() == []
    assert len(client.get(
        "/api/v1/notifications/devices", headers=_auth(client, second)
    ).json()) == 1


def test_you_cannot_unregister_a_device_by_guessing_its_token(client, people):
    first, second = people
    token = f"tok-private-{uuid4().hex}"
    _register(client, _auth(client, first), token)

    response = client.request(
        "DELETE",
        "/api/v1/notifications/devices",
        headers=_auth(client, second),
        json={"token": token},
    )
    assert response.status_code == 204  # nothing matched; nothing to report
    assert len(client.get(
        "/api/v1/notifications/devices", headers=_auth(client, first)
    ).json()) == 1, "the owner's device must survive"


def test_signing_out_retires_the_device(db, client, people):
    user, _ = people
    headers = _auth(client, user)
    token = f"tok-signout-{uuid4().hex}"
    _register(client, headers, token, deviceId="install-1")

    response = client.request(
        "DELETE", "/api/v1/notifications/devices", headers=headers,
        json={"deviceId": "install-1"},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/notifications/devices", headers=headers).json() == []

    # Retired, not deleted: the row is what distinguishes "never registered"
    # from "signed out" when a missing notification is investigated.
    row = db.query(DeviceToken).filter(DeviceToken.token == token).one()
    assert row.is_active is False
    assert row.deactivated_reason == "signed out"


# --- the development-only trigger -------------------------------------------


def test_the_dev_trigger_is_absent_unless_explicitly_enabled(client, people):
    """404 rather than 403: a disabled endpoint should not confirm it exists."""
    user, _ = people
    assert settings.NOTIFICATION_DEV_TEST_ENABLED is False, (
        "the flag must default to false, or a production deployment that "
        "changes nothing would expose this route"
    )
    response = client.post(
        "/api/v1/notifications/dev/test-notification", headers=_auth(client, user)
    )
    assert response.status_code == 404


def test_the_dev_trigger_can_only_ever_notify_the_caller(db, client, monkeypatch, people):
    """Even switched on, there is no parameter that redirects it."""
    first, second = people
    monkeypatch.setattr(settings, "NOTIFICATION_DEV_TEST_ENABLED", True)

    response = client.post(
        "/api/v1/notifications/dev/test-notification", headers=_auth(client, first)
    )
    assert response.status_code == 200, response.text
    assert response.json()["userId"] == str(first.id)

    # And it landed in the caller's history, not the other user's.
    assert client.get(
        "/api/v1/notifications/unread-count", headers=_auth(client, first)
    ).json()["count"] == 1
    assert client.get(
        "/api/v1/notifications/unread-count", headers=_auth(client, second)
    ).json()["count"] == 0
