"""Read handlers. Every one delegates to something that already existed.

None of these queries is new. Task scoping comes from `authorized_voice_tasks`,
document scoping from `readable_document_ids`, IFC from `ifc_knowledge` and the
Phase 2 tables, project knowledge from the Phase 4 router. Writing fresh
queries here would have created a second, unaudited definition of what each
role can see — which is exactly the bypass this layer must not be.
"""

from __future__ import annotations

from app.models.design_change import DesignChange
from app.models.document import Document
from app.models.ifc import AIInsight, IFCCoordinationFinding, IFCModelVersion
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.schemas.voice_analysis import DetectedQuery, VoiceQueryTopic
from app.services import rag
from app.services.ai_tools.contracts import ToolError
from app.services.document_access import readable_document_ids
from app.services.ifc_knowledge import answer_ifc_question
from app.services.ifc_policy import can_ifc
from app.services.knowledge_router import SourceAvailability, route_question
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_query_service import answer_query, project_snapshot


def _number(value):
    """Numeric columns arrive as `Decimal`, which JSONB cannot serialise.

    Coerced at the tool boundary rather than by each consumer: this layer
    exists to feed agents and models, so anything it emits has to survive being
    written to JSONB or sent to a provider.
    """
    return float(value) if value is not None else None


def _task_json(task: Task) -> dict:
    return {
        "id": str(task.id), "taskCode": task.task_code, "name": task.name,
        "status": task.status.value if task.status else None,
        "progressPercentage": _number(task.progress_percentage),
        "priority": task.priority.value if task.priority else None,
        "plannedStartDate": task.planned_start_date.isoformat() if task.planned_start_date else None,
        "plannedEndDate": task.planned_end_date.isoformat() if task.planned_end_date else None,
        "assigneeIds": [str(person.id) for person in task.assignees],
    }


def get_project(db, actor: User, project_id, args) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise ToolError("NOT_FOUND", "Project not found", status=404)
    return {
        "id": str(project.id), "name": project.name,
        "status": project.status.value if project.status else None,
        "projectType": project.project_type, "location": project.location,
        "startDate": project.start_date.isoformat() if project.start_date else None,
        "plannedEndDate": project.planned_end_date.isoformat() if project.planned_end_date else None,
    }


def get_project_status(db, actor: User, project_id, args) -> dict:
    """The progress snapshot the voice assistant already computes."""
    tasks = authorized_voice_tasks(db, actor, project_id)
    snapshot = project_snapshot(db, project_id=project_id, tasks=tasks)
    return {
        "snapshot": snapshot,
        "taskCount": len(tasks),
        "note": "Counts cover only work this caller is authorized to see.",
    }


def get_tasks(db, actor: User, project_id, args) -> dict:
    tasks = authorized_voice_tasks(db, actor, project_id)
    if args.status:
        tasks = [task for task in tasks if task.status and task.status.value == args.status]
    if args.assignee_id:
        tasks = [task for task in tasks if any(p.id == args.assignee_id for p in task.assignees)]
    return {"tasks": [_task_json(task) for task in tasks[: args.limit]], "total": len(tasks)}


def get_task(db, actor: User, project_id, args) -> dict:
    """Resolved from the caller's own authorized list, never fetched by id alone.

    Fetching by primary key and then checking would work, but this way a task
    outside the caller's scope is indistinguishable from one that does not
    exist — which is the correct thing for it to be.
    """
    task = next(
        (item for item in authorized_voice_tasks(db, actor, project_id) if item.id == args.task_id),
        None,
    )
    if not task:
        raise ToolError("NOT_FOUND", "No such task in this project for this user", status=404)
    return {"task": _task_json(task), "description": task.description}


def get_project_users(db, actor: User, project_id, args) -> dict:
    members = (
        db.query(User, ProjectMember)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project_id, ProjectMember.is_active.is_(True))
        .all()
    )
    # Display only — no branch anywhere in the agent or tool layer reads these.
    # They are the configurable role first and the retired enum only as a
    # fallback for a membership the backfill has not reached, so this stops
    # describing people by a vocabulary the office may no longer use (and stops
    # depending on a column the contract migration drops). `party` is here for
    # the same reason `role` is: an agent summarising a project should be able
    # to say who is the office's and who is a contractor's.
    return {"users": [
        {
            "id": str(person.id), "fullName": person.full_name,
            "role": (
                membership.project_role_name
                or (person.role.value if person.role else None)
            ),
            "roleOnProject": (
                membership.project_role_name
                or (membership.role_on_project.value if membership.role_on_project else None)
            ),
            "party": membership.party_name,
            "isExternal": membership.is_external,
        }
        for person, membership in members
    ]}


def get_site_reports(db, actor: User, project_id, args) -> dict:
    reports = (
        db.query(SiteReport)
        .filter(SiteReport.project_id == project_id)
        .order_by(SiteReport.created_at.desc())
        .limit(args.limit)
        .all()
    )
    return {"reports": [
        {
            "id": str(report.id),
            "status": report.status.value if getattr(report, "status", None) else None,
            "reportDate": report.report_date.isoformat() if getattr(report, "report_date", None) else None,
            "createdAt": report.created_at.isoformat() if report.created_at else None,
        }
        for report in reports
    ]}


