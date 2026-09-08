"""Issuing, listing and revoking MCP client tokens.

The rules an MCP client token is issued under, in one place, so the API module
above it is request shape and nothing else.

## Three rules, and why each is here

**It is bound to one project.** The caller must already have access to that
project — the token cannot reach a project its owner cannot, and cannot reach
the *other* projects its owner can. Binding is the difference between "a
credential for this MCP server" and "a second password".

**It expires, always.** A lifetime is capped at `MCP_TOKEN_MAX_LIFETIME_DAYS`
and cannot be omitted. A credential with no end is one nobody gets round to
revoking, and the whole reason this is a database row rather than a long-lived
JWT is to keep taking one back cheap.

**Only its owner can mint one.** These endpoints authenticate with a session
token, never with a client token — which is automatic rather than checked,
because no route outside `api/mcp.py` consults this table at all. A client
token therefore cannot mint another, so a leaked one cannot be used to
manufacture a longer-lived replacement before anybody notices.

## The secret

Generated once, hashed with the same SHA-256 the platform uses for its other
opaque tokens, and returned exactly once in the response that created it.
Nothing stored can reconstruct it. `prefix` is the visible head — enough to
recognise a token in a list, useless for using one.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token
from app.models.mcp_token import (
    ALL_SCOPES, SCOPE_READ, TOKEN_PREFIX, McpClientToken,
)
from app.models.user import User

#: How much of the secret is stored in the clear. Long enough to be unique in
#: any one person's list, far too short to brute-force the rest.
PREFIX_LENGTH = len(TOKEN_PREFIX) + 8


class TokenError(Exception):
    """A token request that cannot be granted, in HTTP terms."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def normalise_scopes(requested) -> str:
    """Validate what was asked for and return it in storage form.

    `mcp:read` is added rather than demanded: a token that may propose but not
    read is a credential for nothing, and refusing the request over it would be
    pedantry aimed at a client that meant the obvious thing.

    An unknown scope is refused rather than dropped. Silently ignoring it would
    let a client believe it had asked for something it had not — and the next
    scope this platform adds would be one a stale client thinks it holds.
    """
    if requested is None:
        return SCOPE_READ
    if isinstance(requested, str):
        requested = requested.split()
    unknown = [item for item in requested if item not in ALL_SCOPES]
    if unknown:
        raise TokenError(400, f"Unknown scope: {', '.join(sorted(unknown))}")
    granted = set(requested) | {SCOPE_READ}
    # Stored in the order declared, so two equivalent scope sets are one string.
    return " ".join(scope for scope in ALL_SCOPES if scope in granted)


def _expiry(lifetime_days: int | None, now: datetime) -> datetime:
    days = settings.MCP_TOKEN_DEFAULT_LIFETIME_DAYS if lifetime_days is None else lifetime_days
    if days < 1:
        raise TokenError(400, "A token must be valid for at least one day")
    if days > settings.MCP_TOKEN_MAX_LIFETIME_DAYS:
        raise TokenError(
            400,
            f"A token may not be valid for more than "
            f"{settings.MCP_TOKEN_MAX_LIFETIME_DAYS} days",
        )
    return now + timedelta(days=days)


def live_tokens(db: Session, *, user_id: uuid.UUID, now: datetime | None = None):
    """This person's tokens that would still authenticate a request."""
    now = now or datetime.now(timezone.utc)
    return db.query(McpClientToken).filter(
        McpClientToken.user_id == user_id,
        McpClientToken.revoked_at.is_(None),
        McpClientToken.expires_at > now,
    )


def issue(
    db: Session,
    *,
    owner: User,
    project_id: uuid.UUID,
    name: str,
    scopes=None,
    lifetime_days: int | None = None,
    now: datetime | None = None,
) -> tuple[McpClientToken, str]:
    """Mint one token. Returns the row and the plaintext secret, once.

    The caller is responsible for having checked that `owner` can reach
    `project_id` — that check belongs with the request, which is where the
    project came from. Everything else is here.
    """
    now = now or datetime.now(timezone.utc)

    label = (name or "").strip()
    if not label:
        raise TokenError(400, "A token needs a name, so it can be recognised later")
    if len(label) > 120:
        raise TokenError(400, "That name is too long")

    granted = normalise_scopes(scopes)
    expires_at = _expiry(lifetime_days, now)

    if live_tokens(db, user_id=owner.id, now=now).count() >= settings.MCP_TOKENS_PER_USER_MAX:
        raise TokenError(
            409,
            f"You already hold {settings.MCP_TOKENS_PER_USER_MAX} live MCP tokens. "
            "Revoke one before issuing another.",
        )

    secret = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    row = McpClientToken(
        user_id=owner.id,
        project_id=project_id,
        name=label,
        token_hash=hash_token(secret),
        prefix=secret[:PREFIX_LENGTH],
        scopes=granted,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    return row, secret


def visible_tokens(db: Session, *, viewer: User, include_revoked: bool = False,
                   now: datetime | None = None):
    """The tokens this viewer may see: their own, or everyone's for an admin.

    An administrator sees all of them because revoking a compromised credential
    is not something that can wait for its owner to be reachable. They never see
    a secret — nobody does; the column does not exist.
    """
    from app.core.permissions import can_manage_all_users

    now = now or datetime.now(timezone.utc)
    query = db.query(McpClientToken)
    if not can_manage_all_users(viewer.role):
        query = query.filter(McpClientToken.user_id == viewer.id)
    if not include_revoked:
        query = query.filter(
            McpClientToken.revoked_at.is_(None),
            McpClientToken.expires_at > now,
        )
    return query.order_by(McpClientToken.created_at.desc())


def revoke(db: Session, row: McpClientToken, *, now: datetime | None = None) -> bool:
    """Take a token back. Idempotent; returns whether this call did it.

    The row stays. Deleting it would orphan the audit entry that recorded the
    token being issued, and a credential's history is the part worth keeping
    once the credential itself is dead.
    """
    if row.revoked_at is not None:
        return False
    row.revoked_at = now or datetime.now(timezone.utc)
    return True


def find_for_revocation(db: Session, *, viewer: User, token_id: uuid.UUID):
    """One token this viewer is allowed to revoke, or None.

    Deliberately answers None for both "no such token" and "not yours": the two
    are the same fact to anybody who should not be told the token exists.
    """
    from app.core.permissions import can_manage_all_users

    query = db.query(McpClientToken).filter(McpClientToken.id == token_id)
    if not can_manage_all_users(viewer.role):
        query = query.filter(McpClientToken.user_id == viewer.id)
    return query.first()


__all__ = [
    "PREFIX_LENGTH", "TokenError", "find_for_revocation", "issue",
    "live_tokens", "normalise_scopes", "revoke", "visible_tokens",
]
