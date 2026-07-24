import uuid

import pytest

from app.core.security import hash_password, verify_password
from app.db.seed_demo import (
    _ensure_user,
    load_config,
    stable_id,
)
from app.models.company import Company
from app.models.enums import UserRole, UserStatus
from app.models.user import User


class OneResult:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def one_or_none(self):
        return self.value


class UserSession:
    def __init__(self, user):
        self.user = user
        self.added = []

    def get(self, model, record_id):
        if model is User and self.user and self.user.id == record_id:
            return self.user
        return None

    def query(self, model):
        if model is User:
            return OneResult(self.user)
        return OneResult(None)

    def add(self, value):
        self.added.append(value)


def _company():
    return Company(
        id=stable_id("company:contractor"),
        name="Al-Nour General Contracting",
        is_active=True,
    )


def _demo_user(password="OriginalDemoPass123"):
    company = _company()
    return User(
        id=stable_id("user:worker1"),
        email="worker.one.demo@smartconstruction-demo.com",
        full_name="Ahmad Barakat",
        hashed_password=hash_password(password),
        role=UserRole.WORKER,
        status=UserStatus.ACTIVE,
        is_email_verified=True,
        is_superuser=False,
        must_change_password=False,
        invitation_accepted=True,
        company_id=company.id,
    )


def test_seed_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DEMO_SEED", raising=False)
    monkeypatch.delenv("DEMO_USER_PASSWORD", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    assert load_config() is None


def test_enabled_seed_requires_exact_staging_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "ValidDemoPass123")

    with pytest.raises(ValueError, match="exactly 'staging'"):
        load_config()


def test_enabled_seed_accepts_a_dedicated_existing_admin_email(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DEMO_USER_PASSWORD", "ValidDemoPass123")
    monkeypatch.setenv("DEMO_SEED_ADMIN_EMAIL", " Admin@Example.com ")

    config = load_config()

    assert config is not None
    assert config.bootstrap_email == "admin@example.com"


@pytest.mark.parametrize(
    "password",
    [
        "short1A",
        "alllowercase123",
        "ALLUPPERCASE123",
        "NoNumbersPresent",
        " ValidDemoPass123",
        "ValidDemoPass123 ",
    ],
)
def test_enabled_seed_enforces_password_policy(monkeypatch, password):
    monkeypatch.setenv("ENABLE_DEMO_SEED", "true")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("DEMO_USER_PASSWORD", password)

    with pytest.raises(ValueError, match="DEMO_USER_PASSWORD"):
        load_config()


def test_stable_ids_are_deterministic_and_distinct():
    assert stable_id("user:worker1") == stable_id("user:worker1")
    assert stable_id("user:worker1") != stable_id("user:worker2")
    assert isinstance(stable_id("project:al-nour-residential"), uuid.UUID)


def test_rerun_does_not_reset_a_demo_users_password(monkeypatch):
    user = _demo_user()
    original_hash = user.hashed_password
    db = UserSession(user)

    monkeypatch.setattr(
        "app.db.seed_demo.hash_password",
        lambda value: pytest.fail("rerun must not hash or replace an existing password"),
    )
    returned = _ensure_user(
        db,
        key="worker1",
        email=user.email,
        full_name=user.full_name,
        role=UserRole.WORKER,
        company=_company(),
        password="DifferentDemoPass123",
    )

    assert returned is user
    assert user.hashed_password == original_hash
    assert verify_password("OriginalDemoPass123", user.hashed_password)
    assert db.added == []


def test_email_collision_never_modifies_a_real_user(monkeypatch):
    company = _company()
    real_user = User(
        id=uuid.uuid4(),
        email="worker.one.demo@smartconstruction-demo.com",
        full_name="Existing Real User",
        hashed_password=hash_password("ExistingRealPass123"),
        role=UserRole.OWNER,
        status=UserStatus.ACTIVE,
        is_email_verified=True,
        is_superuser=False,
        must_change_password=False,
        invitation_accepted=True,
        company_id=company.id,
    )
    original_hash = real_user.hashed_password
    db = UserSession(real_user)
    monkeypatch.setattr(
        "app.db.seed_demo.hash_password",
        lambda value: pytest.fail("collision handling must not hash a replacement password"),
    )

    with pytest.raises(RuntimeError, match="existing non-demo account"):
        _ensure_user(
            db,
            key="worker1",
            email=real_user.email,
            full_name="Ahmad Barakat",
            role=UserRole.WORKER,
            company=company,
            password="DifferentDemoPass123",
        )

    assert real_user.role == UserRole.OWNER
    assert real_user.hashed_password == original_hash
