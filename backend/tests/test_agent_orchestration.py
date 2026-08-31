"""Orchestration: isolation, observability, subscriptions and controlled coupling.

The Phase 6 suites prove each agent. This proves the layer above them — that a
pass runs the right agents for the right caller, that one agent failing leaves
the others intact, that what happened is recorded, and that the only route
between agents is the tool layer.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.agent_run import AgentRun as AgentRunRecord
from app.models.enums import ProjectStatus, TaskStatus, UserRole, UserStatus
from app.models.ifc import AIInsight
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services.agents import BY_NAME
from app.services.agents.orchestrator import orchestrate, orchestrate_for_event
from app.services.agents.subscriptions import (
    EVENT_COOLDOWN, TriggerType, agents_for_event, decide, event_subscription_map,
)
from app.services.domain_event_dispatcher import IMPORTANT_EVENTS


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def world(db):
    suffix = uuid4().hex[:10]

    def user(name, role):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE)

    manager = user("OrchPm", UserRole.PROJECT_MANAGER)
    outsider = user("OrchOutsider", UserRole.PROJECT_MANAGER)
    site_engineer = user("OrchSiteEngineer", UserRole.ENGINEER)
    owner = user("OrchOwner", UserRole.OWNER)
    db.add_all([manager, outsider, site_engineer, owner])
    db.flush()
    project = Project(name=f"Orch {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    for person, role in ((manager, UserRole.PROJECT_MANAGER), (site_engineer, UserRole.ENGINEER)):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=role, is_active=True))
    db.add(Task(project_id=project.id, task_code="T-001", name="Blocked work",
                status=TaskStatus.BLOCKED, progress_percentage=10,
                created_by_id=manager.id))
    db.commit()
    try:
        yield {"project": project, "manager": manager, "outsider": outsider, "site_engineer": site_engineer}
    finally:
        _purge(db, project.id, [manager.id, outsider.id, site_engineer.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM agent_runs WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insight_sources WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        try:
            db.execute(text(statement), params)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    db.commit()


def run(db, world, actor="manager", **kwargs):
    return orchestrate(db, user=world[actor], project_id=world["project"].id, **kwargs)


# --- A pass runs, and reports each outcome separately ------------------------

def test_a_pass_runs_the_agents_the_caller_may_run(db, world):
    report = run(db, world, persist=False)
    assert report.ran
    assert {item["agent"] for item in report.ran} <= set(BY_NAME)


def test_ran_skipped_and_failed_are_reported_separately(db, world):
    """A skip is not a failure, and a healthy pass must not look broken."""
    payload = run(db, world, persist=False).as_json()
    assert set(payload) >= {"ran", "skipped", "failed", "agentsRun", "agentsSkipped", "agentsFailed"}
    assert payload["agentsFailed"] == 0


def test_an_outsider_gets_an_empty_pass_rather_than_an_error(db, world):
    report = run(db, world, actor="outsider", persist=False)
    assert report.ran == []
    assert report.skipped[0]["skipCode"] == "FORBIDDEN"


def test_agents_the_caller_may_not_run_are_skipped_with_a_reason(db, world):
    report = run(db, world, actor="site_engineer", persist=False)
    for skip in report.skipped:
        assert skip["reason"]
        assert skip["skipCode"] in {"FORBIDDEN", "COOLDOWN", "NOT_SUBSCRIBED", "UNKNOWN_AGENT"}


def test_naming_an_agent_is_not_authority_to_run_it(db, world):
    """An explicit list still goes through the same decision."""
    report = orchestrate(db, user=world["outsider"], project_id=world["project"].id,
                         agents=["schedule_risk_agent"], persist=False)
    assert report.ran == []


def test_an_unknown_agent_is_skipped_not_fatal(db, world):
    report = run(db, world, agents=["schedule_risk_agent", "nonexistent_agent"], persist=False)
    assert {item["agent"] for item in report.ran} == {"schedule_risk_agent"}
    assert any(item["skipCode"] == "UNKNOWN_AGENT" for item in report.skipped)


# --- Failure isolation ------------------------------------------------------

def _break(monkeypatch, name):
    """Replace one agent's analyzer with a failing one.

    `AgentSpec` is frozen on purpose — an agent's grants must not be mutable at
    runtime — so the substitution happens on the registry entry rather than on
    the spec.
    """
    from dataclasses import replace

    from app.services.agents import registry

    def explode(_context):
        raise RuntimeError("analyzer blew up")

    monkeypatch.setitem(registry.BY_NAME, name, replace(registry.BY_NAME[name], analyzer=explode))


def test_one_agent_failing_does_not_stop_the_others(db, world, monkeypatch):
    _break(monkeypatch, "schedule_risk_agent")
    report = run(db, world, persist=False)

    assert any(item["agent"] == "schedule_risk_agent" for item in report.failed)
    assert report.ran, "the other agents must still have produced results"
    assert "schedule_risk_agent" not in {item["agent"] for item in report.ran}


def test_a_persist_failure_is_contained_to_its_own_agent(db, world, monkeypatch):
    """Storing is a separate failure domain from analysing."""
    from app.services.agents import runtime

    original = runtime._store
    calls = {"n": 0}

    def flaky(db_, agent, project_id, finding):
        if agent.name == "schedule_risk_agent":
            raise RuntimeError("database unavailable")
        calls["n"] += 1
        return original(db_, agent, project_id, finding)

    monkeypatch.setattr(runtime, "_store", flaky)
    report = run(db, world, persist=True)
    failed = [item for item in report.failed if item["agent"] == "schedule_risk_agent"]
    assert failed and failed[0]["errorCode"] == "PERSIST_FAILED"
    assert report.ran


def test_a_failed_agent_records_a_failed_run(db, world, monkeypatch):
    _break(monkeypatch, "schedule_risk_agent")
    run(db, world, agents=["schedule_risk_agent"], persist=True)
    record = db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id,
        AgentRunRecord.agent_name == "schedule_risk_agent",
    ).first()
    assert record is not None
    assert record.status == "FAILED"
    assert record.error_code == "AGENT_FAILED"


# --- Observability ----------------------------------------------------------

def test_a_run_is_recorded_with_what_it_did(db, world):
    run(db, world, agents=["schedule_risk_agent"], persist=True)
    record = db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id
    ).first()
    assert record is not None
    assert record.agent_name == "schedule_risk_agent"
    assert record.status == "SUCCEEDED"
    assert record.actor_user_id == world["manager"].id
    assert record.trigger_type == TriggerType.MANUAL
    assert record.trigger_reason
    assert record.tool_calls_json, "the tools it called must be recorded"
    assert record.duration_ms is not None


def test_a_run_that_found_nothing_is_still_recorded(db, world):
    """The outcome that leaves no finding behind, and would otherwise vanish."""
    run(db, world, agents=["rfi_agent"], persist=True)
    record = db.query(AgentRunRecord).filter(
        AgentRunRecord.agent_name == "rfi_agent",
        AgentRunRecord.project_id == world["project"].id,
    ).first()
    assert record is not None
    assert record.status == "SUCCEEDED"


def test_the_record_links_findings_to_the_run_that_made_them(db, world):
    run(db, world, agents=["schedule_risk_agent"], persist=True)
    record = db.query(AgentRunRecord).filter(
        AgentRunRecord.agent_name == "schedule_risk_agent",
        AgentRunRecord.project_id == world["project"].id,
    ).first()
    assert record.finding_count == len(record.finding_codes_json)
    for insight_id in record.insight_ids_json:
        assert db.get(AIInsight, insight_id) is not None


def test_a_preview_pass_records_nothing(db, world):
    run(db, world, persist=False)
    assert db.query(AgentRunRecord).filter(
        AgentRunRecord.project_id == world["project"].id
    ).count() == 0


# --- Subscriptions: architecture without execution --------------------------

def test_every_declared_subscription_maps_to_a_real_event():
    for event, agents in event_subscription_map().items():
        assert event in IMPORTANT_EVENTS
        assert agents


def test_an_event_resolves_to_the_agents_that_want_it():
    assert "document_consistency_agent" in agents_for_event("DOCUMENT_UPLOADED")
    assert "revision_impact_agent" in agents_for_event("IFC_REVISION_CREATED")
    assert "schedule_risk_agent" in agents_for_event("TASK_PROGRESS_CHANGED")


def test_an_unsubscribed_event_wakes_nobody():
    assert agents_for_event("SOMETHING_NOBODY_LISTENS_FOR") == []


def test_an_event_pass_runs_only_the_subscribed_agents(db, world):
    report = orchestrate_for_event(
        db, user=world["manager"], project_id=world["project"].id,
        event_type="TASK_PROGRESS_CHANGED",
    )
    assert {item["agent"] for item in report.ran} <= set(agents_for_event("TASK_PROGRESS_CHANGED"))


def test_an_agent_is_not_run_for_an_event_it_did_not_subscribe_to(db, world):
    decision = decide(db, user=world["manager"], project_id=world["project"].id,
                      agent_name="rfi_agent", trigger_type=TriggerType.EVENT,
                      event_type="TASK_PROGRESS_CHANGED")
    assert decision.should_run is False
    assert decision.skip_code == "NOT_SUBSCRIBED"


def test_a_burst_of_events_does_not_re_run_the_same_agent(db, world):
    """Ten uploads in a minute is one action by a person, not ten analyses."""
    first = orchestrate_for_event(db, user=world["manager"], project_id=world["project"].id,
                                  event_type="TASK_PROGRESS_CHANGED")
    assert first.ran
    second = orchestrate_for_event(db, user=world["manager"], project_id=world["project"].id,
                                   event_type="TASK_PROGRESS_CHANGED")
    assert second.ran == []
    assert any(item["skipCode"] == "COOLDOWN" for item in second.skipped)


def test_a_manual_run_ignores_the_cooldown(db, world):
    """A person asking for analysis has a reason."""
    orchestrate_for_event(db, user=world["manager"], project_id=world["project"].id,
                          event_type="TASK_PROGRESS_CHANGED")
    manual = run(db, world, agents=["schedule_risk_agent"], persist=True)
    assert manual.ran


def test_the_cooldown_expires(db, world):
    orchestrate_for_event(db, user=world["manager"], project_id=world["project"].id,
                          event_type="TASK_PROGRESS_CHANGED")
    later = datetime.now(timezone.utc) + EVENT_COOLDOWN + timedelta(minutes=1)
    decision = decide(db, user=world["manager"], project_id=world["project"].id,
                      agent_name="schedule_risk_agent", trigger_type=TriggerType.EVENT,
                      event_type="TASK_PROGRESS_CHANGED", now=later)
    assert decision.should_run is True


def test_permission_is_checked_before_anything_that_reveals_activity(db, world):
    """A refusal must not depend on whether the project has recent runs."""
    decision = decide(db, user=world["outsider"], project_id=world["project"].id,
                      agent_name="schedule_risk_agent", trigger_type=TriggerType.EVENT,
                      event_type="TASK_PROGRESS_CHANGED")
    assert decision.skip_code == "FORBIDDEN"


def test_the_dispatcher_hook_is_gated_rather_than_absent(db, world):
    """Phase 7 built the architecture; Phase 8 wired it, deliberately.

    This test previously asserted the dispatcher contained no agent wiring at
    all — a tripwire whose job was to make adding that hook a decision rather
    than a drift. Phase 8 made the decision, so the assertion now guards what
    actually matters about the hook: that it is switched off by default and
    that it cannot take down the event processing it runs inside.
    """
    import app.services.domain_event_dispatcher as dispatcher
    from app.core.config import Settings

    with open(dispatcher.__file__, encoding="utf-8") as handle:
        body = handle.read()
    assert "safe_handle_event" in body, "the hook must go through the wrapped entry point"
    assert "handle_event(db, event)" not in body.replace("safe_handle_event(db, event)", ""),         "the dispatcher must never call the unwrapped handler"
    assert Settings.model_fields["AGENT_AUTO_ANALYSIS_ENABLED"].default is False


# --- Controlled agent-to-agent ----------------------------------------------

def test_cross_agent_reading_goes_through_the_tool_layer(db, world):
    """The only sanctioned coupling: a tool call, not a direct call."""
    assert "get_findings" in BY_NAME["schedule_risk_agent"].allowed_tools
    assert "get_findings" in BY_NAME["revision_impact_agent"].allowed_tools


def test_an_agent_without_the_grant_cannot_read_findings(db, world):
    from app.services.agents.context import AgentContext

    context = AgentContext(db=db, user=world["manager"], project_id=world["project"].id,
                           agent=BY_NAME["rfi_agent"])
    result = context.call("get_findings", {})
    assert result.ok is False
    assert result.error_code == "TOOL_NOT_GRANTED"


def test_reading_findings_still_requires_the_callers_own_permission(db, world):
    from app.services.agents.context import AgentContext

    context = AgentContext(db=db, user=world["outsider"], project_id=world["project"].id,
                           agent=BY_NAME["schedule_risk_agent"])
    result = context.call("get_findings", {})
    assert result.ok is False
    assert result.error_code == "FORBIDDEN"


def test_the_schedule_agent_can_see_the_site_agents_conclusions(db, world):
    from app.services.agents.context import AgentContext

    context = AgentContext(db=db, user=world["manager"], project_id=world["project"].id,
                           agent=BY_NAME["schedule_risk_agent"])
    result = context.call("get_findings", {"sourceEngine": "SITE_REPORT_AGENT_V1"})
    assert result.ok is True
    assert "findings" in result.data


# --- Still no writes --------------------------------------------------------

def test_an_orchestrated_pass_changes_no_project_data(db, world):
    before = db.query(Task).filter(Task.project_id == world["project"].id).count()
    run(db, world, persist=True)
    db.expire_all()
    assert db.query(Task).filter(Task.project_id == world["project"].id).count() == before


def test_repeating_a_pass_does_not_multiply_findings(db, world):
    run(db, world, persist=True)
    first = db.query(AIInsight).filter(AIInsight.project_id == world["project"].id).count()
    run(db, world, persist=True)
    assert db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id
    ).count() == first
