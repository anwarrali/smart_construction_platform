"""Running a set of agents as one governed pass.

The orchestration Phase 7 asks for, and deliberately not more than that. It
decides which agents should run, runs them one at a time, isolates each from
the others, and records what happened. It does not chain agents, feed one's
output into another's input, or run anything in the background.

Agent-to-agent coupling is the thing this avoids. Five independent analysts
that share a finding table can be reasoned about one at a time; five analysts
wired into a pipeline cannot, and a failure anywhere in that pipeline becomes
everybody's failure. Where one agent genuinely needs another's conclusions, it
reads them the same way a person would — through the `get_findings` tool, with
the same authorization, and only if it was granted that tool.

Isolation is enforced twice: `run_agent` catches its own analysis and persist
failures, and this catches anything that still escapes. One agent failing
leaves the others' results intact and reported.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.models.agent_run import AgentRun as AgentRunRecord
from app.models.user import User
from app.services.agents.registry import AGENTS
from app.services.agents.runtime import run_agent
from app.services.agents.subscriptions import RunDecision, TriggerType, agents_for_event, decide

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationReport:
    """What one pass did, agent by agent."""

    project_id: str
    trigger_type: str
    trigger_reason: str
    ran: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

    @property
    def finding_count(self) -> int:
        return sum(item.get("findingCount", 0) for item in self.ran)

    def as_json(self) -> dict:
        return {
            "projectId": self.project_id,
            "trigger": {"type": self.trigger_type, "reason": self.trigger_reason},
            "ran": self.ran, "skipped": self.skipped, "failed": self.failed,
            "agentsRun": len(self.ran), "agentsSkipped": len(self.skipped),
            "agentsFailed": len(self.failed), "findingCount": self.finding_count,
        }


def orchestrate(
    db: Session,
    *,
    user: User,
    project_id,
    agents: list[str] | None = None,
    trigger_type: str = TriggerType.MANUAL,
    trigger_reason: str | None = None,
    event_type: str | None = None,
    event_id=None,
    persist: bool = True,
) -> OrchestrationReport:
    """Run the agents that should run, and record what each of them did.

    `agents=None` means every agent — narrowed by `decide`, which drops the
    ones this caller may not run and, for event triggers, the ones that just
    ran. Passing an explicit list still goes through `decide`: naming an agent
    is not authority to run it.
    """
    reason = trigger_reason or (
        f"Triggered by {event_type}" if event_type else "Requested directly"
    )
    report = OrchestrationReport(str(project_id), trigger_type, reason)

    if not user_has_project_access(db, user, project_id):
        report.skipped.append(RunDecision(
            "*", False, "The caller has no access to this project.", "FORBIDDEN",
        ).as_json())
        return report

    if agents is not None:
        candidates = agents
    elif event_type:
        candidates = agents_for_event(event_type)
    else:
        candidates = [agent.name for agent in AGENTS]

    for name in candidates:
        decision = decide(
            db, user=user, project_id=project_id, agent_name=name,
            trigger_type=trigger_type, event_type=event_type,
        )
        if not decision.should_run:
            report.skipped.append(decision.as_json())
            continue

        try:
            result = run_agent(db, user=user, project_id=project_id, name=name, persist=persist)
        except Exception:
            # `run_agent` already contains its own failures; this is the
            # backstop that keeps one unexpected escape from ending the pass.
            logger.exception("[Orchestrator] %s escaped its own error handling", name)
            _record(db, project_id, name, user, trigger_type, reason, event_id,
                    status="FAILED", error_code="ORCHESTRATION_FAILED",
                    error="The agent failed unexpectedly", persist=persist)
            report.failed.append({"agent": name, "ok": False,
                                  "errorCode": "ORCHESTRATION_FAILED",
                                  "error": "The agent failed unexpectedly"})
            continue

        payload = result.as_json()
        payload["reason"] = decision.reason
        _record(
            db, project_id, name, user, trigger_type, reason, event_id,
            status="SUCCEEDED" if result.ok else "FAILED",
            error_code=result.error_code, error=result.error,
            tool_calls=result.tool_calls,
            finding_codes=[item.code for item in result.findings],
            insight_ids=result.stored_insight_ids,
            highest_confidence=max((item.confidence for item in result.findings), default=None),
            duration_ms=result.duration_ms, persist=persist,
        )
        (report.ran if result.ok else report.failed).append(payload)

    return report


def _record(
    db: Session, project_id, agent_name: str, user: User, trigger_type: str,
    reason: str, event_id, *, status: str, error_code: str | None = None,
    error: str | None = None, tool_calls=None, finding_codes=None, insight_ids=None,
    highest_confidence=None, duration_ms=None, persist: bool = True,
) -> None:
    """Write the run record. Never allowed to break the pass.

    A preview run (`persist=False`) records nothing: it did not change
    anything, and a run log full of previews would bury the runs that did.
    """
    if not persist:
        return
    now = datetime.now(timezone.utc)
    try:
        db.add(AgentRunRecord(
            project_id=project_id, agent_name=agent_name,
            trigger_type=trigger_type, trigger_event_id=event_id, trigger_reason=reason,
            actor_user_id=user.id, status=status, error_code=error_code, error=error,
            tool_calls_json=tool_calls or [], finding_codes_json=finding_codes or [],
            insight_ids_json=insight_ids or [], finding_count=len(finding_codes or []),
            highest_confidence=highest_confidence, duration_ms=duration_ms,
            started_at=now, completed_at=now,
        ))
        db.commit()
    except Exception:
        logger.exception("[Orchestrator] could not record the run of %s", agent_name)
        db.rollback()


def orchestrate_for_event(
    db: Session, *, user: User, project_id, event_type: str, event_id=None,
    reason: str | None = None,
) -> OrchestrationReport:
    """The entry point Phase 8 will call from the event dispatcher.

    It exists now, and is tested now, so that turning proactive analysis on
    later is a matter of calling it rather than designing it. Nothing calls it
    automatically today — there is no subscriber wired to the dispatcher, by
    design.
    """
    return orchestrate(
        db, user=user, project_id=project_id, trigger_type=TriggerType.EVENT,
        event_type=event_type, event_id=event_id,
        trigger_reason=reason or f"Domain event {event_type}",
    )
