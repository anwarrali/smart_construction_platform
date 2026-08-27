"""Running an agent, and turning what it concluded into reviewable findings.

The order is the same discipline the tool runtime uses: authorize, then run,
then persist. An agent's analyzer is only reached by a caller who is a member
of the project and holds the agent's permission — and every read the analyzer
then makes is checked again by the tool runtime against that same caller.

Findings are stored as `AIInsight`, the platform's existing finding record,
with sources registered through `ai_traceability_service`. That is not a
convenience: the review queue, the severity filters, the create-issue and
create-task promotion endpoints and the AI Intelligence page all already work
against `AIInsight`. An agent finding therefore arrives somewhere a person
already looks, with a promotion path that already requires a human — which is
what keeps "no agent silently performs a consequential write" true by
construction rather than by policy.
"""

from __future__ import annotations

import hashlib
import json
import logging
from time import perf_counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.models.enums import UserStatus
from app.models.ifc import AIInsight
from app.models.user import User
from app.services.agents.context import AgentContext
from app.services.agents.contracts import AgentFinding, Certainty
from app.services.agents.registry import AGENTS, BY_NAME
from app.services.ai_traceability_service import register_insight_source
from app.services.authorization import has_permission

logger = logging.getLogger(__name__)

#: `AIInsight.category` for agent output. Findings stay distinguishable from
#: the IFC rule engines' output, which uses its own categories.
AGENT_CATEGORY = "AGENT_FINDING"


@dataclass
class AgentRun:
    """What one agent run did, whether or not it found anything."""

    agent: str
    ok: bool
    findings: list[AgentFinding] = field(default_factory=list)
    stored_insight_ids: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    error_code: str | None = None
    error: str | None = None
    duration_ms: int | None = None

    def as_json(self) -> dict:
        payload = {
            "agent": self.agent, "ok": self.ok,
            "findingCount": len(self.findings),
            "findings": [
                {
                    "code": item.code, "certainty": item.certainty.value,
                    "severity": item.severity, "confidence": item.confidence,
                    "title": item.title, "description": item.description,
                    "reason": item.reason, "recommendedAction": item.recommended_action,
                    "requiresConfirmation": item.requires_confirmation,
                    "evidence": [source.as_json() for source in item.evidence],
                    "affected": item.affected,
                }
                for item in self.findings
            ],
            "storedInsightIds": self.stored_insight_ids,
            "toolCalls": self.tool_calls,
            "durationMs": self.duration_ms,
        }
        if not self.ok:
            payload["errorCode"] = self.error_code
            payload["error"] = self.error
        return payload


def available_agents(db: Session, *, user: User, project_id) -> list[dict]:
    """The agents this caller may actually run here."""
    if not user_has_project_access(db, user, project_id):
        return []
    return [
        agent.as_definition() for agent in AGENTS
        if has_permission(db, user, agent.permission_code, project_id)
    ]


