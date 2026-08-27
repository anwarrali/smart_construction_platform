"""The controlled interface AI systems use to reach this platform.

Nothing in here performs an operation the platform does not already perform,
and nothing decides an authorization question the platform does not already
decide. Tools declare, the runtime enforces, and the services underneath stay
authoritative.
"""

from app.services.ai_tools.contracts import ToolError, ToolKind, ToolResult, ToolSpec
from app.services.ai_tools.registry import BY_NAME, TOOLS, tool_definitions
from app.services.ai_tools.runtime import available_tools, call_tool

__all__ = [
    "BY_NAME", "TOOLS", "ToolError", "ToolKind", "ToolResult", "ToolSpec",
    "available_tools", "call_tool", "tool_definitions",
]
