"""Step-up authentication and OTP security.

The properties under test are the ones an attacker would probe: can a code be
replayed, reused across purposes, used by another account, brute-forced, or
recovered from the database or the audit trail — and can step-up ever be
mistaken for authorization.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import UserRole, UserStatus
from app.models.step_up import OtpChallenge, StepUpGrant
from app.models.user import User
from app.services import rate_limit_service, step_up_service
from app.services.step_up_service import (
    consume_grant, request_challenge, require_step_up, verify_challenge,
)


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
    suffix = uuid4().hex[:10]

    def user(name, role):
        person = User(full_name=name, email=f"{name.lower()}.{suffix}@constro.io",
                      hashed_password=hash_password("Correct#12345"),
                      role=role, status=UserStatus.ACTIVE)
        db.add(person)
        return person

    made = {
        "admin": user("SuAdmin", UserRole.ADMIN),
        "engineer": user("SuEngineer", UserRole.ENGINEER),
        "other": user("SuOther", UserRole.ADMIN),
    }
    db.flush()
    made["db"] = db
    yield made
    ids = [p.id for p in made.values() if isinstance(p, User)]
    db.rollback()
    for statement in (
        "DELETE FROM step_up_grants WHERE user_id = ANY(:users)",
        "DELETE FROM otp_challenges WHERE user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE actor_id = ANY(:users)",
        "DELETE FROM notifications WHERE user_id = ANY(:users)",
        "DELETE FROM rate_limit_hits WHERE key LIKE ANY(:keys)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        db.execute(text(statement), {"users": ids, "keys": [f"{i}%" for i in ids] or ["%"]})
    db.commit()


PURPOSE = "security.change_password"
OTHER_PURPOSE = "admin.change_user_role"


def _fresh(db, user, purpose=PURPOSE, now=None):
    """Issue a challenge, bypassing the resend cooldown between tests."""
    rate_limit_service.clear(db, scope=step_up_service.SEND_SCOPE,
                             key=f"{user.id}:{purpose}")
    return request_challenge(db, user, purpose, now=now)


# --- generation --------------------------------------------------------------

def test_the_code_has_the_configured_length_and_is_numeric(db, people):
    _, code = _fresh(db, people["admin"])
    assert len(code) == settings.OTP_LENGTH and code.isdigit()


def test_generated_codes_are_not_predictable(db, people):
    """A weak generator would repeat quickly across a small sample."""
    codes = set()
    for index in range(25):
        _, code = _fresh(db, people["admin"], now=datetime.now(timezone.utc) + timedelta(hours=index))
        codes.add(code)
    assert len(codes) > 20, "codes repeat far more than chance would explain"


def test_the_plaintext_code_is_never_stored(db, people):
    challenge, code = _fresh(db, people["admin"])
    assert challenge.code_hash != code
    assert code not in challenge.code_hash
    # And the stored digest is keyed, so a database dump alone cannot reverse
    # a six-digit space by brute force.
    from hashlib import sha256
    assert challenge.code_hash != sha256(code.encode()).hexdigest()


# --- verification ------------------------------------------------------------

def test_the_correct_code_verifies_and_grants_step_up(db, people):
    _, code = _fresh(db, people["admin"])
    grant = verify_challenge(db, people["admin"], PURPOSE, code)
    assert grant.purpose == PURPOSE and grant.consumed_at is None
    assert grant.expires_at > datetime.now(timezone.utc)


def test_a_wrong_code_is_rejected(db, people):
    challenge, code = _fresh(db, people["admin"])
    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(HTTPException) as error:
        verify_challenge(db, people["admin"], PURPOSE, wrong)
    assert error.value.status_code == 400
    db.refresh(challenge)
    assert challenge.attempts == 1 and challenge.consumed_at is None


def test_an_expired_code_is_rejected(db, people):
    challenge, code = _fresh(db, people["admin"])
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    with pytest.raises(HTTPException):
        verify_challenge(db, people["admin"], PURPOSE, code)


def test_a_code_cannot_be_replayed(db, people):
    """Scenario E: first use succeeds, the second must not."""
    _, code = _fresh(db, people["admin"])
    verify_challenge(db, people["admin"], PURPOSE, code)
    with pytest.raises(HTTPException):
        verify_challenge(db, people["admin"], PURPOSE, code)


def test_a_code_from_another_purpose_cannot_be_used(db, people):
    """Scenario F: purpose binding."""
    _, code = _fresh(db, people["admin"], purpose=PURPOSE)
    with pytest.raises(HTTPException):
        verify_challenge(db, people["admin"], OTHER_PURPOSE, code)


def test_a_code_issued_to_another_user_cannot_be_used(db, people):
    _, code = _fresh(db, people["admin"])
    with pytest.raises(HTTPException):
        verify_challenge(db, people["other"], PURPOSE, code)


def test_every_failure_reports_the_same_message(db, people):
    """Distinguishable errors would tell an attacker which guess was closer."""
    messages = set()
    challenge, code = _fresh(db, people["admin"])
    wrong = "000000" if code != "000000" else "111111"
    try:
        verify_challenge(db, people["admin"], PURPOSE, wrong)
    except HTTPException as error:
        messages.add(error.detail)
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    try:
        verify_challenge(db, people["admin"], PURPOSE, code)
    except HTTPException as error:
        messages.add(error.detail)
    try:
        verify_challenge(db, people["other"], PURPOSE, code)
    except HTTPException as error:
        messages.add(error.detail)
    assert len(messages) == 1


# --- attempts and lockout ----------------------------------------------------

def test_the_challenge_locks_after_the_configured_attempts(db, people):
    challenge, code = _fresh(db, people["admin"])
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(settings.OTP_MAX_VERIFY_ATTEMPTS):
        with pytest.raises(HTTPException):
            verify_challenge(db, people["admin"], PURPOSE, wrong)
    db.refresh(challenge)
    assert challenge.invalidated_reason == "LOCKED"
    # Even the genuine code is worthless once the challenge is locked.
    with pytest.raises(HTTPException):
        verify_challenge(db, people["admin"], PURPOSE, code)


# --- resend ------------------------------------------------------------------

def test_a_resend_invalidates_the_previous_code(db, people):
    """Scenario H: resending must not leave two working codes."""
    first_challenge, first_code = _fresh(db, people["admin"])
    _, second_code = _fresh(db, people["admin"])
    assert first_code != second_code
    db.refresh(first_challenge)
    assert first_challenge.invalidated_reason == "SUPERSEDED"
    with pytest.raises(HTTPException):
        verify_challenge(db, people["admin"], PURPOSE, first_code)
    assert verify_challenge(db, people["admin"], PURPOSE, second_code) is not None


def test_resending_too_quickly_is_refused(db, people):
    request_challenge(db, people["admin"], PURPOSE)
    with pytest.raises(HTTPException) as error:
        request_challenge(db, people["admin"], PURPOSE)
    assert error.value.status_code == 429


def test_too_many_sends_in_the_window_are_refused(db, people):
    """Scenario I: the cooldown alone must not allow unlimited codes."""
    now = datetime.now(timezone.utc)
    for index in range(settings.OTP_MAX_SENDS_PER_WINDOW):
        # Spaced past the cooldown but inside the window.
        request_challenge(db, people["admin"], PURPOSE,
                          now=now + timedelta(seconds=index * (settings.OTP_RESEND_COOLDOWN_SECONDS + 5)))
    with pytest.raises(HTTPException) as error:
        request_challenge(db, people["admin"], PURPOSE,
                          now=now + timedelta(seconds=settings.OTP_MAX_SENDS_PER_WINDOW * (settings.OTP_RESEND_COOLDOWN_SECONDS + 5)))
    assert error.value.status_code == 429


# --- grants ------------------------------------------------------------------

def test_a_sensitive_action_without_step_up_is_denied(db, people):
    with pytest.raises(HTTPException) as error:
        require_step_up(db, people["admin"], PURPOSE)
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "STEP_UP_REQUIRED"


def test_a_sensitive_action_with_a_valid_grant_is_allowed(db, people):
    _, code = _fresh(db, people["admin"])
    verify_challenge(db, people["admin"], PURPOSE, code)
    require_step_up(db, people["admin"], PURPOSE)  # must not raise


def test_a_grant_authorizes_one_action_only(db, people):
    """The grant is consumed, so a second protected call re-challenges."""
    _, code = _fresh(db, people["admin"])
    verify_challenge(db, people["admin"], PURPOSE, code)
    require_step_up(db, people["admin"], PURPOSE)
    with pytest.raises(HTTPException):
        require_step_up(db, people["admin"], PURPOSE)


def test_a_grant_for_one_purpose_does_not_authorize_another(db, people):
    _, code = _fresh(db, people["admin"], purpose=PURPOSE)
    verify_challenge(db, people["admin"], PURPOSE, code)
    with pytest.raises(HTTPException):
        require_step_up(db, people["admin"], OTHER_PURPOSE)


def test_a_grant_expires(db, people):
    _, code = _fresh(db, people["admin"])
    grant = verify_challenge(db, people["admin"], PURPOSE, code)
    later = grant.expires_at + timedelta(seconds=1)
    assert consume_grant(db, people["admin"], PURPOSE, now=later) is None


def test_a_grant_belongs_to_one_user(db, people):
    _, code = _fresh(db, people["admin"])
    verify_challenge(db, people["admin"], PURPOSE, code)
    with pytest.raises(HTTPException):
        require_step_up(db, people["other"], PURPOSE)


def test_an_unknown_purpose_is_rejected(db, people):
    with pytest.raises(HTTPException) as error:
        request_challenge(db, people["admin"], "totally.made.up")
    assert error.value.status_code == 422


# --- authorization is independent of step-up (Phase 20) ----------------------

def test_step_up_does_not_grant_permission(db, people):
    """A verified non-admin still cannot perform an admin-only action.

    This is the property that keeps OTP from becoming a privilege escalation:
    the endpoint's permission dependency runs regardless of any grant.
    """
    from app.services.authorization import has_permission
    _, code = _fresh(db, people["engineer"], purpose=OTHER_PURPOSE)
    verify_challenge(db, people["engineer"], OTHER_PURPOSE, code)
    # The grant exists and is valid...
    assert consume_grant(db, people["engineer"], OTHER_PURPOSE) is not None
    # ...and confers no authority whatsoever.
    assert not has_permission(db, people["engineer"], "platform.manage_users")


def test_a_deactivated_user_holds_no_permissions_even_with_a_grant(db, people):
    _, code = _fresh(db, people["admin"])
    verify_challenge(db, people["admin"], PURPOSE, code)
    people["admin"].status = UserStatus.INACTIVE
    db.flush()
    from app.services.authorization import effective_permissions
    assert effective_permissions(db, people["admin"]) == set()


# --- secret hygiene ----------------------------------------------------------

def test_the_code_never_appears_in_the_audit_trail(db, people):
    challenge, code = _fresh(db, people["admin"])
    wrong = "000000" if code != "000000" else "111111"
    try:
        verify_challenge(db, people["admin"], PURPOSE, wrong)
    except HTTPException:
        pass
    verify_challenge(db, people["admin"], PURPOSE, code)
    db.flush()
    entries = db.query(AuditLog).filter(AuditLog.actor_id == people["admin"].id).all()
    assert entries, "the flow must be audited at all"
    for entry in entries:
        blob = f"{entry.action} {entry.details or ''}"
        assert code not in blob
        assert wrong not in blob
        assert challenge.code_hash not in blob


def test_the_audit_trail_records_the_security_events(db, people):
    _, code = _fresh(db, people["admin"])
    wrong = "000000" if code != "000000" else "111111"
    try:
        verify_challenge(db, people["admin"], PURPOSE, wrong)
    except HTTPException:
        pass
    verify_challenge(db, people["admin"], PURPOSE, code)
    require_step_up(db, people["admin"], PURPOSE)
    db.flush()
    actions = {entry.action for entry in
               db.query(AuditLog).filter(AuditLog.actor_id == people["admin"].id).all()}
    assert {"step_up_challenge_created", "step_up_verification_failed",
            "step_up_verification_succeeded", "step_up_action_authorized"} <= actions


def test_rate_limit_keys_never_contain_a_secret(db, people):
    _fresh(db, people["admin"])
    from app.models.rate_limit import RateLimitHit
    for hit in db.query(RateLimitHit).all():
        assert "Correct#12345" not in hit.key
        assert len(hit.key) < 200


def test_the_development_code_echo_is_disabled_by_default():
    """A production deployment must never hand the code back over the API."""
    assert settings.OTP_DEV_ECHO_ENABLED is False


# --- authorization enforced over real HTTP (Phase 20) ------------------------
#
# The resolver-level test above proves a grant confers no permission. This one
# proves the *endpoint* refuses too, through the real FastAPI stack with its
# dependencies active — the distinction matters, because calling an endpoint
# function directly bypasses `Depends(require_permission(...))` entirely and
# would make an unprotected endpoint look protected.

def test_a_valid_grant_does_not_let_a_non_admin_deactivate_a_user(db, people):
    from fastapi.testclient import TestClient
    from app.main import app

    engineer, victim = people["engineer"], people["other"]
    victim.role = UserRole.ENGINEER
    db.add(StepUpGrant(
        user_id=engineer.id, purpose="admin.deactivate_user",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    ))
    db.commit()

    client = TestClient(app)
    login = client.post("/api/v1/auth/login",
                        data={"username": engineer.email, "password": "Correct#12345"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.put(f"/api/v1/users/{victim.id}/deactivate", headers=headers)
    assert response.status_code == 403

    db.refresh(victim)
    assert victim.status == UserStatus.ACTIVE, "the target must be untouched"


def test_the_step_up_endpoints_never_return_the_code(db, people):
    """The API must not hand back what it just emailed."""
    from fastapi.testclient import TestClient
    from app.main import app

    admin = people["admin"]
    db.commit()
    client = TestClient(app)
    login = client.post("/api/v1/auth/login",
                        data={"username": admin.email, "password": "Correct#12345"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post("/api/v1/auth/step-up/request",
                           json={"purpose": PURPOSE}, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body.get("devCode") is None, "the development echo must be off by default"

    stored = db.query(OtpChallenge).filter(
        OtpChallenge.user_id == admin.id, OtpChallenge.purpose == PURPOSE,
    ).order_by(OtpChallenge.created_at.desc()).first()
    # Nothing in the payload may reconstruct the code or its stored digest.
    assert stored.code_hash not in json.dumps(body)
