"""Running the five project agents.

Deliberately small. The agents produce `AIInsight` rows, so everything after a
run — listing, filtering, reviewing, promoting a finding into an issue or a
task — is already served by `/ai-intelligence`. Adding a second review surface
here would have split the queue in two.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.user import User
from app.models.agent_run import AgentRun as AgentRunRecord
from app.services.agents import agent_definitions, available_agents, run_agent, run_all
from app.services.agents.orchestrator import orchestrate
from app.services.agents.subscriptions import TriggerType, event_subscription_map

router = APIRouter(prefix="/projects/{project_id}/agents", tags=["Project Agents"])


@router.get("")
def list_agents(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The agents this caller may run here, and the full catalogue for reference."""
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    return {
        "available": available_agents(db, user=current_user, project_id=project_id),
        "catalogue": agent_definitions(),
    }


@router.post("/{agent_name}/run")
def run_one(
    project_id: uuid.UUID,
    agent_name: str,
    persist: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run one agent. Findings are stored for review, never acted on."""
    result = run_agent(db, user=current_user, project_id=project_id, name=agent_name, persist=persist)
    if not result.ok:
        raise HTTPException(
            status_code=403 if result.error_code == "FORBIDDEN" else 404
            if result.error_code == "UNKNOWN_AGENT" else 500,
            detail=result.error,
        )
    return result.as_json()


@router.post("/run")
def run_every_agent(
    project_id: uuid.UUID,
    persist: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run every agent this caller may run."""
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    return {"runs": [item.as_json() for item in run_all(
        db, user=current_user, project_id=project_id, persist=persist,
    )]}


@router.post("/orchestrate")
def orchestrate_agents(
    project_id: uuid.UUID,
    persist: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run every agent this caller may run, as one governed pass.

    Each agent is isolated: one failing leaves the others' results intact, and
    the response reports ran / skipped / failed separately so a skip is never
    mistaken for a failure.
    """
    return orchestrate(
        db, user=current_user, project_id=project_id,
        trigger_type=TriggerType.MANUAL, persist=persist,
    ).as_json()


@router.get("/runs")
def list_agent_runs(
    project_id: uuid.UUID,
    agent_name: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The run history: which agent ran, why, what it called, what it produced."""
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(AgentRunRecord).filter(AgentRunRecord.project_id == project_id)
    if agent_name:
        query = query.filter(AgentRunRecord.agent_name == agent_name)
    runs = query.order_by(AgentRunRecord.created_at.desc()).limit(min(limit, 200)).all()
    return {"runs": [
        {
            "id": str(run.id), "agent": run.agent_name, "status": run.status,
            "triggerType": run.trigger_type, "triggerReason": run.trigger_reason,
            "findingCount": run.finding_count, "findingCodes": run.finding_codes_json,
            "highestConfidence": run.highest_confidence,
            "toolCalls": run.tool_calls_json, "insightIds": run.insight_ids_json,
            "durationMs": run.duration_ms, "errorCode": run.error_code, "error": run.error,
            "createdAt": run.created_at.isoformat() if run.created_at else None,
        }
        for run in runs
    ]}


@router.get("/subscriptions")
def list_subscriptions(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Which domain events would wake which agents, and whether they will.

    The docstring here used to say nothing was wired to the dispatcher. That
    stopped being true: `domain_event_dispatcher.process_event` calls
    `agents.event_subscriber.safe_handle_event`, and every declared event type
    now has an emission site. What remains between "declared" and "running" is
    one operator switch, so that is what this reports — a client showing the
    subscription map needs to be able to say whether it describes what happens
    or only what would happen.
    """
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    enabled = settings.AGENT_AUTO_ANALYSIS_ENABLED
    return {
        "subscriptions": event_subscription_map(),
        "automaticAnalysisEnabled": enabled,
        "note": (
            "These events trigger analysis automatically on this server."
            if enabled
            else (
                "Declared subscriptions. Automatic analysis is switched off "
                "(AGENT_AUTO_ANALYSIS_ENABLED), so agents run only when requested."
            )
        ),
    }
