import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import func

from app.api.auth import login
from app.core.deps import get_current_user
from app.core.security import verify_password
from app.db.bootstrap_admin import BootstrapConfig, bootstrap_admin
from app.models.audit_log import AuditLog
from app.models.enums import UserRole, UserStatus
from app.models.revoked_token import RevokedToken
from app.models.user import User


class QueryResult:
    def __init__(self, *, one=None, all_items=None, scalar_value=0, first=None):
        self.one = one
        self.all_items = all_items or []
        self.scalar_value = scalar_value
        self.first_value = first

    def filter(self, *args, **kwargs):
        return self

    def one_or_none(self):
        return self.one

    def all(self):
        return self.all_items

    def scalar(self):
        return self.scalar_value

    def first(self):
        return self.first_value

    def delete(self, *args, **kwargs):
        return 0


class BootstrapSession:
    def __init__(self, *, existing=None, admins=None, user_count=0):
        self.existing = existing
        self.admins = admins or []
        self.user_count = user_count
        self.user_queries = 0
        self.added = []
        self.commits = 0

    def query(self, entity):
        if entity is User:
            self.user_queries += 1
            if self.user_queries == 1:
                return QueryResult(one=self.existing)
            return QueryResult(all_items=self.admins)
        return QueryResult(scalar_value=self.user_count)

    def add(self, entity):
        self.added.append(entity)

    def commit(self):
        self.commits += 1

    def refresh(self, entity):
        if isinstance(entity, User) and entity.id is None:
            entity.id = uuid.uuid4()


class AuthSession:
    def __init__(self, user):
        self.user = user

    def query(self, entity):
        if entity is RevokedToken:
            return QueryResult()
        if entity is User:
            return QueryResult(first=self.user)
        raise AssertionError(f"Unexpected query entity: {entity}")

    def commit(self):
        return None


@pytest.fixture
def migration_head(monkeypatch):
    monkeypatch.setattr(
        "app.db.bootstrap_admin._require_alembic_head",
        lambda db: "x25a8e3c0b24",
    )


def config(password="SafeStagePass12345", *, recover=False):
    return BootstrapConfig(
        email="admin@example.com",
        password=password,
        full_name="Stage Administrator",
        recover_password=recover,
    )


def pending_admin(password="OriginalPass12345"):
    from app.core.security import hash_password

    return User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Stage Administrator",
        hashed_password=hash_password(password),
        role=UserRole.ADMIN,
        status=UserStatus.PENDING,
        is_email_verified=True,
        is_superuser=True,
        must_change_password=True,
        invitation_accepted=False,
    )


def test_fresh_bootstrap_hash_authenticates_and_wrong_password_is_rejected(migration_head):
    db = BootstrapSession()
    bootstrap_admin(db, config())
    user = next(entity for entity in db.added if isinstance(entity, User))

    assert verify_password("SafeStagePass12345", user.hashed_password)
    token = login(
        SimpleNamespace(username=user.email, password="SafeStagePass12345"),
        AuthSession(user),
    )
    assert token["role"] == "admin"
    assert user.must_change_password is True

    with pytest.raises(HTTPException) as exc:
        login(
            SimpleNamespace(username=user.email, password="WrongPass12345"),
            AuthSession(user),
        )
    assert exc.value.status_code == 401


def test_pending_bootstrap_admin_can_read_profile_but_cannot_edit_it(migration_head):
    db = BootstrapSession()
    bootstrap_admin(db, config())
    user = next(entity for entity in db.added if isinstance(entity, User))
    token = login(
        SimpleNamespace(username=user.email, password="SafeStagePass12345"),
        AuthSession(user),
    )["access_token"]

    read_request = Request(
        {"type": "http", "method": "GET", "path": "/api/v1/users/profile", "headers": []}
    )
    assert get_current_user(read_request, token, AuthSession(user)) is user

    write_request = Request(
        {"type": "http", "method": "PUT", "path": "/api/v1/users/profile", "headers": []}
    )
    with pytest.raises(HTTPException) as exc:
        get_current_user(write_request, token, AuthSession(user))
    assert exc.value.status_code == 403
    assert exc.value.detail == "PASSWORD_CHANGE_REQUIRED"


def test_password_mismatch_does_not_reset_without_explicit_recovery(migration_head):
    user = pending_admin()
    db = BootstrapSession(existing=user, admins=[user], user_count=1)

    with pytest.raises(RuntimeError, match="RECOVER_PASSWORD=true"):
        bootstrap_admin(db, config("ReplacementPass12345"))

    assert verify_password("OriginalPass12345", user.hashed_password)
    assert db.commits == 0


def test_explicit_recovery_resets_only_pending_bootstrap_admin_and_audits(migration_head):
    user = pending_admin()
    db = BootstrapSession(existing=user, admins=[user], user_count=1)

    result = bootstrap_admin(db, config("ReplacementPass12345", recover=True))

    assert "Recovered initial administrator password" in result
    assert verify_password("ReplacementPass12345", user.hashed_password)
    assert not verify_password("OriginalPass12345", user.hashed_password)
    audit = next(entity for entity in db.added if isinstance(entity, AuditLog))
    assert audit.action == "bootstrap_password_recovery"
    assert audit.entity_id == user.id
    assert db.commits == 1


def test_recovery_cannot_reset_an_ordinary_user(migration_head):
    user = pending_admin()
    user.role = UserRole.OWNER
    user.is_superuser = False
    db = BootstrapSession(existing=user, admins=[], user_count=1)

    with pytest.raises(RuntimeError, match="refusing to change its privileges"):
        bootstrap_admin(db, config("ReplacementPass12345", recover=True))

    assert verify_password("OriginalPass12345", user.hashed_password)
    assert db.commits == 0


def test_recovery_cannot_reset_an_activated_admin(migration_head):
    user = pending_admin()
    user.status = UserStatus.ACTIVE
    user.invitation_accepted = True
    db = BootstrapSession(existing=user, admins=[user], user_count=1)

    with pytest.raises(RuntimeError, match="lone, pending"):
        bootstrap_admin(db, config("ReplacementPass12345", recover=True))

    assert verify_password("OriginalPass12345", user.hashed_password)
    assert db.commits == 0
