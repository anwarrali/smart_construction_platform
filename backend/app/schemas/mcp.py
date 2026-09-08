"""Wire shapes for MCP client tokens.

There is deliberately **no field anywhere in this module that carries a stored
secret**. `McpTokenCreated` returns the plaintext once, at the moment it is
generated and before it is anywhere in the database; every other model here
describes a token the server can no longer produce, because only its SHA-256
was kept. The absence is structural — a listing model with no such field
cannot leak one however the service layer changes, which is the same reasoning
`schemas/rag.py` applies to embeddings.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class McpTokenCreate(CamelModel):
    """What a client asks for when it wants a credential."""

    #: Shown in the listing, so a token can be revoked by the machine it lives
    #: on rather than by guessing which of five is the laptop's.
    name: str = Field(min_length=1, max_length=120)
    #: The single project this token may reach. Required — a token that is not
    #: bound to one carries its owner's authority over all of theirs.
    project_id: UUID
    #: Subset of `mcp:read` / `mcp:propose`. `mcp:read` is implied; omitting
    #: `mcp:propose` is how a client is given a credential that can answer
    #: questions but cannot suggest changes.
    scopes: Optional[List[str]] = None
    #: Capped by `MCP_TOKEN_MAX_LIFETIME_DAYS`. Defaults to
    #: `MCP_TOKEN_DEFAULT_LIFETIME_DAYS` when omitted; never unbounded.
    lifetime_days: Optional[int] = Field(default=None, ge=1, le=3650)


class McpTokenOut(CamelModel):
    """One token, as everybody sees it after the moment it was created."""

    id: UUID
    name: str
    project_id: UUID
    #: The displayable head of the secret, e.g. `cpmcp_A1b2C3d4`. Enough to
    #: tell two tokens apart, useless for using one.
    prefix: str
    scopes: List[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    #: Neither revoked nor expired — the one question a person reading this
    #: list is actually asking, answered here rather than left to the client to
    #: recompute from two timestamps and a clock it may not share.
    active: bool = True
    #: Whose token. Present because an administrator's listing spans people.
    owner_id: UUID
    owner_name: Optional[str] = None


class McpTokenCreated(CamelModel):
    """The one response that carries a secret, and says so.

    Two fields rather than one flat object: a client that logs the whole
    response should at least have had to reach past a field called `token`.
    """

    token: str
    #: The stored record, identical to what the listing will show from now on.
    record: McpTokenOut
    #: Repeated in the payload rather than left to documentation, because the
    #: client that most needs to hear it is a script.
    warning: str = (
        "This is the only time the token is shown. Store it in the MCP "
        "client's configuration now; the server keeps only a hash and cannot "
        "show it again."
    )
