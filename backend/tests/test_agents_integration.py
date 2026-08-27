"""The five agents against a real project, with real roles and real records.

The contract suite proves the shapes. This proves the wiring: that an agent
reaches real data through the tool layer, that what it reports is backed by
records that exist, that a caller who may not see something gets an agent that
cannot see it either, and that nothing an agent concludes changes the project.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.models.collaboration import AIInsightSource
from app.models.design_change import DesignChange, DesignChangeAffectedDiscipline
from app.models.enums import (
    DesignChangeStatus, ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.ifc import AIInsight
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.db.database import SessionLocal
from app.services.agents import BY_NAME, Certainty, available_agents, run_agent, run_all
from app.services.agents.runtime import AGENT_CATEGORY


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
    """A project carrying exactly the conditions the agents look for."""
    suffix = uuid4().hex[:10]
    today = date.today()

    def user(name, role):
        return User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                    hashed_password="x", role=role, status=UserStatus.ACTIVE)

    manager = user("AgentPm", UserRole.PROJECT_MANAGER)
    outsider = user("AgentOutsider", UserRole.PROJECT_MANAGER)
    worker = user("AgentWorker", UserRole.WORKER)
    owner = user("AgentOwner", UserRole.OWNER)
    db.add_all([manager, outsider, worker, owner])
    db.flush()

    project = Project(name=f"Agents {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    db.add(project)
    db.flush()
    for person, role in ((manager, UserRole.PROJECT_MANAGER), (worker, UserRole.WORKER)):
        db.add(ProjectMember(project_id=project.id, user_id=person.id,
                             role_on_project=role, is_active=True))

    overdue = Task(project_id=project.id, task_code="T-001", name="Pour ground slab",
                   status=TaskStatus.IN_PROGRESS, progress_percentage=20,
                   planned_start_date=today - timedelta(days=40),
                   planned_end_date=today - timedelta(days=5), created_by_id=manager.id)
    blocked = Task(project_id=project.id, task_code="T-002", name="Erect steel frame",
                   status=TaskStatus.BLOCKED, progress_percentage=10,
                   planned_start_date=today - timedelta(days=20),
                   planned_end_date=today + timedelta(days=10), created_by_id=manager.id)
    db.add_all([overdue, blocked])
    db.flush()

    # Three reports naming a delay, one of them claiming progress the task denies.
    reports = []
    for index in range(3):
        reports.append(SiteReport(
            project_id=project.id, task_id=overdue.id, submitted_by_id=manager.id,
            report_date=today - timedelta(days=index), review_status="submitted",
            work_completed="Formwork continued",
            delays="Concrete delivery delayed again; crane unavailable",
            issues_summary="Concrete delivery delayed again; crane unavailable",
            progress_percentage_reported=80 if index == 0 else None,
        ))
    empty_report = SiteReport(
        project_id=project.id, submitted_by_id=manager.id,
        report_date=today - timedelta(days=5), review_status="submitted",
    )
    db.add_all([*reports, empty_report])

    change = DesignChange(
        project_id=project.id, title="Relocate riser shaft",
        description="Shaft moves 600mm east", reason="Clash with beam",
        source_discipline="STRUCTURAL", proposed_by_id=manager.id,
        status=DesignChangeStatus.PROPOSED, expected_schedule_impact_days=10,
        task_id=blocked.id,
    )
    db.add(change)
    db.flush()
    db.add(DesignChangeAffectedDiscipline(design_change_id=change.id, discipline="MECHANICAL"))
    db.commit()
    # Age it past the overdue threshold without relying on wall-clock time.
    db.execute(text("UPDATE design_changes SET created_at = now() - interval '20 days' WHERE id = :id"),
               {"id": change.id})
    db.commit()
    try:
        yield {"project": project, "manager": manager, "outsider": outsider,
               "worker": worker, "overdue": overdue, "blocked": blocked, "change": change}
    finally:
        _purge(db, project.id, [manager.id, outsider.id, worker.id, owner.id])


def _purge(db, project_id, user_ids):
    db.rollback()
    params = {"projects": [project_id], "users": list(user_ids)}
    for statement in (
        "DELETE FROM ai_insight_sources WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_insights WHERE project_id = ANY(:projects)",
        "DELETE FROM design_change_affected_disciplines WHERE design_change_id IN (SELECT id FROM design_changes WHERE project_id = ANY(:projects))",
        "DELETE FROM design_changes WHERE project_id = ANY(:projects) OR proposed_by_id = ANY(:users)",
        "DELETE FROM site_reports WHERE project_id = ANY(:projects) OR submitted_by_id = ANY(:users)",
        "DELETE FROM task_assignees WHERE task_id IN (SELECT id FROM tasks WHERE project_id = ANY(:projects))",
        "DELETE FROM tasks WHERE project_id = ANY(:projects) OR created_by_id = ANY(:users)",
        "DELETE FROM issues WHERE project_id = ANY(:projects) OR raised_by_id = ANY(:users)",
        "DELETE FROM notifications WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        # Committed one at a time on purpose. Sharing a transaction means a
        # single failing statement rolls back every delete before it, silently
        # — which is how a fixture leaves eleven projects behind while
        # appearing to clean up.
        try:
            db.execute(text(statement), params)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    db.commit()


def run(db, world, agent, actor="manager", persist=True):
    return run_agent(db, user=world[actor], project_id=world["project"].id,
                     name=agent, persist=persist)


def codes(result):
    return {finding.code for finding in result.findings}


# --- Each agent runs and reports something grounded -------------------------

@pytest.mark.parametrize("agent", sorted(BY_NAME))
def test_every_agent_runs_without_error(db, world, agent):
    result = run(db, world, agent, persist=False)
    assert result.ok is True, result.error


@pytest.mark.parametrize("agent", sorted(BY_NAME))
def test_every_agent_reaches_the_platform_only_through_tools(db, world, agent):
    result = run(db, world, agent, persist=False)
    assert result.tool_calls, f"{agent} read nothing through the tool layer"
    granted = set(BY_NAME[agent].allowed_tools)
    assert {call["tool"] for call in result.tool_calls} <= granted


@pytest.mark.parametrize("agent", sorted(BY_NAME))
def test_every_finding_carries_evidence_or_declares_uncertainty(db, world, agent):
    for finding in run(db, world, agent, persist=False).findings:
        if finding.certainty is Certainty.UNCERTAIN:
            continue
        assert finding.evidence, f"{agent}/{finding.code} asserts without evidence"


# --- The findings each agent exists to make ---------------------------------

def test_the_site_report_agent_finds_the_reported_delays(db, world):
    result = run(db, world, "site_report_agent", persist=False)
    assert "SITE_REPORTED_DELAYS" in codes(result)
    delay = next(f for f in result.findings if f.code == "SITE_REPORTED_DELAYS")
    assert delay.certainty is Certainty.FACT
    assert delay.confidence == 1.0


def test_the_site_report_agent_notices_the_empty_report(db, world):
    assert "SITE_REPORTS_MISSING_CONTENT" in codes(run(db, world, "site_report_agent", persist=False))


def test_the_site_report_agent_flags_progress_the_task_does_not_show(db, world):
    result = run(db, world, "site_report_agent", persist=False)
    conflict = next((f for f in result.findings if f.code == "SITE_PROGRESS_CONFLICT"), None)
    assert conflict is not None
    assert conflict.related_task_ids == [str(world["overdue"].id)]


def test_a_recurring_site_issue_is_inferred_not_asserted(db, world):
    result = run(db, world, "site_report_agent", persist=False)
    recurring = next((f for f in result.findings if f.code == "SITE_RECURRING_ISSUE"), None)
    if recurring:
        assert recurring.certainty is Certainty.INFERRED
        assert recurring.confidence <= 0.7


def test_the_schedule_agent_finds_overdue_and_blocked_work(db, world):
    found = codes(run(db, world, "schedule_risk_agent", persist=False))
    assert "SCHEDULE_TASKS_OVERDUE" in found
    assert "SCHEDULE_TASKS_BLOCKED" in found


def test_the_rfi_agent_finds_the_overdue_request(db, world):
    result = run(db, world, "rfi_agent", persist=False)
    assert "RFI_OVERDUE" in codes(result)
    overdue = next(f for f in result.findings if f.code == "RFI_OVERDUE")
    assert overdue.evidence[0].source_type == "DESIGN_CHANGE"
    # The agent must be explicit that it is reading design changes.
    assert "design change" in overdue.description.casefold()


def test_the_revision_agent_reports_the_declared_schedule_impact(db, world):
    result = run(db, world, "revision_impact_agent", persist=False)
    impact = next((f for f in result.findings if f.code == "REVISION_DECLARES_SCHEDULE_IMPACT"), None)
    assert impact is not None
    assert impact.certainty is Certainty.FACT
    assert "10" in impact.title


def test_the_revision_agent_labels_a_linked_task_as_inference(db, world):
    result = run(db, world, "revision_impact_agent", persist=False)
    linked = next((f for f in result.findings if f.code == "REVISION_LINKED_TASK_AT_RISK"), None)
    assert linked is not None
    assert linked.certainty is Certainty.INFERRED
    assert linked.confidence <= 0.7


def test_the_document_agent_reports_uncertainty_when_there_are_no_documents(db, world):
    result = run(db, world, "document_consistency_agent", persist=False)
    assert result.findings
    assert all(f.certainty is Certainty.UNCERTAIN for f in result.findings)
    assert "DOCUMENTS_UNAVAILABLE" in codes(result)


def test_missing_evidence_produces_uncertainty_rather_than_silence(db, world):
    """"Nothing found" and "could not look" must not be the same answer."""
    uncertain = next(f for f in run(db, world, "document_consistency_agent", persist=False).findings)
    assert uncertain.certainty is Certainty.UNCERTAIN
    assert uncertain.confidence <= 0.3


# --- RBAC cannot be bypassed ------------------------------------------------

@pytest.mark.parametrize("agent", sorted(BY_NAME))
def test_an_outsider_cannot_run_any_agent(db, world, agent):
    result = run(db, world, agent, actor="outsider")
    assert result.ok is False
    assert result.error_code == "FORBIDDEN"


def test_an_unknown_agent_is_refused(db, world):
    result = run(db, world, "rogue_agent")
    assert result.ok is False
    assert result.error_code == "UNKNOWN_AGENT"


def test_the_agent_list_reflects_the_callers_permissions(db, world):
    manager = {item["name"] for item in available_agents(
        db, user=world["manager"], project_id=world["project"].id)}
    worker = {item["name"] for item in available_agents(
        db, user=world["worker"], project_id=world["project"].id)}
    assert manager
    assert worker <= manager


def test_an_outsider_is_offered_no_agents(db, world):
    assert available_agents(db, user=world["outsider"], project_id=world["project"].id) == []


def test_an_agent_cannot_call_a_tool_it_was_not_granted(db, world):
    """The containment a prompt cannot argue its way past."""
    from app.services.agents.context import AgentContext

    context = AgentContext(db=db, user=world["manager"], project_id=world["project"].id,
                           agent=BY_NAME["schedule_risk_agent"])
    result = context.call("search_documents", {"query": "contract"})
    assert result.ok is False
    assert result.error_code == "TOOL_NOT_GRANTED"


def test_a_granted_tool_still_obeys_the_callers_own_permissions(db, world):
    """Two gates: the grant, and then the caller's own rights."""
    from app.services.agents.context import AgentContext

    context = AgentContext(db=db, user=world["outsider"], project_id=world["project"].id,
                           agent=BY_NAME["schedule_risk_agent"])
    result = context.call("get_tasks")
    assert result.ok is False
    assert result.error_code == "FORBIDDEN"


