"""The five project agents.

Each is a bounded analyst over data the platform already holds. They read
through the Phase 5 tool layer, reason deterministically, and produce findings
stored as `AIInsight` — the same record the review queue, the promotion
endpoints and the AI Intelligence page already work against.

No agent writes project data. Acting on a recommendation goes through the
existing human promotion path.
"""

from app.services.agents.contracts import (
    AgentError, AgentFinding, AgentSpec, Certainty, Evidence,
)
from app.services.agents.context import AgentContext
from app.services.agents.registry import AGENTS, BY_NAME, agent_definitions
from app.services.agents.runtime import AgentRun, available_agents, run_agent, run_all

__all__ = [
    "AGENTS", "BY_NAME", "AgentContext", "AgentError", "AgentFinding", "AgentRun",
    "AgentSpec", "Certainty", "Evidence", "agent_definitions", "available_agents",
    "run_agent", "run_all",
]
