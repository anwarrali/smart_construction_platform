"""Step-up authentication: OTP challenges and the short-lived grants they produce.

Two separate records on purpose. The challenge is the *question* (a code that
was sent, how many times it has been answered wrongly, when it stops being
valid); the grant is the *answer's consequence* (this person proved possession
for this one operation, until this moment). Keeping them apart is what lets a
grant expire on its own schedule without resurrecting a spent code, and lets a
challenge be invalidated by a resend without touching an already-earned grant.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class OtpChallenge(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        # The hot lookup: "the active challenge for this user and purpose".
        Index("ix_otp_challenges_user_purpose", "user_id", "purpose", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The single operation this code may authorize. A code minted for
    #: `security.change_password` must never satisfy `admin.change_user_role`,
    #: so the purpose is part of the challenge's identity, not a hint.
    purpose: Mapped[str] = mapped_column(String(60), nullable=False)
    #: HMAC-SHA256 of the code under the server secret — never the code itself.
    #: A plain digest would be pointless here: a six-digit space is a million
    #: candidates, which is a fraction of a second to enumerate offline from a
    #: database dump. Keying the digest with a secret the dump does not contain
    #: is what actually protects it.
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    #: Set the moment a correct code is accepted. Its presence is what makes
    #: the code single-use: replay is rejected on this field, not on expiry.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Set when a resend supersedes this challenge, or when it is locked after
    #: too many wrong answers. Distinct from `consumed_at` so the audit trail
    #: can tell "used correctly" from "abandoned" from "locked out".
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: How the code reached the user, for the audit trail. Never the address.
    delivery_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="EMAIL", server_default="EMAIL")

    user: Mapped["User"] = relationship(foreign_keys=[user_id])

    def is_open(self, now: datetime) -> bool:
        """Whether this challenge can still accept an answer."""
        return (
            self.consumed_at is None
            and self.invalidated_at is None
            and self.attempts < self.max_attempts
            and self.expires_at > now
        )


class StepUpGrant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Proof that a user recently completed step-up for one specific purpose.

    Deliberately *not* a flag on the user and *not* an extension of the login
    session: it names one purpose, it expires on its own short clock, and it
    is consumed by the operation it authorized.
    """

    __tablename__ = "step_up_grants"
    __table_args__ = (
        Index("ix_step_up_grants_user_purpose", "user_id", "purpose", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(60), nullable=False)
    challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("otp_challenges.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set when the protected operation actually runs, so one verification
    #: authorizes one action rather than every action inside the window.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])

    def is_valid(self, now: datetime) -> bool:
        return self.consumed_at is None and self.expires_at > now
