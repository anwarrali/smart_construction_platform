"""Calling a tool: validate, authorize, run, report.

The order is the whole point. Arguments are validated before authorization so a
malformed call cannot reach a permission check; authorization runs before the
handler so a handler that forgot to check is checked anyway. A handler is only
ever reached by a caller who is a member of the project, holds the tool's
permission, and supplied arguments that fit the declared contract.

This is what stops the tool layer being a bypass. The individual handlers
delegate to the platform's own scoping helpers — they are not trusted to be the
boundary, they are simply not the only one.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.models.user import User
from app.models.enums import UserStatus
from app.services.ai_tools.contracts import ToolError, ToolResult
from app.services.ai_tools.registry import BY_NAME
from app.services.authorization import has_permission

logger = logging.getLogger(__name__)


def available_tools(db: Session, *, user: User, project_id) -> list[dict]:
    """The contracts for tools this caller can actually use here.

    An agent prompt built from this lists only what the speaker holds, so the
    model is never taught to attempt something that will be refused — the same
    approach `voice_capabilities` already takes for the voice prompt.
    """
    if not user_has_project_access(db, user, project_id):
        return []
    return [
        tool.as_definition()
        for tool in BY_NAME.values()
        if _permitted(db, user, project_id, tool)
    ]


def _permitted(db: Session, user: User, project_id, tool) -> bool:
    if tool.permission_code is None:
        return True
    return has_permission(db, user, tool.permission_code, project_id)


def call_tool(
    db: Session,
    *,
    user: User,
    project_id,
    name: str,
    arguments: dict | None = None,
) -> ToolResult:
    """Run one tool call and return a structured result, never an exception.

    Failures come back as `ok: false` with a code, because an agent has to be
    able to act on the difference between "you may not", "that does not exist"
    and "your arguments were wrong". Raising would collapse all three into a
    stack trace the model cannot read.
    """
    tool = BY_NAME.get(name)
    if tool is None:
        return ToolResult(name, ok=False, error_code="UNKNOWN_TOOL",
                          error=f"No tool named {name!r}")

    if user.status != UserStatus.ACTIVE:
        return ToolResult(name, ok=False, error_code="FORBIDDEN",
                          error="An active account is required")

    # 1. Arguments, before anything else touches them.
    try:
        parsed = tool.arguments.model_validate(arguments or {})
    except ValidationError as error:
        return ToolResult(
            name, ok=False, error_code="INVALID_ARGUMENTS",
            error="; ".join(
                f"{'.'.join(str(part) for part in item['loc']) or 'arguments'}: {item['msg']}"
                for item in error.errors()[:5]
            ),
        )

    # 2. Project access, then the tool's own permission.
    if tool.project_scoped:
        if project_id is None:
            return ToolResult(name, ok=False, error_code="INVALID_ARGUMENTS",
                              error="This tool requires a project")
        if not user_has_project_access(db, user, project_id):
            return ToolResult(name, ok=False, error_code="FORBIDDEN",
                              error="You do not have access to this project")
    if not _permitted(db, user, project_id, tool):
        return ToolResult(name, ok=False, error_code="FORBIDDEN",
                          error=f"The {tool.permission_code} permission is required")

    # 3. The handler, which may still refuse for reasons only it can see.
    try:
        payload = tool.handler(db, user, project_id, parsed)
    except ToolError as error:
        return ToolResult(name, ok=False, error_code=error.code, error=error.message)
    except Exception:
        # Never leak an internal failure to a model as prose it might repeat.
        logger.exception("[AITools] %s failed", name)
        return ToolResult(name, ok=False, error_code="TOOL_FAILED",
                          error="The tool could not be completed")

    if tool.requires_confirmation:
        return ToolResult(name, ok=True, data={}, proposal=payload)
    return ToolResult(name, ok=True, data=payload)
