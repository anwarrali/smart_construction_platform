"""The Model Context Protocol, as this platform speaks it.

MCP is JSON-RPC 2.0. This module is the whole protocol: envelopes, method
dispatch, and the translation between MCP's vocabulary and the tool layer's.
It is deliberately **pure** — it takes a session, a user and a decoded request,
and returns a dict. No FastAPI, no HTTP, no transport. `api/mcp.py` is the
transport and does nothing else, which is what makes every rule below testable
without a client.

## Why this is written rather than taken from the SDK

The official `mcp` package builds standalone servers: it owns the transport,
the session lifecycle and the event loop. Every one of those fights what this
server has to do — resolve a JWT through `Depends(get_current_user)`, open a
request-scoped SQLAlchemy session through `Depends(get_db)`, and check
permissions with the same helpers the REST API uses. Reusing those is the
entire security argument for this feature, so an SDK that wants to own the
request lifecycle would have to be worked around at exactly the point where
mistakes are expensive.

What is actually required for a request/response tool server is JSON-RPC over
one POST, which is small enough to read in full. If server-initiated
notifications are ever needed — `notifications/tools/list_changed`, progress,
sampling — the SDK becomes the right answer and this module is what it
replaces.

## The two error channels, and why the distinction matters

MCP separates them and so does this:

  * A **protocol** failure — malformed JSON-RPC, an unknown method, a missing
    parameter — is a JSON-RPC `error` object. The call never reached a tool.
  * A **tool** failure — no permission, not found, bad arguments — is a
    *successful* JSON-RPC response whose result carries `isError: true`.

That is not pedantry. A model reading `isError` learns "the platform answered,
and the answer is no", which it can act on; a JSON-RPC error tells it the
request itself was wrong. Collapsing them would make "you may not read that"
indistinguishable from "your client is broken". `ToolResult.ok` already draws
exactly this line, so the mapping is one field.

## Authorization is not implemented here

`tools/list` calls `ai_tools.available_tools`; `tools/call` calls
`ai_tools.call_tool`. Neither is wrapped, widened or second-guessed. A tool the
caller may not use is not listed, and calling it anyway is refused by the same
runtime the agent layer goes through. This module adds no authorization
decision of its own — if it did, there would be two, and one of them would
eventually be wrong.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import ai_tools
from app.services.ai_tools.contracts import ToolKind, ToolResult
from app.services.ai_tools.registry import BY_NAME

logger = logging.getLogger("uvicorn.error").getChild("mcp")

#: The spec revision this server implements. Sent back from `initialize`, and
#: echoed when a client asks for a version we also support.
PROTOCOL_VERSION = "2025-06-18"
#: Older revisions whose `tools/*` shape is identical to the one above. A
#: client pinned to one of these is answered in its own version rather than
#: being told to upgrade over a difference that does not affect it.
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION, "2025-03-26", "2024-11-05")

SERVER_NAME = "construction-platform"
SERVER_TITLE = "Construction Platform"

# --- JSON-RPC error codes ---------------------------------------------------
# The four standard ones plus MCP's convention of using the implementation-
# defined range for its own conditions.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ProtocolError(Exception):
    """A JSON-RPC level failure: the call never reached a tool."""

    def __init__(self, code: int, message: str, data: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _result(request_id: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def error_response(request_id: Any, code: int, message: str,
                   data: dict | None = None) -> dict:
    body: dict[str, Any] = {"code": code, "message": message}
    if data:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": body}


# --- Tool translation -------------------------------------------------------


def _annotations(definition: dict) -> dict:
    """MCP's behavioural hints, derived from what the tool already declares.

    These are *hints* in the spec — a client may show them, and a well-built
    one uses `readOnlyHint` to decide whether to ask before calling. They are
    not a security control and nothing here treats them as one: the guarantee
    that a PROPOSE tool changes nothing comes from the handlers, which build a
    dict and persist nothing.
    """
    proposes = definition["kind"] == ToolKind.PROPOSE.value
    return {
        "title": definition["name"].replace("_", " ").title(),
        "readOnlyHint": not proposes,
        # A proposal is not destructive: it is a suggestion a person must
        # accept, and accepting runs through the confirmation lifecycle where
        # the real checks are.
        "destructiveHint": False,
        # A read is idempotent; a proposal builds the same proposal each time,
        # because it writes nothing that a second call would see.
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _describe(definition: dict) -> str:
    """The tool's description, plus the two facts a model must not miss.

    A model that reports a proposal as a completed action is the single most
    damaging thing this surface could enable, so the description says so
    outright rather than relying on the client to render an annotation.
    """
    parts = [definition["description"]]
    if definition["requiresConfirmation"]:
        parts.append(
            "PROPOSAL ONLY: this does not perform the change. It returns a "
            "proposal that a person must confirm, after which the platform "
            "re-checks permission and executes it. Never report the result of "
            "this tool as something that has happened."
        )
    if definition.get("permission"):
        parts.append(f"Requires the {definition['permission']} permission.")
    return " ".join(parts)


def tool_descriptor(definition: dict) -> dict:
    """One tool, in MCP's shape.

    `inputSchema` is the Pydantic-generated JSON Schema the tool already
    publishes — the same contract `call_tool` validates against, so what a
    client is told and what the server enforces cannot drift.
    """
    return {
        "name": definition["name"],
        "title": definition["name"].replace("_", " ").title(),
        "description": _describe(definition),
        "inputSchema": definition["parameters"],
        "annotations": _annotations(definition),
    }


def _content_blocks(payload: dict) -> list[dict]:
    """The result as MCP content.

    One JSON text block. Every client understands `type: "text"`, and the
    structured form is offered alongside in `structuredContent` for those that
    read it — rather than instead of it, which would leave older clients with
    nothing.
    """
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}]


# --- Methods ----------------------------------------------------------------


def _initialize(params: dict) -> dict:
    """Negotiate. The only method that runs before anything is authorized.

    A version we recognise is echoed back so a pinned client keeps working; an
    unknown one is answered with ours, which the spec says the client may then
    accept or disconnect over. Refusing outright would break clients over a
    difference that does not affect the two methods this server implements.
    """
    requested = str(params.get("protocolVersion") or "")
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
    client = params.get("clientInfo") or {}
    if client:
        logger.info(
            "[MCP] initialize from %s %s (protocol %s)",
            client.get("name", "?"), client.get("version", "?"), requested or "unspecified",
        )
    return {
        "protocolVersion": version,
        "capabilities": {
            # Static: the tool table is a module-level constant, so it cannot
            # change while a session is open and a client need never re-list.
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": SERVER_NAME,
            "title": SERVER_TITLE,
            "version": _server_version(),
        },
        "instructions": (
            "Tools for one construction project. Everything listed is already "
            "scoped to what this caller may see: a tool you cannot use is not "
            "listed, and calling it anyway is refused. Tools whose description "
            "begins PROPOSAL ONLY change nothing — they return a proposal for a "
            "person to confirm."
        ),
    }


def _server_version() -> str:
    from app.main import app  # deferred: app imports the router that imports this

    return getattr(app, "version", "1.0.0")


def _tools_list(db: Session, user: User, project_id, credential=None) -> dict:
    """Exactly the tools this caller may use on this project.

    Filtered by `available_tools`, not by the full table. Listing a tool the
    caller cannot use would teach a model to attempt something that will be
    refused, and would disclose which capabilities exist behind a permission
    they do not hold.

    A credential narrows that further and can never widen it. `available_tools`
    answers what the *person* may do; the credential they arrived with may hold
    less — a client token without `mcp:propose` sees no PROPOSE tool here, and
    is refused one in `_tools_call` if it asks anyway. Two enforcement points
    for one rule, because hiding a tool is a courtesy to the model and the
    refusal is the boundary.
    """
    definitions = ai_tools.available_tools(db, user=user, project_id=project_id)
    if credential is not None:
        definitions = [item for item in definitions if credential.allows_definition(item)]
    return {"tools": [tool_descriptor(item) for item in definitions]}


def _scope_refusal(name: str, credential) -> ToolResult | None:
    """Refuse a tool the credential is not scoped for, in the tool layer's own
    shape.

    Built as a `ToolResult` rather than as a dict assembled here, so a scope
    refusal is indistinguishable in form from every other refusal a client
    already handles — `ok: false`, a code, a sentence.

    An unknown name falls through deliberately: answering "not in your scope"
    for a tool that does not exist would tell a client which names are real.
    `call_tool` reports UNKNOWN_TOOL for both.
    """
    if credential is None:
        return None
    tool = BY_NAME.get(name)
    if tool is None or credential.allows_definition(tool.as_definition()):
        return None
    return ToolResult(
        name, ok=False, error_code="SCOPE_DENIED",
        error=(
            "This credential is not scoped for that tool. An MCP client token "
            "needs the mcp:propose scope to reach a tool that proposes changes."
        ),
    )


def _tools_call(db: Session, user: User, project_id, params: dict,
                credential=None) -> dict:
    """Run one tool. Refusals come back as results, not as protocol errors."""
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise ProtocolError(INVALID_PARAMS, "A tool name is required")

    arguments = params.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ProtocolError(INVALID_PARAMS, "Tool arguments must be an object")

    result = _scope_refusal(name, credential) or ai_tools.call_tool(
        db, user=user, project_id=project_id, name=name, arguments=arguments,
    )
    payload = result.as_json()

    logger.info(
        "[MCP] tools/call project=%s actor=%s via=%s tool=%s ok=%s code=%s",
        project_id, user.id, getattr(credential, "label", "session"),
        name, result.ok, result.error_code or "-",
    )

    return {
        "content": _content_blocks(payload),
        "structuredContent": payload,
        # The line MCP draws: the platform answered, and the answer may be no.
        "isError": not result.ok,
    }


#: Methods that need no project and no authorization beyond a valid token.
#: `initialize` is the handshake; `ping` is the spec's liveness check.
UNSCOPED_METHODS = frozenset({"initialize", "ping"})

#: Notifications carry no id and must produce no response body.
NOTIFICATION_PREFIX = "notifications/"


def handle(db: Session, *, user: User, project_id, message: dict,
           credential=None) -> dict | None:
    """Dispatch one JSON-RPC message. Returns None for a notification.

    Raises `ProtocolError` only for protocol-level problems. Anything a tool
    decides — including refusing — comes back as a result.

    `credential` is optional and defaults to unrestricted, which means "as much
    as this user may do". That default is not a loophole: the only caller that
    omits it is a test, because `api/mcp.py` resolves one for every request.
    It is a default rather than a required argument so that a credential can
    only ever *subtract* — there is no value of it that grants anything
    `available_tools` and `call_tool` would not already have granted the user.
    """
    if message.get("jsonrpc") != "2.0":
        raise ProtocolError(INVALID_REQUEST, "Only JSON-RPC 2.0 is supported")

    method = message.get("method")
    if not isinstance(method, str) or not method:
        raise ProtocolError(INVALID_REQUEST, "A method is required")

    params = message.get("params") or {}
    if not isinstance(params, dict):
        raise ProtocolError(INVALID_PARAMS, "Params must be an object")

    request_id = message.get("id")
    is_notification = "id" not in message or method.startswith(NOTIFICATION_PREFIX)

    if method == "initialize":
        payload = _initialize(params)
    elif method == "ping":
        # The spec's ping takes and returns an empty object.
        payload = {}
    elif method == "tools/list":
        payload = _tools_list(db, user, project_id, credential)
    elif method == "tools/call":
        payload = _tools_call(db, user, project_id, params, credential)
    elif method.startswith(NOTIFICATION_PREFIX):
        # `notifications/initialized` and friends. Accepted and acknowledged by
        # silence, which is what a notification requires.
        logger.debug("[MCP] notification %s", method)
        return None
    else:
        raise ProtocolError(METHOD_NOT_FOUND, f"Unknown method {method!r}")

    if is_notification:
        return None
    return _result(request_id, payload)


def known_tool_names() -> set[str]:
    """Every tool in the table, whether or not any given caller may use it."""
    return set(BY_NAME)
