"""Rate-limit counters shared across API workers."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class RateLimitHit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rate_limit_hits"
    __table_args__ = (
        # Every read filters on exactly this triple, ordered or counted by time.
        Index("ix_rate_limit_scope_key_created", "scope", "key", "created_at"),
    )

    #: What is being limited, e.g. "login", "otp_send", "otp_verify".
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Who/what it is limited for. Never a secret — an account identifier or
    #: a user id, never a password, token or OTP.
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
