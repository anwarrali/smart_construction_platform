"""Login brute-force protection.

The security audit found login completely unthrottled: an attacker could make
unlimited password guesses against any address they knew. These tests pin the
limit that closed it.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import LOGIN_SCOPE, login
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.user import User


class _Form:
    """Stands in for OAuth2PasswordRequestForm, which the endpoint takes."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password


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
def account(db):
    suffix = uuid4().hex[:10]
    email = f"ratelimit.{suffix}@constro.io"
    user = User(full_name="Rate Limited", email=email,
                hashed_password=hash_password("Correct#12345"),
                role=UserRole.ENGINEER, status=UserStatus.ACTIVE)
    db.add(user)
    db.commit()
    yield user, email
    db.rollback()
    db.execute(text("DELETE FROM rate_limit_hits WHERE key = :key"), {"key": email})
    db.execute(text("DELETE FROM rate_limit_hits WHERE key = :key"),
               {"key": f"unknown.{suffix}@constro.io"})
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    db.commit()


def test_repeated_wrong_passwords_are_eventually_refused(db, account):
    _, email = account
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(HTTPException) as error:
            login(_Form(email, "Wrong#Guess1"), db=db)
        assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        login(_Form(email, "Wrong#Guess1"), db=db)
    assert error.value.status_code == 429


def test_the_throttle_still_applies_when_the_correct_password_arrives_late(db, account):
    """Otherwise an attacker's final successful guess would sail through."""
    _, email = account
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(HTTPException):
            login(_Form(email, "Wrong#Guess1"), db=db)
    with pytest.raises(HTTPException) as error:
        login(_Form(email, "Correct#12345"), db=db)
    assert error.value.status_code == 429


def test_a_successful_login_clears_the_failure_history(db, account):
    """A user who mistypes twice must not stay throttled afterwards."""
    _, email = account
    for _ in range(3):
        with pytest.raises(HTTPException):
            login(_Form(email, "Wrong#Guess1"), db=db)
    assert login(_Form(email, "Correct#12345"), db=db)["access_token"]
    from app.services import rate_limit_service
    assert rate_limit_service.count_recent(
        db, scope=LOGIN_SCOPE, key=email, window_seconds=3600) == 0


def test_attempts_against_an_unknown_address_are_also_counted(db, account):
    """Counting only real accounts would turn the throttle itself into an
    account-enumeration oracle: unlimited guesses would mean "no such user"."""
    _, email = account
    unknown = email.replace("ratelimit.", "unknown.")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(HTTPException) as error:
            login(_Form(unknown, "Wrong#Guess1"), db=db)
        assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        login(_Form(unknown, "Wrong#Guess1"), db=db)
    assert error.value.status_code == 429


def test_one_account_being_throttled_does_not_lock_out_another(db, account):
    user, email = account
    other_email = email.replace("ratelimit.", "unknown.")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS + 1):
        with pytest.raises(HTTPException):
            login(_Form(other_email, "Wrong#Guess1"), db=db)
    assert login(_Form(email, "Correct#12345"), db=db)["access_token"]
