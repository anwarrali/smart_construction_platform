"""Which agents care about which events, and whether one should run.

Phase 6 let each agent *declare* the events it subscribes to. This resolves
those declarations in the other direction — given an event, which agents want
it — and decides whether a matched agent should actually run.

**Nothing here executes anything.** There is no scheduler, no worker, no
background thread. `agents_for_event` and `decide` are pure functions over
declarations, and the orchestrator calls them only when something asks it to.
That separation is deliberate: Phase 8 turns proactive analysis on by calling
these from the event dispatcher, and it should be able to do that without first
having to unpick an execution model built here on speculation.

The decision is separate from the match because "this agent subscribes to this
event" and "this agent should run right now" are different questions. An agent
can match an event and still be skipped — the caller may lack its permission,
or the same evidence may have been analysed moments ago — and a skip is a
normal outcome that must not read as a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun as AgentRunRecord
from app.models.user import User
from app.services.agents.registry import AGENTS, BY_NAME
from app.services.authorization import has_permission

#: How recently the same agent must have run on the same project for a new
#: event-driven run to be considered redundant. Events arrive in bursts — ten
#: documents uploaded in a minute is one action by a person — and re-running an
#: agent ten times over near-identical evidence produces no new information.
#:
#: Manual runs ignore this: a person asking for analysis has a reason.
EVENT_COOLDOWN = timedelta(minutes=10)


class TriggerType:
    MANUAL = "MANUAL"
    EVENT = "EVENT"


@dataclass(frozen=True)
class RunDecision:
    """Whether an agent should run, and why — either way."""

    agent: str
    should_run: bool
    reason: str
    #: Set when the answer is no, so a caller can tell a permission refusal
    #: from a cooldown from an unknown agent.
    skip_code: str | None = None

    def as_json(self) -> dict:
        return {
            "agent": self.agent, "shouldRun": self.should_run,
            "reason": self.reason, "skipCode": self.skip_code,
        }


def agents_for_event(event_type: str) -> list[str]:
    """Agents that declared an interest in this event type."""
    return [agent.name for agent in AGENTS if event_type in agent.subscribes_to]


def event_subscription_map() -> dict[str, list[str]]:
    """Every event the agents listen for, and who listens.

    Rendered for documentation and for Phase 8 to read when it wires the
    dispatcher, so the mapping never has to be restated by hand.
    """
    mapping: dict[str, list[str]] = {}
    for agent in AGENTS:
        for event in agent.subscribes_to:
            mapping.setdefault(event, []).append(agent.name)
    return mapping


def decide(
    db: Session,
    *,
    user: User,
    project_id,
    agent_name: str,
    trigger_type: str = TriggerType.MANUAL,
    event_type: str | None = None,
    now: datetime | None = None,
) -> RunDecision:
    """Should this agent run, for this caller, right now?

    Ordered cheapest-first, and permission is checked before anything else that
    could leak whether a project has recent activity.
    """
    agent = BY_NAME.get(agent_name)
    if agent is None:
        return RunDecision(agent_name, False, f"No agent named {agent_name!r}", "UNKNOWN_AGENT")

    if not has_permission(db, user, agent.permission_code, project_id):
        return RunDecision(
            agent_name, False,
            f"The caller does not hold {agent.permission_code}.", "FORBIDDEN",
        )

    if trigger_type == TriggerType.EVENT:
        if event_type and event_type not in agent.subscribes_to:
            return RunDecision(
                agent_name, False,
                f"{agent_name} does not subscribe to {event_type}.", "NOT_SUBSCRIBED",
            )
        moment = now or datetime.now(timezone.utc)
        recent = (
            db.query(AgentRunRecord)
            .filter(
                AgentRunRecord.project_id == project_id,
                AgentRunRecord.agent_name == agent_name,
                AgentRunRecord.status == "SUCCEEDED",
                AgentRunRecord.created_at >= moment - EVENT_COOLDOWN,
            )
            .first()
        )
        if recent:
            return RunDecision(
                agent_name, False,
                (
                    f"{agent_name} already ran on this project within "
                    f"{int(EVENT_COOLDOWN.total_seconds() // 60)} minutes; "
                    "a burst of events is one action, not many."
                ),
                "COOLDOWN",
            )
        return RunDecision(agent_name, True, f"{event_type} matched {agent_name}'s subscription.")

    return RunDecision(agent_name, True, "Requested directly.")
