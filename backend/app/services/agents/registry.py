"""The five agents. Fixed set, declared here and nowhere else.

Each row states the whole of what an agent may do: the tools it holds, the
permission its caller needs, the engine name its findings carry, and the domain
events that should eventually wake it. Nothing is discovered at runtime.

The tool grants are deliberately narrow. An agent is given what its
responsibility needs and nothing more, so a prompt injection or a coding
mistake in one analyzer cannot reach data that agent was never meant to see —
the Schedule Risk Agent holds no document tools at all.
"""

from __future__ import annotations

from app.services.agents import analyzers
from app.services.agents.contracts import AgentSpec

SITE_REPORT_AGENT = AgentSpec(
    name="site_report_agent",
    title="Site Report Agent",
    responsibility=(
        "Analyse filed site reports and field information for delays, recurring "
        "problems, missing detail and progress that conflicts with the task record."
    ),
    allowed_tools=("get_site_reports", "get_site_report", "get_tasks", "get_issues",
                   "get_project_status"),
    permission_code="site_report.submit",
    source_engine="SITE_REPORT_AGENT_V1",
    subscribes_to=("FIELD_SUBMISSION_CREATED", "FIELD_SUBMISSION_VERIFIED"),
    analyzer=analyzers.site_report_agent,
)

DOCUMENT_CONSISTENCY_AGENT = AgentSpec(
    name="document_consistency_agent",
    title="Document Consistency Agent",
    responsibility=(
        "Establish which project documents are actually related, then check those "
        "for inconsistency, misfiling and content that cannot be verified."
    ),
    allowed_tools=("search_documents", "get_document", "query_project_knowledge"),
    permission_code="task.view",
    source_engine="DOCUMENT_CONSISTENCY_AGENT_V1",
    subscribes_to=("DOCUMENT_UPLOADED",),
    analyzer=analyzers.document_consistency_agent,
)

REVISION_IMPACT_AGENT = AgentSpec(
    name="revision_impact_agent",
    title="Revision Impact Agent",
    responsibility=(
        "When a model revision or design change appears, identify what it may affect "
        "— always with the evidence that links the two."
    ),
    allowed_tools=("analyze_ifc", "query_ifc", "get_design_changes", "get_tasks",
                   "search_documents", "get_findings"),
    permission_code="ifc.view",
    source_engine="REVISION_IMPACT_AGENT_V1",
    subscribes_to=("IFC_UPLOADED", "IFC_REVISION_CREATED", "DESIGN_CHANGE_CREATED"),
    analyzer=analyzers.revision_impact_agent,
)

RFI_AGENT = AgentSpec(
    name="rfi_agent",
    title="RFI Agent",
    responsibility=(
        "Track requests for information — which this platform records as design "
        "changes — for unanswered and overdue requests and recurring clarification areas."
    ),
    allowed_tools=("get_design_changes", "get_project_users", "search_documents",
                   "query_project_knowledge"),
    permission_code="design_change.propose",
    source_engine="RFI_AGENT_V1",
    subscribes_to=("DESIGN_CHANGE_CREATED", "CONSULTANT_REVIEW_COMPLETED"),
    analyzer=analyzers.rfi_agent,
)

SCHEDULE_RISK_AGENT = AgentSpec(
    name="schedule_risk_agent",
    title="Schedule Risk Agent",
    responsibility=(
        "Identify schedule risk on top of the platform's existing scheduling data: "
        "overdue, stalled, blocked and undated work. It does not recompute the "
        "critical path or reschedule anything."
    ),
    allowed_tools=("get_tasks", "get_project_status", "get_site_reports", "get_findings"),
    permission_code="schedule.view",
    source_engine="SCHEDULE_RISK_AGENT_V1",
    subscribes_to=("TASK_UPDATED", "TASK_PROGRESS_CHANGED", "TASK_COMPLETED"),
    analyzer=analyzers.schedule_risk_agent,
)

AGENTS: tuple[AgentSpec, ...] = (
    SITE_REPORT_AGENT,
    DOCUMENT_CONSISTENCY_AGENT,
    REVISION_IMPACT_AGENT,
    RFI_AGENT,
    SCHEDULE_RISK_AGENT,
)

BY_NAME: dict[str, AgentSpec] = {agent.name: agent for agent in AGENTS}


def agent_definitions() -> list[dict]:
    return [agent.as_definition() for agent in AGENTS]
