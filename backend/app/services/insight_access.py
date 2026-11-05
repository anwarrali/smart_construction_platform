"""Reauthorize derived information against all its original sources on read.

No prompt, stored role snapshot, or analysis principal grants the reader access.
Unknown/missing/foreign provenance fails closed. Cyclic derived evidence is not
an authority path. Legacy source-free project rule findings remain project data.
"""
from uuid import UUID

from fastapi import HTTPException

from app.core.deps import user_has_project_access
from app.models.collaboration import AIInsightSource
from app.models.document import Document
from app.models.ingestion import IngestedFile
from app.models.ifc import AIInsight, IFCModelVersion, IFCElement, IFCCoordinationFinding
from app.models.task import Task
from app.models.site_report import SiteReport
from app.models.issue import Issue
from app.models.design_change import DesignChange
from app.models.field_submission import FieldSubmission
from app.models.enums import UserStatus
from app.services.authorization import has_permission
from app.services.document_access import readable_document_ids, readable_ingested_file_ids
from app.services.voice_analysis_authorization import authorized_voice_tasks


def can_read_insight(db, user, insight, seen=None):
    if user.status != UserStatus.ACTIVE:
        return False
    if not user_has_project_access(db, user, insight.project_id):
        return False
    if not has_permission(db, user, "ai.view_insights", insight.project_id):
        return False
    seen = set(seen or ())
    if insight.id in seen:
        return False
    seen.add(insight.id)
    refs = {(r.source_type, str(r.source_id)) for r in db.query(AIInsightSource).filter(
        AIInsightSource.insight_id == insight.id).all()}
    for claim in (insight.evidence_json or {}).get("claims", []):
        refs.add((claim.get("sourceType", ""), str(claim.get("sourceId", ""))))
    refs.update(("TASK", str(i)) for i in (insight.related_task_ids_json or []))
    refs.update(("ISSUE", str(i)) for i in (insight.related_issue_ids_json or []))
    refs.update(("FIELD_SUBMISSION", str(i)) for i in (insight.related_evidence_ids_json or []))
    if insight.model_revision_id:
        refs.add(("IFC_VERSION", str(insight.model_revision_id)))
    for key, kind in (("documents", "DOCUMENT"), ("tasks", "TASK"), ("ifcVersions", "IFC_VERSION"),
                      ("siteReports", "SITE_REPORT"), ("designChanges", "DESIGN_CHANGE")):
        refs.update((kind, str(i)) for i in (insight.affected_json or {}).get(key, []))
    if not refs and (insight.evidence_json or {}).get("certainty") != "UNCERTAIN":
        # Legacy records without attributable evidence cannot inherit the
        # broad insight-read grant. Limit them to the accountable principal.
        from app.models.project import Project
        project = db.get(Project, insight.project_id)
        return bool(project and project.project_manager_id == user.id)
    return all(source_readable(db, user, insight.project_id, kind, source_id, seen)
               for kind, source_id in refs)


def source_readable(db, user, project_id, kind, source_id, seen=None):
    try:
        source_id = UUID(str(source_id))
    except (ValueError, TypeError):
        return False
    if not user_has_project_access(db, user, project_id):
        return False
    kind = kind.upper()
    if kind == "PROJECT_RECORD":
        return source_id == project_id and has_permission(db, user, "task.view", project_id)
    if kind == "DOCUMENT":
        row = db.get(Document, source_id)
        return bool(row and row.project_id == project_id and source_id in readable_document_ids(db, user, project_id))
    if kind == "INGESTED_FILE":
        row = db.get(IngestedFile, source_id)
        return bool(row and row.project_id == project_id and source_id in readable_ingested_file_ids(db, user, project_id))
    if kind == "AI_INSIGHT":
        row = db.get(AIInsight, source_id)
        return bool(row and row.project_id == project_id and can_read_insight(db, user, row, seen))
    if kind == "FIELD_SUBMISSION":
        from app.services.field_submission_authorization import can_view_field_submission
        row = db.get(FieldSubmission, source_id)
        return bool(row and row.project_id == project_id and can_view_field_submission(db, user, row))
    if kind == "TASK":
        return any(t.id == source_id and t.project_id == project_id
                   for t in authorized_voice_tasks(db, user, project_id))
    model, permission = {
        "IFC_VERSION": (IFCModelVersion, "ifc.view"),
        "IFC_MODEL_VERSION": (IFCModelVersion, "ifc.view"),
        "IFC_ELEMENT": (IFCElement, "ifc.view"),
        "IFC_COORDINATION_FINDING": (IFCCoordinationFinding, "ifc.view"),
        "SITE_REPORT": (SiteReport, "site_report.submit"),
        "ISSUE": (Issue, "task.view"),
        "DESIGN_CHANGE": (DesignChange, "design_change.propose"),
    }.get(kind, (None, None))
    if model is None:
        return False
    row = db.get(model, source_id)
    if not row or row.project_id != project_id or not has_permission(db, user, permission, project_id):
        return False
    if kind == "SITE_REPORT" and row.task_id:
        return source_readable(db, user, project_id, "TASK", row.task_id, seen)
    return True


def require_readable_insight(db, user, insight):
    if not can_read_insight(db, user, insight):
        raise HTTPException(status_code=404, detail="AI insight not found")


def require_readable_chunks(db, user, project_id, chunks):
    # A provider call may take long enough for access to be revoked elsewhere.
    # Re-read ORM membership/party/account state rather than reusing identity-map
    # objects loaded before the call. Retrieval uses read-only request sessions.
    db.expire_all()
    user.__dict__.pop("_office_role_ids", None)
    for item in chunks:
        source = item.chunk.source
        if not source_readable(db, user, project_id, source.kind, source.id):
            raise HTTPException(status_code=403, detail="Evidence access changed; retry the question")


def notification_readable(db, user, notification):
    if notification.related_entity_type != "AI_INSIGHT":
        return True
    insight = db.get(AIInsight, notification.related_entity_id)
    return bool(insight and can_read_insight(db, user, insight))
