"""The tool table. One row per operation an AI system may reach.

Adding a tool means adding a row here, which forces the three decisions that
matter to be made explicitly and in one place: what its arguments are, which
permission governs it, and whether it reads or proposes. A handler that exists
without a row is unreachable, which is the intended direction — a tool must be
declared before it can be called, never discovered by reflection.
"""

from __future__ import annotations

from app.services.ai_tools import arguments as args
from app.services.ai_tools import read_tools, write_tools
from app.services.ai_tools.contracts import ToolKind, ToolSpec

TOOLS: tuple[ToolSpec, ...] = (
    # -- reads ---------------------------------------------------------------
    ToolSpec(
        "get_project", ToolKind.READ,
        "Basic facts about the project: name, status, type, location and dates.",
        args.NoArguments, "task.view",
        handler=read_tools.get_project,
        authorization_note="Project membership is checked by the runtime before this runs.",
    ),
    ToolSpec(
        "get_project_status", ToolKind.READ,
        "Progress snapshot: task counts by status, completion and overdue work. "
        "Covers only work the caller is authorized to see.",
        args.NoArguments, "task.view",
        handler=read_tools.get_project_status,
        authorization_note="Built from `authorized_voice_tasks`, so it cannot report on hidden work.",
    ),
    ToolSpec(
        "get_tasks", ToolKind.READ,
        "List tasks, optionally filtered by status or assignee.",
        args.GetTasksArguments, "task.view",
        handler=read_tools.get_tasks,
        authorization_note="Scoped to the caller's authorized task list.",
    ),
    ToolSpec(
        "get_task", ToolKind.READ,
        "One task by id, including its description.",
        args.TaskIdArgument, "task.view",
        handler=read_tools.get_task,
        authorization_note="Resolved from the caller's own list; an unauthorized task reads as not found.",
    ),
    ToolSpec(
        "get_issues", ToolKind.READ,
        "Open and recent issues raised on the project.",
        args.NoArguments, "task.view",
        handler=read_tools.get_issues,
        authorization_note="Project-scoped; issues are visible to project members.",
    ),
    ToolSpec(
        "get_project_users", ToolKind.READ,
        "Active members of the project and their roles, for assignment and messaging.",
        args.NoArguments, "task.view",
        handler=read_tools.get_project_users,
        authorization_note="Lists membership of the project the caller already has access to.",
    ),
    ToolSpec(
        "get_site_reports", ToolKind.READ,
        "Recent site reports filed on the project, newest first.",
        args.GetSiteReportsArguments, "site_report.submit",
        handler=read_tools.get_site_reports,
        authorization_note="Project-scoped; gated on the site-report permission.",
    ),
    ToolSpec(
        "search_documents", ToolKind.READ,
        "Find project documents by title or notes. Returns metadata, not content.",
        args.SearchDocumentsArguments, None,
        handler=read_tools.search_documents,
        authorization_note=(
            "No catalogue permission because document visibility is per-document, not "
            "per-project: `readable_document_ids` applies the owner and consultant "
            "scopes the documents API applies, and this cannot widen them."
        ),
    ),
    ToolSpec(
        "get_document", ToolKind.READ,
        "Metadata and classification for one document, including its index status.",
        args.DocumentIdArgument, None,
        handler=read_tools.get_document,
        authorization_note=(
            "Same per-document scoping as `search_documents`; an unreadable document "
            "reads as not found."
        ),
    ),
    ToolSpec(
        "query_project_knowledge", ToolKind.READ,
        "Ask a question about the project. Routes to project records, site reports, "
        "the IFC model or document retrieval, and returns the answer with citations.",
        args.QueryKnowledgeArguments, None,
        handler=read_tools.query_project_knowledge,
        authorization_note=(
            "Each source applies its own scoping — authorized tasks, readable documents, "
            "IFC view permission — so this is never wider than its narrowest source."
        ),
    ),
    ToolSpec(
        "query_ifc", ToolKind.READ,
        "Ask about model elements or coordination findings: what an element is, or "
        "what conflicts with it.",
        args.QueryIFCArguments, "ifc.view",
        handler=read_tools.query_ifc,
        authorization_note="Requires the same IFC view permission the workspace requires.",
    ),
    ToolSpec(
        "analyze_ifc", ToolKind.READ,
        "Report the stored analysis of an IFC revision: statistics, disciplines and "
        "coordination findings. Does not re-run processing.",
        args.AnalyzeIFCArguments, "ifc.view",
        handler=read_tools.analyze_ifc,
        authorization_note="Read-only despite the name; processing is never triggered by a tool call.",
    ),

    ToolSpec(
        "get_site_report", ToolKind.READ,
        "One site report in full: completed work, work in progress, delays, issues, "
        "reported progress and weather.",
        args.SiteReportIdArgument, "site_report.submit",
        handler=read_tools.get_site_report,
        authorization_note="Project-scoped; a report from another project reads as not found.",
    ),
    ToolSpec(
        "get_design_changes", ToolKind.READ,
        "Design changes on the project, including declared cost and schedule impact. "
        "This platform records requests for information as design changes; there is no "
        "separate RFI entity.",
        args.GetDesignChangesArguments, "design_change.propose",
        handler=read_tools.get_design_changes,
        authorization_note="Project-scoped and gated on the design-change permission.",
    ),

    ToolSpec(
        "get_findings", ToolKind.READ,
        "Existing AI findings on the project — from the rule engines or from other "
        "agents. Returns type, severity, confidence, certainty and affected entities.",
        args.GetFindingsArguments, "ai.view_insights",
        handler=read_tools.get_findings,
        authorization_note=(
            "Gated on the same permission the review queue uses. This is the only "
            "route by which one agent reaches another's conclusions; direct "
            "agent-to-agent calls are not permitted."
        ),
    ),

    # -- proposals -----------------------------------------------------------
    ToolSpec(
        "create_task", ToolKind.PROPOSE,
        "Propose a new task. Returns a proposal for a human to confirm; nothing is created.",
        args.CreateTaskArguments, "task.create",
        handler=write_tools.create_task,
        authorization_note="Pre-checked against the voice capability registry; executed only after confirmation.",
    ),
    ToolSpec(
        "update_task", ToolKind.PROPOSE,
        "Propose a change to a task's progress, status or notes. Returns a proposal "
        "for a human to confirm; nothing is changed.",
        args.UpdateTaskArguments, "task.update_progress",
        handler=write_tools.update_task,
        authorization_note="Resolves to the specific capability governing the field being changed.",
    ),
    ToolSpec(
        "create_issue", ToolKind.PROPOSE,
        "Propose raising an issue. Returns a proposal for a human to confirm.",
        args.CreateIssueArguments, "issue.create",
        handler=write_tools.create_issue,
        authorization_note="Pre-checked against the voice capability registry.",
    ),
    ToolSpec(
        "update_issue", ToolKind.PROPOSE,
        "Propose changing an issue's status or assignee. Returns a proposal to confirm.",
        args.UpdateIssueArguments, "issue.create",
        handler=write_tools.update_issue,
        authorization_note="Pre-checked against the voice capability registry.",
    ),
    ToolSpec(
        "send_message", ToolKind.PROPOSE,
        "Propose a message to a project member. Returns a proposal to confirm; "
        "nothing is sent.",
        args.SendMessageArguments, None,
        handler=write_tools.send_message,
        authorization_note=(
            "Messaging has no catalogue permission because the messaging service decides "
            "per recipient at send time. This proposes only; it never sends."
        ),
    ),
)

BY_NAME: dict[str, ToolSpec] = {tool.name: tool for tool in TOOLS}


def tool_definitions() -> list[dict]:
    """Every tool's public contract, for an agent framework to render."""
    return [tool.as_definition() for tool in TOOLS]