def search_documents(db, actor: User, project_id, args) -> dict:
    """Title/notes search inside the documents this caller may read."""
    readable = readable_document_ids(db, actor, project_id)
    if not readable:
        return {"documents": [], "note": "No documents in this project are readable by this caller."}
    pattern = f"%{args.query}%"
    query = db.query(Document).filter(
        Document.id.in_(readable),
        Document.title.ilike(pattern) | Document.notes.ilike(pattern),
    )
    if args.document_type:
        query = query.filter(Document.document_type == args.document_type)
    return {"documents": [
        {
            "id": str(document.id), "title": document.title,
            "documentType": document.document_type.value if document.document_type else None,
            "detectedFormat": document.detected_format,
            "suggestedDocumentType": document.suggested_document_type,
            "indexStatus": document.index_status,
        }
        for document in query.limit(args.limit).all()
    ]}


def get_document(db, actor: User, project_id, args) -> dict:
    readable = readable_document_ids(db, actor, project_id)
    document = db.query(Document).filter(
        Document.id == args.document_id, Document.id.in_(readable or []),
    ).first()
    if not document:
        raise ToolError("NOT_FOUND", "No such document readable by this caller", status=404)
    return {"document": {
        "id": str(document.id), "title": document.title,
        "documentType": document.document_type.value if document.document_type else None,
        "detectedFormat": document.detected_format,
        "classification": document.classification_json,
        "indexStatus": document.index_status, "pageCount": document.page_count,
    }}


def query_project_knowledge(db, actor: User, project_id, args) -> dict:
    """The Phase 4 router, reached as a tool rather than as an endpoint."""
    availability = SourceAvailability(
        documents=True,
        ifc=can_ifc(db, actor, project_id, "VIEW") and db.query(IFCModelVersion.id).filter(
            IFCModelVersion.project_id == project_id,
            IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
        ).first() is not None,
        site_reports=db.query(SiteReport.id).filter(SiteReport.project_id == project_id).first() is not None,
        structured=True,
    )
    routing = route_question(args.question, availability=availability)
    payload = {"route": routing.as_json()}

    if routing.source.value in {"PROJECT_STRUCTURED", "SITE_REPORTS"} and routing.topic:
        tasks = authorized_voice_tasks(db, actor, project_id)
        answer = answer_query(
            db, user=actor, project_id=project_id,
            query=DetectedQuery(topic=routing.topic, confidence=routing.confidence),
            tasks=tasks, spoken=args.question,
        )
        if answer and answer.is_answered:
            payload.update({
                "answer": answer.text_for(args.language), "found": True,
                "facts": answer.data,
                "citations": [{"sourceType": "PROJECT_RECORD", "sourceId": str(project_id)}],
            })
            return payload
        payload.update({"answer": "No answer could be built from the records available to you.", "found": False})
        return payload

    if routing.source.value == "IFC_MODEL":
        return payload | query_ifc(db, actor, project_id, args)

    readable = readable_document_ids(db, actor, project_id)
    allowed = [row[0] for row in db.query(Document.id).filter(
        Document.id.in_(readable), Document.index_status == rag.STATUS_READY,
    ).all()] if readable else []
    if not allowed:
        payload.update({"answer": "No indexed documents are available to this caller.", "found": False})
        return payload
    retrieved = rag.retrieve(db, project_id=project_id, readable_document_ids=allowed, query=args.question)
    answer = rag.AnswerService().answer(args.question, retrieved)
    payload.update({
        "answer": answer.answer, "found": answer.found,
        "citations": [
            {"sourceType": "DOCUMENT", "sourceId": str(c.document_id), "title": c.title,
             "page": c.page, "snippet": c.snippet}
            for c in answer.citations
        ],
    })
    return payload


def query_ifc(db, actor: User, project_id, args) -> dict:
    question = getattr(args, "question", None) or ""
    result = answer_ifc_question(db, project_id=project_id, question=question)
    return {
        "found": result.found,
        "answer": " ".join(fact.statement for fact in result.facts[:5]) or (result.unavailable_reason or ""),
        "resolvedSubject": result.resolved_subject,
        "unavailableReason": result.unavailable_reason,
        "citations": [
            {"sourceType": fact.source_type, "sourceId": fact.source_id,
             "snippet": fact.statement, "evidence": fact.evidence}
            for fact in result.facts
        ],
    }


