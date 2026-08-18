"""Step-up verification endpoints.

Only two operations are exposed: ask for a code, and answer it. Neither ever
returns the code (except under an explicitly enabled development flag), and
the response shape is identical whether or not delivery actually succeeded, so
the API cannot be used to probe which addresses exist or are reachable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.step_up import (
    StepUpChallengeOut, StepUpPurposeOut, StepUpRequest,
    StepUpVerifyRequest, StepUpVerifyOut,
)
from app.services import step_up_service
from app.services.notification_service import (
    CATEGORY_DIRECT, PRIORITY_IMPORTANT, notify,
)

router = APIRouter(prefix="/auth/step-up", tags=["Step-up Authentication"])


@router.get("/purposes", response_model=list[StepUpPurposeOut])
def list_purposes(current_user: User = Depends(get_current_user)):
    """The operations that require verification, for the client's labels."""
    return [
        {"code": item.code, "label": item.label}
        for item in step_up_service.PURPOSES.values()
    ]


@router.post("/request", response_model=StepUpChallengeOut, status_code=201)
def request_code(
    data: StepUpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue (or re-issue) a code for one sensitive operation.

    A resend goes through this same path, which is what guarantees the
    previous code stops working: `request_challenge` invalidates it.
    """
    purpose = step_up_service.resolve_purpose(data.purpose)
    challenge, code = step_up_service.request_challenge(db, current_user, purpose.code)
    delivered = step_up_service.deliver_challenge(
        current_user, purpose, code, settings.OTP_EXPIRE_MINUTES,
    )
    # The in-app notification tells the user a code was requested — it never
    # carries the code itself, which would defeat the point of a second
    # channel for anyone who already has the session open.
    notify(
        db, user_id=current_user.id,
        title="Verification code requested",
        message=f"A verification code was requested to confirm: {purpose.label}. "
                f"If this was not you, change your password immediately.",
        category=CATEGORY_DIRECT, priority=PRIORITY_IMPORTANT,
        entity_type="STEP_UP", entity_id=challenge.id,
        message_key="stepUp.codeRequested",
        message_params={"action": purpose.label},
    )
    db.commit()

    payload = {
        "purpose": purpose.code,
        "label": purpose.label,
        "expiresAt": challenge.expires_at,
        "maxAttempts": challenge.max_attempts,
        "resendAfterSeconds": settings.OTP_RESEND_COOLDOWN_SECONDS,
        # Reported so the UI can be honest when SMTP is not configured in a
        # development environment, without revealing anything about the address.
        "delivered": delivered,
    }
    if settings.OTP_DEV_ECHO_ENABLED:
        # Development convenience only, off by default and validated as such
        # by test_step_up_security.py. Never enable outside local work.
        payload["devCode"] = code
    return payload


@router.post("/verify", response_model=StepUpVerifyOut)
def verify_code(
    data: StepUpVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a challenge. Success mints a short-lived, purpose-bound grant."""
    grant = step_up_service.verify_challenge(
        db, current_user, data.purpose, data.code,
    )
    expires_at = grant.expires_at
    db.commit()
    return {"purpose": data.purpose, "verified": True, "expiresAt": expires_at}
