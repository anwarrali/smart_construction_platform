from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.user import CamelModel


class StepUpPurposeOut(CamelModel):
    code: str
    label: str


class StepUpRequest(CamelModel):
    purpose: str = Field(max_length=60)


class StepUpChallengeOut(CamelModel):
    """Everything the client needs to render the dialog — and nothing secret.

    There is no field here that reveals the code, the delivery address, or
    whether the account exists; the caller is already authenticated, so the
    challenge is always for themselves.
    """
    purpose: str
    label: str
    expires_at: datetime
    max_attempts: int
    resend_after_seconds: int
    delivered: bool
    #: Present only when OTP_DEV_ECHO_ENABLED is explicitly turned on, which
    #: it must never be outside local development.
    dev_code: Optional[str] = None


class StepUpVerifyRequest(CamelModel):
    purpose: str = Field(max_length=60)
    code: str = Field(min_length=4, max_length=12)


class StepUpVerifyOut(CamelModel):
    purpose: str
    verified: bool
    expires_at: datetime
