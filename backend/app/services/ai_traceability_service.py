"""Normalized AI source traceability and stale-insight invalidation."""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.collaboration import AIInsightSource
from app.models.ifc import AIInsight


def source_snapshot_hash(source_type: str, source_id, source_state: str, source_version=None) -> str:
    payload = json.dumps({"type": source_type.upper(), "id": str(source_id), "state": source_state.upper(),
                          "version": str(source_version) if source_version is not None else None}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def register_insight_source(db: Session, insight: AIInsight, *, source_type: str, source_id,
                            label: str | None = None, state: str = "RAW", version=None) -> AIInsightSource:
    normalized = source_type.upper()
    row = db.query(AIInsightSource).filter(AIInsightSource.insight_id == insight.id,
        AIInsightSource.source_type == normalized, AIInsightSource.source_id == source_id).first()
    digest = source_snapshot_hash(normalized, source_id, state, version)
    if not row:
        row = AIInsightSource(insight_id=insight.id, project_id=insight.project_id, source_type=normalized,
                              source_id=source_id, source_label=label, source_state=state.upper(),
                              source_version=str(version) if version is not None else None, snapshot_hash=digest)
        db.add(row)
    else:
        row.source_label, row.source_state, row.source_version, row.snapshot_hash = label, state.upper(), str(version) if version is not None else None, digest
        row.is_valid, row.invalidated_at, row.invalidation_reason = True, None, None
    return row


def register_structured_sources(db: Session, insight: AIInsight) -> int:
    sources = []
    sources += [("TASK", value, "Human-reviewed task state") for value in insight.related_task_ids_json]
    sources += [("ISSUE", value, "Project issue") for value in insight.related_issue_ids_json]
    sources += [("FIELD_SUBMISSION", value, "Field evidence") for value in insight.related_evidence_ids_json]
    if insight.model_revision_id: sources.append(("IFC_MODEL_VERSION", insight.model_revision_id, "IFC model revision"))
    count = 0
    import uuid
    for source_type, value, label in sources:
        try: source_id = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (TypeError, ValueError): continue
        register_insight_source(db, insight, source_type=source_type, source_id=source_id, label=label,
                                state="HUMAN_VERIFIED" if source_type == "FIELD_SUBMISSION" else "OFFICIAL_PROJECT_INFORMATION")
        count += 1
    return count


def invalidate_insights_for_source(db: Session, *, project_id, source_type: str, source_id,
                                   reason: str, rejected: bool = False) -> int:
    rows = db.query(AIInsightSource).filter(AIInsightSource.project_id == project_id,
        AIInsightSource.source_type == source_type.upper(), AIInsightSource.source_id == source_id,
        AIInsightSource.is_valid == True).all()
    now = datetime.now(timezone.utc); affected = 0
    for row in rows:
        row.is_valid = False; row.invalidated_at = now; row.invalidation_reason = reason
        row.source_state = "REJECTED" if rejected else "CHANGED"
        insight = db.get(AIInsight, row.insight_id)
        if insight and insight.status not in {"RESOLVED", "FALSE_POSITIVE", "OUTDATED"}:
            insight.status = "OUTDATED"; insight.resolved_at = now
            insight.review_note = f"Automatically invalidated: {reason}. Re-run analysis against accepted project state."
            affected += 1
    return affected
