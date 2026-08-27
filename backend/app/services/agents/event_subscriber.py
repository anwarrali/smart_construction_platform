"""Analysis that starts because something happened, not because someone asked.

This is the hook Phase 7 built the architecture for. `emit_domain_event` calls
`process_event` synchronously, so there is no worker, no queue and no scheduler
here — analysis runs inline, inside the transaction that emitted the event, and
is wrapped so that a failure in it can never fail the upload or the task update
that triggered it. Secondary products do not get to break primary ones; the IFC
geometry pass established that rule in Phase 1 and it holds here.

## Whose authority does an automatic run use?

The question Phase 7 left open, and the one that decides whether this feature is
safe. A run started by a person borrows that person's permissions. A run started
by an event has no person.

Three answers were considered:

  * **The actor who caused the event.** Rejected. A worker filing site evidence
    has worker-level visibility, so the Site Report Agent would see almost
    nothing and report "analysed, nothing found" — under-detection presented as
    a clean bill of health, which is the exact false confidence this system
    exists to avoid.

  * **A new system superuser.** Rejected. It would be the only principal in the
    platform whose reach nobody had granted, and every finding would carry
    authority no real person holds.

  * **The project's assigned Project Manager.** Chosen. That person is
    accountable for the project, is who the findings are addressed to, and
    already holds the visibility the agents need. Crucially it is a *real*
    authority that a real administrator granted, so an automatic run can never
    read anything a person could not.

A project with no assigned manager is skipped, explicitly. There is no fallback
to anything broader — the absence of an accountable person is a reason not to
analyse, not a reason to analyse with more power.

Attribution stays honest: the run is recorded as `EVENT`-triggered with the
event id, so the log says the system started it on that person's authority
rather than implying they asked.

The whole path is **off by default** (`AGENT_AUTO_ANALYSIS_ENABLED`). Turning
proactive analysis on is a deliberate operator decision.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_governance import DomainEvent
from app.models.enums import NotificationType, UserStatus
from app.models.ifc import AIInsight
from app.models.project import Project
from app.models.user import User
from app.services.agents.notification_policy import compose_message, decide_notification
from app.services.agents.orchestrator import orchestrate_for_event
from app.services.agents.subscriptions import agents_for_event
from app.services.notification_service import notify

logger = logging.getLogger(__name__)

#: Statuses that mean a person has already dealt with a finding. Re-analysis
#: must never notify about one of these again — being told twice about
#: something you dismissed is how people learn to ignore the channel.
SETTLED_STATUSES = frozenset({"RESOLVED", "DISMISSED", "FALSE_POSITIVE", "ACTIONED"})


def _analysis_principal(db: Session, project_id) -> User | None:
    """The accountable person whose authority an automatic run uses."""
    project = db.get(Project, project_id)
    if not project or not project.project_manager_id:
        return None
    manager = db.get(User, project.project_manager_id)
    if not manager or manager.status != UserStatus.ACTIVE:
        return None
    return manager


def handle_event(db: Session, event: DomainEvent) -> dict:
    """Run the agents that subscribe to this event, and notify where warranted.

    Returns a summary rather than raising. The caller is `process_event`, which
    is inside the transaction of whatever the user was actually doing.
    """
    if not settings.AGENT_AUTO_ANALYSIS_ENABLED:
        return {"ran": False, "reason": "AGENT_AUTO_ANALYSIS_ENABLED is off"}

    subscribed = agents_for_event(event.event_type)
    if not subscribed:
        return {"ran": False, "reason": f"No agent subscribes to {event.event_type}"}

    principal = _analysis_principal(db, event.project_id)
    if principal is None:
        # Deliberately not a fallback. See the module docstring.
        return {
            "ran": False,
            "reason": (
                "This project has no active assigned Project Manager, so there is no "
                "accountable authority for an automatic analysis to run under."
            ),
        }

    report = orchestrate_for_event(
        db, user=principal, project_id=event.project_id,
        event_type=event.event_type, event_id=event.id,
        reason=f"{event.event_type} on {event.entity_type}",
    )
    notified = notify_for_findings(db, project_id=event.project_id, report=report,
                                   recipient=principal)
    return {
        "ran": True, "agentsRun": len(report.ran), "agentsSkipped": len(report.skipped),
        "agentsFailed": len(report.failed), "findingCount": report.finding_count,
        "notified": notified, "principal": str(principal.id),
    }


def notify_for_findings(db: Session, *, project_id, report, recipient: User) -> int:
    """Notify about the findings a pass produced, where policy says to.

    Reads the stored insight rather than the in-memory finding, because the
    stored row is what carries the review status — and a finding that already
    existed and was dismissed must not produce a fresh notification.
    """
    sent = 0
    for run in report.ran:
        for insight_id in run.get("storedInsightIds", []):
            insight = db.get(AIInsight, insight_id)
            if insight is None or insight.status in SETTLED_STATUSES:
                continue
            evidence = insight.evidence_json or {}
            decision = decide_notification(
                certainty=evidence.get("certainty", "DETECTED"),
                confidence=insight.confidence or 0.0,
                severity=insight.severity or "LOW",
            )
            if not decision.notify:
                continue
            claims = evidence.get("claims") or []
            location = (insight.affected_json or {}).get("storey") or None
            created = notify(
                db,
                user_id=recipient.id,
                title=insight.title,
                message=compose_message(
                    finding_title=insight.title,
                    description=insight.description or "",
                    severity=insight.severity or "LOW",
                    confidence=insight.confidence or 0.0,
                    recommended_action=insight.recommended_action or "",
                    agent_title=evidence.get("agentTitle") or "Project analysis",
                    location=location,
                    evidence_count=len(claims),
                ),
                notification_type=NotificationType.SYSTEM,
                category=decision.category,
                priority=decision.priority,
                project_id=project_id,
                entity_type="AI_INSIGHT",
                entity_id=insight.id,
                requires_action=decision.requires_action,
                action_url=f"/projects/{project_id}/ai-intelligence?insight={insight.id}",
                # One notification per finding, ever. Re-analysis refreshes the
                # finding in place; it does not re-announce it.
                dedupe_key=f"agent-finding:{insight.id}",
            )
            if created is not None:
                sent += 1
    return sent


def safe_handle_event(db: Session, event: DomainEvent) -> None:
    """`handle_event`, wrapped so it can never break what triggered it.

    An upload that succeeded must not fail because analysis of it did. The
    failure is logged and the originating operation continues.
    """
    try:
        handle_event(db, event)
    except Exception:
        logger.exception(
            "[Agents] automatic analysis failed for %s on project %s",
            event.event_type, event.project_id,
        )
