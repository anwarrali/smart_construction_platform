"""MCP over HTTP. Transport only.

One endpoint, one job: authenticate the request, decode JSON-RPC, hand it to
`services/mcp/protocol.py`, and encode what comes back. Every decision about
what a caller may do is made below this file, by the tool layer that already
makes it for the agent runtime.

## The shape of the URL

`POST /api/v1/mcp/projects/{project_id}` — one MCP server per project, rather
than one server with a `projectId` argument on every tool.

That is a security choice before it is an ergonomic one. With the project in
the path, `tools/list` can return *exactly* what this caller may do *here* —
`available_tools` filters the table by their permissions on that project — so
a model is never shown a capability it cannot use, and never learns that a
capability exists behind a permission it does not hold. A single global server
would have to list everything and refuse per call, which discloses the
catalogue to anyone with a token.

It also makes project isolation structural: there is no code path in this file
that reaches a project other than the one named in the URL.

## Streamable HTTP, statelessly

The MCP Streamable HTTP transport is JSON-RPC over POST, with an optional GET
for server-initiated messages and an optional session id. This server has
nothing to initiate — the tool table is a module constant and no tool streams —
so:

  * **POST** carries every request and returns a JSON response.
  * **GET** is answered 405, which the spec explicitly allows for a server that
    offers no server-to-client stream.
  * **No `Mcp-Session-Id`.** Every request already carries a JWT that resolves
    to a user, and the tool layer holds no per-session state. Issuing a session
    id would be inventing state to look conventional.

## Authentication

Two bearer credentials are accepted and both resolve to one `Credential`:

  * the platform's **session token**, through the same `get_current_user` every
    other route uses — so a revoked token, an inactive account or an expired
    session is refused here exactly as it is everywhere else;
  * an **MCP client token** (`cpmcp_…`), a row in `mcp_client_tokens` bound to
    one project and one scope set. It exists because a desktop MCP client runs
    for weeks and cannot refresh a minutes-long access token, and because the
    alternative — handing that client a refresh token — is handing it the
    account.

A client token is **only** understood here. No other route in the platform
consults that table, so it cannot be used against the REST API, and it cannot
mint another one: the token endpoints authenticate with a session. MCP's OAuth
profile is still not implemented; see `docs/MCP.md`.

## Rate limiting

`tools/call` is charged against the calling credential — per credential and not
per user, so a runaway desktop client cannot throttle the same person's browser
session. A batch costs one unit per `tools/call` it carries, because counting
requests would leave batching as a way straight through the limit. A request
that cannot afford all of its calls is refused whole, with `Retry-After`, and
spends nothing. `services/mcp/limits.py` holds the reasoning.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, oauth2_scheme, user_has_project_access
from app.db.database import get_db
from app.models.user import User
from app.services import mcp
from app.services.ai_tools.contracts import ToolKind
from app.services.ai_tools.registry import BY_NAME
from app.services.audit_service import record_audit
from app.services.mcp import credentials, limits
from app.services.mcp.credentials import Credential, CredentialError
from app.services.mcp.protocol import (
    INTERNAL_ERROR, INVALID_REQUEST, PARSE_ERROR, ProtocolError,
)

logger = logging.getLogger("uvicorn.error").getChild("mcp.api")

router = APIRouter(prefix="/mcp", tags=["MCP"])

#: The header the spec uses to pin a negotiated protocol version. Echoed back
#: so a client can confirm what it is talking to.
PROTOCOL_HEADER = "MCP-Protocol-Version"

#: Refuse a body larger than this before parsing it. A tool call is a name and
#: a small argument object; anything else is a mistake or an attack, and
#: `json.loads` on an unbounded body is the wrong place to find out.
MAX_BODY_BYTES = 256 * 1024


def require_mcp_enabled() -> None:
    """Refuse cleanly when MCP is switched off.

    503 rather than 404: the surface exists, this deployment has not enabled
    it, and a client should be able to tell those apart. Off by default —
    a new externally-reachable protocol is opt-in, the way `RAG_ENABLED` is.

    Shared with `api/mcp_tokens.py`, so a deployment with MCP off does not
    issue credentials for a surface nothing can reach.
    """
    if not settings.MCP_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The MCP tool surface is not enabled on this server",
        )


def mcp_credential(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Credential:
    """Resolve whichever of the two credentials arrived.

    Discriminated by prefix rather than by attempting a JWT decode and falling
    back on failure: a mistyped session token should be reported as a bad
    session, not as an unknown client token, and the two failures deserve
    different sentences.

    The session branch calls `get_current_user` as a plain function rather than
    reimplementing it, so a session reaching MCP is judged by exactly the code
    that judges it on every other route. The token branch cannot share that —
    a client token is not a JWT and has no denylist — so
    `credentials.from_client_token` repeats the *account* checks deliberately:
    a suspension must take effect on a month-old token immediately, not when
    the token happens to expire.
    """
    if credentials.looks_like_client_token(token):
        try:
            return credentials.from_client_token(db, token)
        except CredentialError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=error.detail,
                headers={"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None,
            ) from error
    return credentials.session_credential(
        get_current_user(request=request, token=token, db=db)
    )


@router.get("/projects/{project_id}")
def mcp_stream_not_supported(project_id: uuid.UUID):
    """No server-to-client stream exists, and the spec allows saying so.

    Answered explicitly rather than left to a 405 from the router, so a client
    that opens the optional GET stream gets a reason instead of a bare status.
    """
    require_mcp_enabled()
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail=(
            "This MCP server does not offer a server-to-client stream. "
            "Send JSON-RPC requests by POST to the same URL."
        ),
    )


@router.post("/projects/{project_id}")
async def mcp_endpoint(
    project_id: uuid.UUID,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    credential: Credential = Depends(mcp_credential),
):
    """One JSON-RPC message, or a batch of them.

    Two access checks stand here, and they answer different questions.
    `allows_project` asks whether *this credential* was issued for this
    project — a client token is bound to one, and its owner very likely has
    others. `user_has_project_access` asks whether the person may reach the
    project at all. Neither implies the other, and every tool goes on to check
    the second again through `call_tool` — not because this check is doubted,
    but because the tool layer is reachable from the agent runtime too and
    must not depend on its callers.
    """
    require_mcp_enabled()
    current_user = credential.user

    if not credential.allows_project(project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This MCP client token is issued for a different project",
        )

    if not user_has_project_access(db, current_user, project_id):
        # 403 and not 404: the caller authenticated, and telling them the
        # project is unreachable is the same information either way.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this project",
        )

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The request body is too large for a tool call",
        )

    response.headers[PROTOCOL_HEADER] = _negotiated_version(request)

    try:
        message = _decode(raw)
    except ProtocolError as error:
        return mcp.error_response(None, error.code, error.message)

    budget = _charge(db, credential, message)
    response.headers.update(budget.headers)

    # A batch is a JSON array. Supported because the spec allows it and a
    # client may pipeline `initialize` with its first real call; the responses
    # come back in order, and notifications contribute none.
    if isinstance(message, list):
        if not message:
            return mcp.error_response(None, INVALID_REQUEST, "An empty batch is not a request")
        replies = [
            reply for item in message
            if (reply := _dispatch(db, credential, project_id, item)) is not None
        ]
        # A batch of nothing but notifications gets 202 and no body, which is
        # what the spec requires.
        if not replies:
            return _accepted(response)
        return replies

    reply = _dispatch(db, credential, project_id, message)
    if reply is None:
        return _accepted(response)
    return reply


def _accepted(response: Response) -> Response:
    """202 with no body — and with the headers the request had earned.

    Returning a `Response` object bypasses the injected one entirely, so
    anything set on it up to this point is dropped. That is invisible for a
    plain `notifications/initialized`, and wrong for a `tools/call` sent as a
    notification: it costs a unit like any other call, so a client self-pacing
    on `X-RateLimit-Remaining` would be told nothing about what it just spent.
    """
    return Response(status_code=status.HTTP_202_ACCEPTED,
                    headers=dict(response.headers))


def _decode(raw: bytes):
    import json

    if not raw.strip():
        raise ProtocolError(INVALID_REQUEST, "The request body is empty")
    try:
        return json.loads(raw)
    except ValueError as error:
        raise ProtocolError(PARSE_ERROR, f"The body is not valid JSON: {error}") from error


def _negotiated_version(request: Request) -> str:
    requested = request.headers.get(PROTOCOL_HEADER, "")
    if requested in mcp.SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return mcp.PROTOCOL_VERSION


def _charge(db: Session, credential: Credential, message):
    """Spend this request's tool calls, or refuse the whole request.

    Committed rather than flushed: the budget has been spent by the time the
    tools run, and a client that could roll back its own charge by making the
    request fail afterwards would not be rate limited at all.

    A batch asking for more calls than the entire budget is a client defect,
    not a client going too fast — retrying it will never succeed — so it gets
    400 and a sentence saying so, rather than a 429 that promises a later
    attempt would work.
    """
    units = limits.cost(message)
    if units == 0:
        return limits.unlimited()

    if limits.is_enabled() and units > settings.MCP_RATE_LIMIT_CALLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A batch may contain at most {settings.MCP_RATE_LIMIT_CALLS} "
                "tool calls"
            ),
        )

    budget = limits.consume(db, key=credential.rate_key, units=units)
    db.commit()

    if not budget.allowed:
        logger.warning(
            "[MCP] rate limited actor=%s via=%s units=%s retry_after=%ss",
            credential.user.id, credential.label, units, budget.retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many tool calls. Slow down and try again shortly.",
            headers=budget.headers,
        )
    return budget


def _dispatch(db: Session, credential: Credential, project_id, message) -> dict | None:
    """One message, with every failure turned into something a client can read."""
    if not isinstance(message, dict):
        return mcp.error_response(None, INVALID_REQUEST, "A request must be an object")

    user = credential.user
    request_id = message.get("id")
    try:
        reply = mcp.handle(db, user=user, project_id=project_id, message=message,
                           credential=credential)
    except ProtocolError as error:
        return mcp.error_response(request_id, error.code, error.message, error.data)
    except Exception:
        # A defect here must not reach a model as prose it might repeat, and
        # must not take the connection down. The detail goes to the log.
        logger.exception("[MCP] dispatch failed for method %r", message.get("method"))
        return mcp.error_response(request_id, INTERNAL_ERROR, "The request could not be completed")

    _audit(db, user, project_id, message, reply)
    return reply


def _audit(db: Session, user: User, project_id, message, reply) -> None:
    """Record proposals; log everything else.

    Every call is already logged with its tool, actor and outcome — and with
    neither its arguments nor its results, because those are project content
    and a log is not where content belongs.

    Only PROPOSE calls reach the audit trail. A read is a read: writing a row
    for each would put thousands of entries a day into a table people actually
    read, and drown the entries that matter. A proposal is different — it is an
    AI suggesting a change to somebody's project, and that is worth keeping
    whether or not anybody confirms it.
    """
    if message.get("method") != "tools/call" or reply is None:
        return
    name = (message.get("params") or {}).get("name")
    tool = BY_NAME.get(name) if isinstance(name, str) else None
    if tool is None or tool.kind is not ToolKind.PROPOSE:
        return

    result = reply.get("result") or {}
    record_audit(
        db, actor_id=user.id, action="mcp_tool_proposed", entity_type="project",
        entity_id=project_id, project_id=project_id,
        details={"tool": name, "ok": not result.get("isError", False)},
    )
    db.commit()
