"""The only way an agent reaches the platform.

An agent gets one of these and nothing else — no database session for project
data, no service imports, no query it wrote itself. Every read goes through
`call_tool`, which validates arguments, checks project access and checks the
tool's permission before any handler runs.

Two containments, and the second is the one that matters:

  * The tool runtime stops an agent reading what its *caller* may not read.
  * This context stops an agent calling a tool it was not *granted*, even when
    the caller could call that tool directly. The Schedule Risk Agent holds no
    document tools, so it cannot read a contract however it is prompted.

That second one is why `allowed_tools` is a hard gate here rather than advice
in a prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.ai_tools import ToolResult, call_tool


@dataclass
class AgentContext:
    """A scoped, audited handle on the tool layer."""

    db: Session
    user: User
    project_id: object
    agent: object
    #: Every call made, in order, for the run record. An agent's reasoning is
    #: only reviewable if what it looked at is known.
    calls: list[dict] = field(default_factory=list)

    def call(self, tool: str, arguments: dict | None = None) -> ToolResult:
        """Call a granted tool, or record a refusal.

        A tool outside the grant is refused here and logged, rather than
        raising: an agent asking for something it does not hold is a fact worth
        keeping, and the run should continue with what it does hold.
        """
        if tool not in self.agent.allowed_tools:
            result = ToolResult(
                tool, ok=False, error_code="TOOL_NOT_GRANTED",
                error=f"{self.agent.name} may not call {tool!r}",
            )
        else:
            result = call_tool(
                self.db, user=self.user, project_id=self.project_id,
                name=tool, arguments=arguments or {},
            )
        self.calls.append({
            "tool": tool, "ok": result.ok,
            "errorCode": result.error_code, "arguments": arguments or {},
        })
        return result

    def data(self, tool: str, arguments: dict | None = None) -> dict:
        """The tool's data, or an empty dict when it could not be read.

        Agents branch on emptiness to raise an explicit uncertainty finding, so
        a refused or failed call degrades into "I could not see this" rather
        than into a wrong conclusion drawn from missing data.
        """
        result = self.call(tool, arguments)
        return result.data if result.ok else {}

    @property
    def refused_tools(self) -> list[str]:
        return [item["tool"] for item in self.calls if not item["ok"]]
