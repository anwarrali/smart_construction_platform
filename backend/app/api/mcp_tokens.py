"""Managing MCP client tokens. Request shape only.

Three routes — mint, list, revoke — over `services/mcp/tokens.py`, which holds
every rule about what may be issued. This module reads a request, checks the
one thing that belongs with the request rather than with the token (does the
caller have access to the project it is being bound to?), and shapes a
response.

## Why these routes are not on the MCP surface

They authenticate with `get_current_user`, which means a **session token and
nothing else**. That is not a check written here — it falls out of the design:
`credentials.from_client_token` is only reachable from `api/mcp.py`, so no
client token can authenticate any route in this file.

The consequence is the one that matters. A leaked MCP token cannot mint itself
a replacement, cannot extend its own life, and cannot see or revoke its
sibling. Whoever holds it has one project, one scope set, and a clock running
down; recovering from a leak is revoking a row, not rotating an account.

## Who sees what

Everybody sees their own tokens. An administrator sees everybody's, because
revoking a compromised credential cannot wait for its owner to be reachable —
`services/mcp/tokens.py` decides that, through the same
`can_manage_all_users` the rest of the platform uses. Nobody, at any level,
sees a secret: the column does not exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.mcp import require_mcp_enabled
from app.core.deps import get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.mcp_token import McpClientToken
from app.models.user import User
from app.schemas.mcp import McpTokenCreate, McpTokenCreated, McpTokenOut
from app.services.audit_service import record_audit
from app.services.mcp import tokens as token_service
from app.services.mcp.tokens import TokenError

router = APIRouter(prefix="/mcp/tokens", tags=["MCP"])


def _out(row: McpClientToken, now: datetime | None = None) -> McpTokenOut:
    owner = row.user
    return McpTokenOut(
        id=row.id,
        name=row.name,
        project_id=row.project_id,
        prefix=row.prefix,
        scopes=sorted(row.scope_set),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        active=row.is_usable(now or datetime.now(timezone.utc)),
        owner_id=row.user_id,
        owner_name=getattr(owner, "full_name", None),
    )


@router.post("", response_model=McpTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    payload: McpTokenCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mint one token for one project, and return the secret exactly once.

    Project access is checked here rather than in the service because it is a
    fact about the request: the project id arrived in the body, and a caller
    who cannot reach that project must not be able to learn whether it exists.
    403 for both cases, for that reason.

    The token never grants more than this check confirms *and* less besides —
    authority is resolved from the user at the moment of every call, so a
    permission lost tomorrow is lost to this token tomorrow.
    """
    require_mcp_enabled()

    if not user_has_project_access(db, current_user, payload.project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project",
        )

    try:
        row, secret = token_service.issue(
            db,
            owner=current_user,
            project_id=payload.project_id,
            name=payload.name,
            scopes=payload.scopes,
            lifetime_days=payload.lifetime_days,
        )
    except TokenError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    record_audit(
        db, actor_id=current_user.id, action="mcp_token_created",
        entity_type="mcp_client_token", entity_id=row.id,
        project_id=payload.project_id,
        # The prefix, not the secret, and not the hash either: an audit row is
        # read by people, and neither of the other two would tell them
        # anything the prefix does not.
        details={"prefix": row.prefix, "scopes": row.scopes,
                 "expiresAt": row.expires_at.isoformat()},
    )
    db.commit()
    db.refresh(row)

    return McpTokenCreated(token=secret, record=_out(row))


@router.get("", response_model=list[McpTokenOut])
def list_tokens(
    include_revoked: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The caller's tokens — or everybody's, for an administrator.

    Revoked and expired ones are hidden unless asked for. They are the answer
    to "what happened to the token that stopped working", which is worth being
    able to ask and not worth showing by default.
    """
    require_mcp_enabled()
    now = datetime.now(timezone.utc)
    rows = token_service.visible_tokens(
        db, viewer=current_user, include_revoked=include_revoked, now=now,
    ).all()
    return [_out(row, now) for row in rows]


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke one token. Effective on its next request, which is the point.

    Deliberately **not** gated on `MCP_ENABLED`. Every other route here is —
    issuing credentials for a surface nothing can reach is pointless — but
    taking one back must work whatever the switch says, including immediately
    after an operator has turned the surface off in a hurry.

    404 for a token that does not exist and for one that is not the caller's:
    the two are the same fact to anybody who should not be told it exists.
    """
    row = token_service.find_for_revocation(db, viewer=current_user, token_id=token_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if token_service.revoke(db, row):
        record_audit(
            db, actor_id=current_user.id, action="mcp_token_revoked",
            entity_type="mcp_client_token", entity_id=row.id,
            project_id=row.project_id,
            # Recorded when an administrator revokes somebody else's, which is
            # the case the trail exists for.
            details={"prefix": row.prefix, "ownerId": str(row.user_id)},
        )
        db.commit()
    return None