# --- Nothing is written to the project --------------------------------------

@pytest.mark.parametrize("agent", sorted(BY_NAME))
def test_running_an_agent_changes_no_project_data(db, world, agent):
    before = (
        db.query(Task).filter(Task.project_id == world["project"].id).count(),
        db.query(SiteReport).filter(SiteReport.project_id == world["project"].id).count(),
        db.query(DesignChange).filter(DesignChange.project_id == world["project"].id).count(),
    )
    run(db, world, agent)
    db.expire_all()
    after = (
        db.query(Task).filter(Task.project_id == world["project"].id).count(),
        db.query(SiteReport).filter(SiteReport.project_id == world["project"].id).count(),
        db.query(DesignChange).filter(DesignChange.project_id == world["project"].id).count(),
    )
    assert before == after


def test_a_task_the_agent_reported_on_is_untouched(db, world):
    run(db, world, "schedule_risk_agent")
    db.refresh(world["overdue"])
    assert world["overdue"].progress_percentage == 20
    assert world["overdue"].status is TaskStatus.IN_PROGRESS


# --- Findings land where a person already reviews them -----------------------

def test_findings_are_stored_as_reviewable_insights(db, world):
    result = run(db, world, "schedule_risk_agent")
    assert result.stored_insight_ids
    stored = db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id,
        AIInsight.category == AGENT_CATEGORY,
    ).all()
    assert stored
    assert all(item.status == "NEW" for item in stored)
    assert all(item.source_engine == "SCHEDULE_RISK_AGENT_V1" for item in stored)


