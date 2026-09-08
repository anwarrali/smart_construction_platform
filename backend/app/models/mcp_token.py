"""Long-lived, project-scoped credentials for MCP clients.

## Why this table exists rather than a longer-lived JWT

An MCP client is a desktop application that runs for weeks. The platform's
access token lives for minutes and cannot be refreshed by a client that has no
browser, so the only ways to make one work are to hand the client a refresh
token — which is the user's whole account — or to mint an access token with a
90-day expiry. The second is worse than it looks: a JWT is valid because it is
signed, so revoking one means keeping it in `revoked_tokens` until it expires,
and a credential that cannot be *promptly* taken back is not a credential worth
issuing.

A row is the opposite: authority is looked up on every call, so revoking is one
UPDATE and takes effect on the next request. That is the whole argument.

## What one of these can do, and what it cannot

It is **never** more than its owner. Every call still runs through
`ai_tools.call_tool` as that user, against the same permissions, so a token
held by someone who loses a permission loses it too, at the same moment. The
row only ever *subtracts*:

  * **one project** — `project_id` is not nullable, and the MCP endpoint
    refuses the token on any other project's URL;
  * **one surface** — no other route in the platform consults this table, so
    the token cannot be used against the REST API even though it is a bearer
    token;
  * **a scope** — a token without `mcp:propose` cannot reach a PROPOSE tool,
    and is not shown one.

Only the SHA-256 of the secret is stored, so the plaintext exists exactly once,
in the response that created it. `prefix` is the part shown afterwards, so a
person can tell two tokens apart in a list without the server keeping anything
that would let it impersonate them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

#: Every secret starts with this, which is how the MCP endpoint tells one of
#: these from a JWT without trying to decode it first.
TOKEN_PREFIX = "cpmcp_"

#: Read the project: list tools and call READ tools. Every token holds it —
#: a token that can propose but not read would be a credential for nothing.
SCOPE_READ = "mcp:read"
#: Reach PROPOSE tools. Optional, and off unless asked for: a proposal is an
#: AI suggesting a change to somebody's project, and a client that only needs
#: to answer questions should not be able to make one.
SCOPE_PROPOSE = "mcp:propose"

ALL_SCOPES = (SCOPE_READ, SCOPE_PROPOSE)


class McpClientToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "mcp_client_tokens"
    __table_args__ = (
        # The lookup on every single MCP request.
        Index("ix_mcp_client_tokens_hash", "token_hash", unique=True),
        # The listing, which is always "this person's tokens, newest first".
        Index("ix_mcp_client_tokens_user", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    #: Not nullable on purpose. A token that is not bound to a project would
    #: carry the owner's authority over every project they can reach, which is
    #: the thing a scoped credential exists to avoid.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
    )
    #: What the person called it — "Claude Desktop, work laptop". Shown in the
    #: listing so a token can be revoked by the machine it lives on.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: SHA-256 of the secret. Never the secret.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The displayable head of the secret, e.g. `cpmcp_A1b2C3d4`. Enough to
    #: identify a token, useless for using one.
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    #: Space-separated, OAuth-style. Always a subset of `ALL_SCOPES`.
    scopes: Mapped[str] = mapped_column(String(200), nullable=False, default=SCOPE_READ)
    #: Always set. A credential with no end is one nobody ever gets round to
    #: revoking.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Written at most once a minute, not once a request — see
    #: `services/mcp/credentials.py`. Its job is to let a person tell a live
    #: token from a forgotten one, which a minute's resolution answers.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    #: Set instead of deleting the row, so the audit trail keeps pointing at
    #: something.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    user = relationship("User", lazy="joined")

    @property
    def scope_set(self) -> frozenset[str]:
        return frozenset(self.scopes.split())

    def is_usable(self, now: datetime | None = None) -> bool:
        """Revoked or expired is not usable. The caller reports which."""
        now = now or datetime.now(timezone.utc)
        return self.revoked_at is None and not self.is_expired(now)

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        stamp = self.expires_at
        if stamp is not None and stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp is not None and stamp <= now
