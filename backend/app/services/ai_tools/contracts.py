"""What a tool is, and what it promises.

Every AI system that touches this platform — voice today, agents in Phase 6 —
should reach it through one interface with one set of rules. The rule that
shapes everything here is the one Phase 5 states plainly: the tool layer must
not become a bypass around the backend. So a tool is deliberately *not* a place
where behaviour lives. It is a declaration of an operation the platform already
performs, bound to the permission that already governs it, and its
implementation calls the same service the web UI calls.

Two structural guarantees follow from that, and both are tested rather than
promised:

  * **A tool cannot widen authorization.** Every tool names a permission, and
    the runtime checks it before the implementation runs. An implementation
    that forgot to check would still be checked.

  * **A tool cannot execute a consequential change on its own.** Writes are
    `ToolKind.PROPOSE`: they build a proposal, validate it against the same
    rules engine the voice path uses, and return it for a human to confirm.
    Execution stays behind the existing confirmation lifecycle, where it
    already is. Nothing here shortens that path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel


class ToolKind(str, Enum):
    #: Reads project data. Safe to call without confirmation.
    READ = "READ"
    #: Builds a change for a human to confirm. Never executes it.
    PROPOSE = "PROPOSE"


@dataclass(frozen=True)
class ToolSpec:
    """One capability, declared."""

    name: str
    kind: ToolKind
    #: What it does, in words an agent's prompt can use directly.
    description: str
    #: Pydantic model for the arguments. Invalid arguments are rejected against
    #: this before the implementation is reached, so a tool never has to
    #: defend itself against a malformed call.
    arguments: type[BaseModel]
    #: The catalogue permission the caller must hold on the project. `None`
    #: only where the operation's own service is the sole gate — messaging
    #: decides per recipient — and such tools must say so in `authorization_note`.
    permission_code: str | None
    #: The function that does the work. Signature: (db, actor, project_id, args).
    handler: Callable[..., Any] = field(repr=False, default=None)
    #: True when the tool needs a project. Only platform-level tools do not.
    project_scoped: bool = True
    #: Why this tool is safe, in one sentence — read by reviewers, and required
    #: on any tool that declares no permission code.
    authorization_note: str = ""

    @property
    def requires_confirmation(self) -> bool:
        return self.kind is ToolKind.PROPOSE

    def json_schema(self) -> dict:
        """The argument contract, as an agent framework expects to see it."""
        return self.arguments.model_json_schema()

    def as_definition(self) -> dict:
        """The full public contract for this tool."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "description": self.description,
            "parameters": self.json_schema(),
            "permission": self.permission_code,
            "projectScoped": self.project_scoped,
            "requiresConfirmation": self.requires_confirmation,
            "authorizationNote": self.authorization_note,
        }


class ToolError(Exception):
    """A tool call that could not be completed, with a reason worth showing.

    Carries a machine-readable code so an agent can distinguish "you may not"
    from "that does not exist" from "your arguments were wrong" — three
    outcomes that need three different next moves and would otherwise arrive
    as the same opaque failure.
    """

    def __init__(self, code: str, message: str, *, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class ToolResult:
    """What a tool call returns, whether or not it succeeded."""

    tool: str
    ok: bool
    data: dict = field(default_factory=dict)
    #: Set on PROPOSE tools: what a human is being asked to approve.
    proposal: dict | None = None
    error_code: str | None = None
    error: str | None = None

    def as_json(self) -> dict:
        payload: dict[str, Any] = {"tool": self.tool, "ok": self.ok, "data": self.data}
        if self.proposal is not None:
            payload["proposal"] = self.proposal
            payload["requiresConfirmation"] = True
        if not self.ok:
            payload["errorCode"] = self.error_code
            payload["error"] = self.error
        return payload