def analyze_ifc(db, actor: User, project_id, args) -> dict:
    """Report the analysis already performed. It never re-runs processing.

    Naming this `analyze_ifc` follows the Phase 5 tool list, but an agent must
    not be able to trigger a heavy parse-and-tessellate cycle by asking a
    question — so this reads the stored result of the analysis that ran when
    the revision was processed.
    """
    query = db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == project_id,
        IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
    )
    version = (
        db.query(IFCModelVersion).filter(
            IFCModelVersion.id == args.version_id, IFCModelVersion.project_id == project_id
        ).first()
        if args.version_id
        else (query.filter(IFCModelVersion.is_active.is_(True)).first()
              or query.order_by(IFCModelVersion.created_at.desc()).first())
    )
    if not version:
        raise ToolError("NOT_FOUND", "This project has no processed IFC revision", status=404)
    summary = version.model_summary_json or {}
    findings = db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == version.id,
        IFCCoordinationFinding.false_positive.is_(False),
    ).all()
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    return {
        "versionId": str(version.id),
        "revision": version.revision_code or f"v{version.version_number}",
        "processingStatus": version.processing_status,
        "geometryStatus": version.geometry_status,
        "schema": summary.get("schema"),
        "mainStatistics": summary.get("mainStatistics", {}),
        "disciplineBreakdown": summary.get("disciplineBreakdown", {}),
        "interference": summary.get("interference", {}),
        "findingCount": len(findings),
        "findingsBySeverity": by_severity,
        "note": "Reports the analysis stored for this revision; it does not re-run processing.",
    }


def get_issues(db, actor: User, project_id, args) -> dict:
    issues = db.query(Issue).filter(Issue.project_id == project_id).order_by(
        Issue.created_at.desc()
    ).limit(50).all()
    return {"issues": [
        {
            "id": str(issue.id), "title": issue.title,
            "status": issue.status.value if issue.status else None,
            "severity": issue.severity.value if issue.severity else None,
        }
        for issue in issues
    ]}


def get_site_report(db, actor: User, project_id, args) -> dict:
    """One site report in full, for an agent that needs its narrative fields."""
    report = db.query(SiteReport).filter(
        SiteReport.id == args.report_id, SiteReport.project_id == project_id
    ).first()
    if not report:
        raise ToolError("NOT_FOUND", "No such site report in this project", status=404)
    return {"report": {
        "id": str(report.id), "taskId": str(report.task_id) if report.task_id else None,
        "reportDate": report.report_date.isoformat() if report.report_date else None,
        "summaryText": report.summary_text,
        "progressPercentageReported": float(report.progress_percentage_reported)
        if report.progress_percentage_reported is not None else None,
        "workCompleted": report.work_completed, "workInProgress": report.work_in_progress,
        "delays": report.delays, "issuesSummary": report.issues_summary,
        "weatherConditions": report.weather_conditions, "workersCount": report.workers_count,
        "reviewStatus": report.review_status,
    }}


def get_design_changes(db, actor: User, project_id, args) -> dict:
    """Design changes — the flow this platform uses for requests for information.

    There is no RFI entity here; `docs/NOTIFICATIONS.md` records that decision
    and designates DesignChange as what carries "raised by one discipline, must
    be reviewed and responded to by another".
    """
    query = db.query(DesignChange).filter(DesignChange.project_id == project_id)
    if args.status:
        query = query.filter(DesignChange.status == args.status)
    changes = query.order_by(DesignChange.created_at.desc()).limit(args.limit).all()
    return {"designChanges": [
        {
            "id": str(change.id), "title": change.title, "description": change.description,
            "reason": change.reason, "relatedDrawings": change.related_drawings,
            "status": change.status.value if change.status else None,
            "sourceDiscipline": change.source_discipline,
            "affectedDisciplines": [item.discipline for item in change.affected_disciplines],
            "expectedCostImpact": float(change.expected_cost_impact)
            if change.expected_cost_impact is not None else None,
            "expectedScheduleImpactDays": change.expected_schedule_impact_days,
            "reviewNotes": change.review_notes,
            "taskId": str(change.task_id) if change.task_id else None,
            "createdAt": change.created_at.isoformat() if change.created_at else None,
        }
        for change in changes
    ]}


def get_findings(db, actor: User, project_id, args) -> dict:
    """Existing AI findings on the project, whatever produced them.

    This is the *only* route by which one agent reaches another's conclusions.
    Direct agent-to-agent calls are not permitted: they would couple five
    independent analysts into a pipeline and bypass the authorization every
    other read goes through. Reading a stored finding is an ordinary read,
    gated on `ai.view_insights` like the review queue itself.
    """
    query = db.query(AIInsight).filter(AIInsight.project_id == project_id)
    if args.severity:
        query = query.filter(AIInsight.severity == args.severity)
    if args.status:
        # The two engines label an untouched finding "OPEN" and "NEW"; they
        # mean the same thing, so one filter matches both.
        query = query.filter(AIInsight.status.in_(
            ["OPEN", "NEW"] if args.status in {"OPEN", "NEW"} else [args.status]
        ))
    if args.source_engine:
        query = query.filter(AIInsight.source_engine == args.source_engine)
    findings = query.order_by(AIInsight.created_at.desc()).limit(args.limit).all()
    return {"findings": [
        {
            "id": str(item.id), "type": item.insight_type, "category": item.category,
            "severity": item.severity, "confidence": item.confidence,
            "title": item.title, "status": item.status,
            "sourceEngine": item.source_engine,
            "affected": item.affected_json,
            "relatedTaskIds": item.related_task_ids_json,
            "certainty": (item.evidence_json or {}).get("certainty"),
            "createdAt": item.created_at.isoformat() if item.created_at else None,
        }
        for item in findings
    ]}