def test_a_stored_finding_keeps_its_certainty_and_its_claims(db, world):
    run(db, world, "site_report_agent")
    insight = db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id,
        AIInsight.insight_type == "SITE_REPORTED_DELAYS",
    ).first()
    assert insight is not None
    assert insight.evidence_json["certainty"] == "FACT"
    assert insight.evidence_json["claims"]
    assert insight.evidence_json["agent"] == "site_report_agent"


def test_sources_are_registered_so_a_finding_can_be_traced(db, world):
    run(db, world, "site_report_agent")
    sources = db.query(AIInsightSource).filter(
        AIInsightSource.project_id == world["project"].id
    ).all()
    assert sources, "no citations were registered"
    assert {source.source_type for source in sources} & {"SITE_REPORT", "TASK"}


def test_re_running_updates_rather_than_duplicating(db, world):
    first = run(db, world, "schedule_risk_agent")
    second = run(db, world, "schedule_risk_agent")
    assert set(first.stored_insight_ids) == set(second.stored_insight_ids)


def test_a_reviewed_finding_is_not_reopened_by_a_later_run(db, world):
    run(db, world, "schedule_risk_agent")
    insight = db.query(AIInsight).filter(
        AIInsight.project_id == world["project"].id,
        AIInsight.insight_type == "SCHEDULE_TASKS_BLOCKED",
    ).first()
    insight.status = "RESOLVED"
    db.commit()

    run(db, world, "schedule_risk_agent")
    db.refresh(insight)
    assert insight.status == "RESOLVED"


def test_preview_mode_stores_nothing(db, world):
    before = db.query(AIInsight).filter(AIInsight.project_id == world["project"].id).count()
    result = run(db, world, "schedule_risk_agent", persist=False)
    assert result.findings
    assert result.stored_insight_ids == []
    assert db.query(AIInsight).filter(AIInsight.project_id == world["project"].id).count() == before


def test_running_every_agent_returns_one_run_each(db, world):
    runs = run_all(db, user=world["manager"], project_id=world["project"].id, persist=False)
    assert {item.agent for item in runs} <= set(BY_NAME)
    assert all(item.ok for item in runs)