def _fingerprint(agent: str, project_id, finding: AgentFinding) -> str:
    """Stable identity for a finding, so re-running does not duplicate it.

    Keyed on what the finding is *about* rather than on its wording, so a
    rephrased description updates the existing row instead of creating a second
    one beside it.
    """
    payload = json.dumps({
        "agent": agent, "project": str(project_id), "code": finding.code,
        "affected": finding.affected,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def run_agent(db: Session, *, user: User, project_id, name: str, persist: bool = True) -> AgentRun:
    """Run one agent and, by default, store what it found.

    `persist=False` exists for callers that want to see what an agent would
    report without adding to anyone's review queue — a preview, not a
    different analysis.
    """
    agent = BY_NAME.get(name)
    if agent is None:
        return AgentRun(name, ok=False, error_code="UNKNOWN_AGENT",
                        error=f"No agent named {name!r}")
    if user.status != UserStatus.ACTIVE:
        return AgentRun(name, ok=False, error_code="FORBIDDEN",
                        error="An active account is required")
    if not user_has_project_access(db, user, project_id):
        return AgentRun(name, ok=False, error_code="FORBIDDEN",
                        error="You do not have access to this project")
    if not has_permission(db, user, agent.permission_code, project_id):
        return AgentRun(name, ok=False, error_code="FORBIDDEN",
                        error=f"The {agent.permission_code} permission is required to run {agent.title}")

    context = AgentContext(db=db, user=user, project_id=project_id, agent=agent)
    started = perf_counter()
    try:
        findings = list(agent.analyzer(context))
    except Exception:
        logger.exception("[Agents] %s analysis failed", name)
        return AgentRun(name, ok=False, tool_calls=context.calls,
                        error_code="AGENT_FAILED", error="The agent could not complete",
                        duration_ms=int((perf_counter() - started) * 1000))

    run = AgentRun(name, ok=True, findings=findings, tool_calls=context.calls)
    if persist:
        # Storing is a separate failure domain from analysing. An agent that
        # reasoned correctly and then hit a database problem must not take the
        # rest of the pass down with it, so this is caught here rather than
        # allowed to escape into the orchestrator.
        try:
            for finding in findings:
                run.stored_insight_ids.append(str(_store(db, agent, project_id, finding).id))
            db.commit()
        except Exception:
            logger.exception("[Agents] %s could not store its findings", name)
            db.rollback()
            run.ok = False
            run.error_code = "PERSIST_FAILED"
            run.error = "The agent produced findings but they could not be stored"
            run.stored_insight_ids = []
    run.duration_ms = int((perf_counter() - started) * 1000)
    return run


def _store(db: Session, agent, project_id, finding: AgentFinding) -> AIInsight:
    """Persist one finding as an `AIInsight`, with its sources registered."""
    fingerprint = _fingerprint(agent.name, project_id, finding)
    insight = db.query(AIInsight).filter(AIInsight.fingerprint == fingerprint).first()
    evidence_json = {
        **finding.as_evidence_json(),
        "agent": agent.name,
        "agentTitle": agent.title,
    }
    if not insight:
        insight = AIInsight(
            project_id=project_id, fingerprint=fingerprint,
            insight_type=finding.code, category=AGENT_CATEGORY,
            severity=finding.severity, confidence=finding.confidence,
            title=finding.title, description=finding.description,
            reason=finding.reason, recommended_action=finding.recommended_action,
            potential_impact=finding.potential_impact,
            evidence_json=evidence_json, affected_json=finding.affected,
            related_task_ids_json=list(finding.related_task_ids),
            related_issue_ids_json=list(finding.related_issue_ids),
            source_engine=agent.source_engine, status="NEW",
        )
        db.add(insight)
        db.flush()
    elif insight.status in {"NEW", "OPEN", "UNDER_REVIEW"}:
        # A finding a person has already ruled on is left alone; one still in
        # the queue is refreshed, because the underlying data has moved on.
        insight.severity = finding.severity
        insight.confidence = finding.confidence
        insight.description = finding.description
        insight.reason = finding.reason
        insight.recommended_action = finding.recommended_action
        insight.potential_impact = finding.potential_impact
        insight.evidence_json = evidence_json
        insight.affected_json = finding.affected
        insight.related_task_ids_json = list(finding.related_task_ids)
        insight.related_issue_ids_json = list(finding.related_issue_ids)

    for source in finding.evidence:
        try:
            register_insight_source(
                db, insight, source_type=source.source_type,
                source_id=source.source_id, label=source.label,
            )
        except Exception:
            # A citation that cannot be registered must not lose the finding.
            logger.exception("[Agents] source registration failed for %s", source.source_id)
    return insight


def run_all(db: Session, *, user: User, project_id, persist: bool = True) -> list[AgentRun]:
    """Every agent this caller may run. Agents do not call each other.

    They share the finding table instead: one agent's output is another's
    potential input on a later run. Orchestration between them is Phase 7.
    """
    return [
        run_agent(db, user=user, project_id=project_id, name=definition["name"], persist=persist)
        for definition in available_agents(db, user=user, project_id=project_id)
    ]
