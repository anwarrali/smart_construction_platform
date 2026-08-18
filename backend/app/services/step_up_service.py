"""Step-up authentication: the one place OTP challenges and grants are managed.

The design constraint that shapes everything here is that step-up must be an
*additional* condition, never a substitute for authorization. A valid code
proves possession of the account's inbox; it says nothing about whether the
account may perform the operation. Both questions are asked, separately, and
the permission question is asked first — see `require_step_up`.

Purposes are a closed registry rather than free-form strings so that a code
minted for one operation can never be presented for another: an unknown
purpose is rejected outright instead of quietly creating a new namespace.
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.step_up import OtpChallenge, StepUpGrant
from app.models.user import User
from app.services import rate_limit_service
from app.services.audit_service import record_audit
from app.services.email_service import send_step_up_code_email


@dataclass(frozen=True)
class StepUpPurpose:
    code: str
    #: Shown to the user so they know what they are approving.
    label: str
    #: Which catalogue permission (if any) the action itself also demands.
    #: Recorded here for documentation; the endpoint still enforces it. OTP
    #: never grants permission, so this is never used to *allow* anything.
    related_permission: str | None = None


#: Every operation that requires step-up. Adding one is a single entry here
#: plus the dependency on the endpoint — not a new branch in a policy `if`.
PURPOSES: dict[str, StepUpPurpose] = {
    purpose.code: purpose
    for purpose in (
        StepUpPurpose("security.change_password", "Change your password"),
        StepUpPurpose("admin.change_user_role", "Change a user's role", "platform.manage_users"),
        StepUpPurpose("admin.deactivate_user", "Deactivate a user", "platform.manage_users"),
        StepUpPurpose("admin.delete_user", "Permanently delete a user", "platform.manage_users"),
        StepUpPurpose("admin.reset_user_password", "Reset another user's password", "platform.manage_users"),
        StepUpPurpose("admin.change_permissions", "Change roles and permissions", "platform.manage_permissions"),
    )
}

SEND_SCOPE = "otp_send"
VERIFY_SCOPE = "otp_verify"


def resolve_purpose(code: str) -> StepUpPurpose:
    purpose = PURPOSES.get((code or "").strip())
    if not purpose:
        raise HTTPException(status_code=422, detail="Unknown step-up purpose")
    return purpose


def _hash_code(code: str) -> str:
    """Keyed digest of the code.

    HMAC rather than a bare hash: six digits is a million possibilities, so an
    unkeyed digest in a leaked database is recovered essentially instantly.
    The server secret is not in the database, so it is what makes the stored
    value useless on its own.
    """
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), sha256).hexdigest()


def _generate_code() -> str:
    """A cryptographically random numeric code of the configured length.

    `secrets.randbelow` over the whole range keeps every value equally likely;
    building it digit-by-digit from a non-CSPRNG, or trimming a UUID, would
    not.
    """
    upper = 10 ** settings.OTP_LENGTH
    return str(secrets.randbelow(upper)).zfill(settings.OTP_LENGTH)


def _rate_key(user_id: uuid.UUID, purpose: str) -> str:
    return f"{user_id}:{purpose}"


def active_challenge(db: Session, user_id: uuid.UUID, purpose: str,
                     now: datetime | None = None) -> OtpChallenge | None:
    now = now or datetime.now(timezone.utc)
    challenge = db.query(OtpChallenge).filter(
        OtpChallenge.user_id == user_id,
        OtpChallenge.purpose == purpose,
        OtpChallenge.consumed_at.is_(None),
        OtpChallenge.invalidated_at.is_(None),
    ).order_by(OtpChallenge.created_at.desc()).first()
    return challenge if challenge and challenge.is_open(now) else challenge


def request_challenge(db: Session, user: User, purpose_code: str,
                      now: datetime | None = None) -> tuple[OtpChallenge, str]:
    """Issue a fresh code, superseding any previous one for this user+purpose.

    Returns the challenge and the plaintext code. The plaintext is handed only
    to the delivery channel; it is never persisted, returned by the API, or
    written to a log or audit record.
    """
    now = now or datetime.now(timezone.utc)
    purpose = resolve_purpose(purpose_code)
    key = _rate_key(user.id, purpose.code)

    # Throttle before doing any work, so a flood costs an attacker a row read
    # rather than an email.
    since_last = rate_limit_service.seconds_since_last(db, scope=SEND_SCOPE, key=key, now=now)
    if since_last is not None and since_last < settings.OTP_RESEND_COOLDOWN_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {int(settings.OTP_RESEND_COOLDOWN_SECONDS - since_last) + 1}s before requesting another code",
        )
    window = settings.OTP_SEND_WINDOW_MINUTES * 60
    if rate_limit_service.count_recent(db, scope=SEND_SCOPE, key=key,
                                       window_seconds=window, now=now) >= settings.OTP_MAX_SENDS_PER_WINDOW:
        record_audit(db, actor_id=user.id, action="step_up_send_rate_limited",
                     entity_type="otp_challenge", details={"purpose": purpose.code})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification codes requested. Try again later.",
        )

    # Exactly one code is live at a time for a user+purpose: a resend retires
    # the previous challenge rather than adding a second valid answer.
    db.query(OtpChallenge).filter(
        OtpChallenge.user_id == user.id,
        OtpChallenge.purpose == purpose.code,
        OtpChallenge.consumed_at.is_(None),
        OtpChallenge.invalidated_at.is_(None),
    ).update({"invalidated_at": now, "invalidated_reason": "SUPERSEDED"}, synchronize_session=False)

    code = _generate_code()
    challenge = OtpChallenge(
        user_id=user.id,
        purpose=purpose.code,
        code_hash=_hash_code(code),
        expires_at=now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES),
        max_attempts=settings.OTP_MAX_VERIFY_ATTEMPTS,
        delivery_channel="EMAIL",
    )
    db.add(challenge)
    db.flush()
    rate_limit_service.record_hit(db, scope=SEND_SCOPE, key=key, now=now)
    # The audit trail records that a code was issued and for what — never the
    # code, and never the address it went to.
    record_audit(db, actor_id=user.id, action="step_up_challenge_created",
                 entity_type="otp_challenge", entity_id=challenge.id,
                 details={"purpose": purpose.code, "channel": "EMAIL",
                          "expiresAt": challenge.expires_at.isoformat()})
    return challenge, code


def deliver_challenge(user: User, purpose: StepUpPurpose, code: str, expires_minutes: int) -> bool:
    """Send the code over the one channel this platform actually has."""
    return send_step_up_code_email(
        to_email=user.email, full_name=user.full_name,
        action_label=purpose.label, code=code, expires_minutes=expires_minutes,
    )


def verify_challenge(db: Session, user: User, purpose_code: str, code: str,
                     now: datetime | None = None) -> StepUpGrant:
    """Check a submitted code and, on success, mint a short-lived grant.

    Every failure path is deliberately reported the same way ("invalid or
    expired"), so a caller cannot use the error text to learn whether a code
    was wrong, already used, or issued for a different purpose.
    """
    now = now or datetime.now(timezone.utc)
    purpose = resolve_purpose(purpose_code)
    key = _rate_key(user.id, purpose.code)
    generic = HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid or expired verification code")

    challenge = db.query(OtpChallenge).filter(
        OtpChallenge.user_id == user.id,
        OtpChallenge.purpose == purpose.code,
        OtpChallenge.consumed_at.is_(None),
        OtpChallenge.invalidated_at.is_(None),
    ).order_by(OtpChallenge.created_at.desc()).first()

    if not challenge:
        record_audit(db, actor_id=user.id, action="step_up_verification_failed",
                     entity_type="otp_challenge",
                     details={"purpose": purpose.code, "reason": "NO_ACTIVE_CHALLENGE"})
        raise generic

    if challenge.expires_at <= now:
        challenge.invalidated_at = now
        challenge.invalidated_reason = "EXPIRED"
        record_audit(db, actor_id=user.id, action="step_up_challenge_expired",
                     entity_type="otp_challenge", entity_id=challenge.id,
                     details={"purpose": purpose.code})
        raise generic

    if challenge.attempts >= challenge.max_attempts:
        challenge.invalidated_at = now
        challenge.invalidated_reason = "LOCKED"
        raise generic

    rate_limit_service.record_hit(db, scope=VERIFY_SCOPE, key=key, now=now)
    challenge.attempts += 1

    # Constant-time comparison: a short-circuiting `==` on the digest leaks
    # how much of it matched through timing.
    if not hmac.compare_digest(challenge.code_hash, _hash_code(code or "")):
        locked = challenge.attempts >= challenge.max_attempts
        if locked:
            challenge.invalidated_at = now
            challenge.invalidated_reason = "LOCKED"
        db.flush()
        record_audit(
            db, actor_id=user.id,
            action="step_up_challenge_locked" if locked else "step_up_verification_failed",
            entity_type="otp_challenge", entity_id=challenge.id,
            # Attempt counts are safe to record; the submitted value is not.
            details={"purpose": purpose.code, "attempts": challenge.attempts,
                     "maxAttempts": challenge.max_attempts},
        )
        raise generic

    challenge.consumed_at = now
    grant = StepUpGrant(
        user_id=user.id, purpose=purpose.code, challenge_id=challenge.id,
        expires_at=now + timedelta(minutes=settings.STEP_UP_VALIDITY_MINUTES),
    )
    db.add(grant)
    db.flush()
    # A clean verification clears the throttle so an honest user who fumbled
    # the first code is not left rate-limited afterwards.
    rate_limit_service.clear(db, scope=VERIFY_SCOPE, key=key)
    record_audit(db, actor_id=user.id, action="step_up_verification_succeeded",
                 entity_type="otp_challenge", entity_id=challenge.id,
                 details={"purpose": purpose.code, "grantExpiresAt": grant.expires_at.isoformat()})
    return grant


def consume_grant(db: Session, user: User, purpose_code: str,
                  now: datetime | None = None) -> StepUpGrant | None:
    """Spend a valid grant for this purpose, or return None if there is none.

    Consuming rather than merely checking is what keeps one verification tied
    to one action: a second attempt inside the same window must verify again.
    """
    now = now or datetime.now(timezone.utc)
    grant = db.query(StepUpGrant).filter(
        StepUpGrant.user_id == user.id,
        StepUpGrant.purpose == purpose_code,
        StepUpGrant.consumed_at.is_(None),
        StepUpGrant.expires_at > now,
    ).order_by(StepUpGrant.created_at.desc()).first()
    if not grant:
        return None
    grant.consumed_at = now
    db.flush()
    return grant


def require_step_up(db: Session, user: User, purpose_code: str,
                    now: datetime | None = None) -> None:
    """Gate a sensitive operation. Raises 401 with a machine-readable marker.

    Call this *after* the endpoint's normal permission check. Step-up is an
    extra condition layered on top of authorization, never a way around it:
    a user who lacks the permission is refused before a code is ever relevant.
    """
    purpose = resolve_purpose(purpose_code)
    if consume_grant(db, user, purpose.code, now=now) is None:
        record_audit(db, actor_id=user.id, action="step_up_required_denied",
                     entity_type="step_up", details={"purpose": purpose.code})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # The frontend keys off this code to open the verification dialog;
            # the header keeps it visible to non-JSON clients too.
            detail={"code": "STEP_UP_REQUIRED", "purpose": purpose.code,
                    "label": purpose.label},
            headers={"X-Step-Up-Required": purpose.code},
        )
    record_audit(db, actor_id=user.id, action="step_up_action_authorized",
                 entity_type="step_up", details={"purpose": purpose.code})
