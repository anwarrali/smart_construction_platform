from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.ai_governance import DomainEvent
from app.models.enums import NotificationType, TaskStatus
from app.models.ifc import AIInsight, IFCElement, IFCModelVersion, IFCSpatialNode
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task


IMPORTANT_EVENTS = {
    "TASK_CREATED", "TASK_UPDATED", "TASK_PROGRESS_CHANGED", "TASK_COMPLETED",
    "ISSUE_CREATED", "DESIGN_CHANGE_CREATED", "FIELD_SUBMISSION_CREATED",
    "FIELD_SUBMISSION_VERIFIED", "CONSULTANT_REVIEW_COMPLETED", "IFC_UPLOADED",
    "IFC_REVISION_CREATED", "DOCUMENT_UPLOADED", "PROJECT_STRUCTURE_CHANGED",
    "AI_ACTION_REVERTED",
}


def emit_domain_event(
    db: Session,
    *,
    project_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    actor_user_id: UUID | None,
    payload: dict | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
) -> DomainEvent:
    if event_type not in IMPORTANT_EVENTS:
        raise ValueError(f"Unsupported domain event: {event_type}")
    key = idempotency_key or f"{event_type}:{entity_id}:{uuid4().hex}"
    existing = db.query(DomainEvent).filter(
        DomainEvent.project_id == project_id,
        DomainEvent.idempotency_key == key,
    ).first()
    if existing:
        return existing
    event = DomainEvent(
        project_id=project_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        correlation_id=correlation_id or key,
        idempotency_key=key,
        payload_json=payload or {},
        status="PENDING",
    )
    db.add(event)
    db.flush()
    process_event(db, event)
    return event


def process_event(db: Session, event: DomainEvent) -> None:
    if event.status not in {"PENDING", "RETRY"}:
        return
    event.processing_attempts += 1
    try:
        if event.event_type in {"TASK_CREATED", "TASK_UPDATED", "TASK_PROGRESS_CHANGED", "TASK_COMPLETED", "AI_ACTION_REVERTED"}:
            _validate_task_event(db, event)
        elif event.event_type == "FIELD_SUBMISSION_CREATED":
            _validate_field_claim(db, event)
        event.status = "PROCESSED_RULES_ONLY"
        event.processed_at = datetime.now(timezone.utc)
        event.error = None
    except Exception as exc:
        event.status = "RETRY" if event.processing_attempts < 3 else "FAILED"
        event.error = f"{type(exc).__name__}: event validation failed"
        if event.processing_attempts >= 3:
            event.processed_at = datetime.now(timezone.utc)


def _validate_task_event(db: Session, event: DomainEvent) -> None:
    task = db.get(Task, event.entity_id)
    if not task or task.project_id != event.project_id:
        return
    progress = float(task.progress_percentage or 0)
    if not 0 <= progress <= 100:
        _finding(
            db, event, "PROGRESS_OUT_OF_RANGE", "DATA_INCONSISTENCY", "CRITICAL",
            "Task progress is outside the valid range",
            "The persisted progress value is not between 0 and 100.",
            {"progress": progress, "status": task.status.value}, [task.id],
        )
    if progress > 0 and task.status in {TaskStatus.BACKLOG, TaskStatus.TODO}:
        _finding(
            db, event, "PROGRESS_STATUS_CONFLICT", "PROGRESS_CONFLICT", "HIGH",
            "Task progress conflicts with task status",
            "The task has reported progress while its status still indicates work has not started.",
            {"progress": progress, "status": task.status.value}, [task.id],
        )
    if task.planned_start_date and task.planned_end_date and task.planned_end_date < task.planned_start_date:
        _finding(
            db, event, "TASK_DATE_ORDER_INVALID", "SCHEDULE_CONFLICT", "HIGH",
            "Task finish date precedes its start date",
            "Deterministic date validation found an impossible planned date order.",
            {"start": task.planned_start_date.isoformat(), "finish": task.planned_end_date.isoformat()}, [task.id],
        )
    _validate_task_model_context(db, event, task)


def _validate_task_model_context(db: Session, event: DomainEvent, task: Task) -> None:
    version = db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == task.project_id,
        IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
    ).order_by(IFCModelVersion.is_active.desc(), IFCModelVersion.created_at.desc()).first()
    if not version:
        return
    text = f"{task.name} {task.description or ''}".casefold()
    required = {
        "WINDOW": (["window", "windows", "glazing", "نافذة", "نوافذ"], ["IfcWindow"]),
        "DOOR": (["door", "doors", "باب", "أبواب"], ["IfcDoor"]),
        "WALL": (["wall", "partition", "جدار", "قاطع"], ["IfcWall", "IfcWallStandardCase"]),
    }
    types = {value for (value,) in db.query(IFCElement.entity_type).filter(IFCElement.version_id == version.id).distinct().all()}
    for category, (terms, classes) in required.items():
        if any(term in text for term in terms) and not types.intersection(classes):
            _finding(
                db, event, f"TASK_MODEL_{category}_MISSING", "TASK_MODEL_MISMATCH", "HIGH",
                f"Task scope has no matching {category.lower()} elements in the current IFC",
                "Task terminology and deterministic IFC entity classes are inconsistent.",
                {"taskText": text[:1000], "expectedClasses": classes, "versionId": str(version.id)}, [task.id],
                model_revision_id=version.id,
            )


def _validate_field_claim(db: Session, event: DomainEvent) -> None:
    task_id = (event.payload_json or {}).get("taskId")
    description = str((event.payload_json or {}).get("description") or "").casefold()
    try:
        task = db.get(Task, UUID(task_id)) if task_id else None
    except (TypeError, ValueError):
        task = None
    if task and task.status in {TaskStatus.BACKLOG, TaskStatus.TODO} and any(
        word in description for word in ("finished", "complete", "completed", "انته", "خلص")
    ):
        _finding(
            db, event, "FIELD_CLAIM_BEFORE_TASK_START", "SUSPICIOUS_UPDATE", "HIGH",
            "Field completion claim conflicts with task status",
            "A worker field claim reports completion while the official task is not started. The claim remains unverified.",
            {"taskStatus": task.status.value, "claim": description[:1000]}, [task.id],
        )


def _finding(
    db: Session,
    event: DomainEvent,
    code: str,
    category: str,
    severity: str,
    title: str,
    description: str,
    evidence: dict,
    task_ids: list[UUID],
    model_revision_id: UUID | None = None,
) -> AIInsight:
    fingerprint = hashlib.sha256(
        json.dumps({"event": str(event.id), "code": code}, sort_keys=True).encode()
    ).hexdigest()
    existing = db.query(AIInsight).filter(AIInsight.fingerprint == fingerprint).first()
    if existing:
        return existing
    item = AIInsight(
        project_id=event.project_id,
        model_revision_id=model_revision_id,
        fingerprint=fingerprint,
        insight_type=code,
        category=category,
        severity=severity,
        confidence=1.0,
        title=title,
        description=description,
        reason="A deterministic event validation rule produced this finding.",
        recommended_action="Review the evidence and correct the project or model state; no automatic mutation was applied.",
        evidence_json={**evidence, "eventId": str(event.id), "eventType": event.event_type},
        affected_json={"tasks": [str(value) for value in task_ids]},
        related_task_ids_json=[str(value) for value in task_ids],
        source_engine="DOMAIN_EVENT_RULES_V1",
        status="OPEN",
    )
    db.add(item)
    project = db.get(Project, event.project_id)
    if severity in {"HIGH", "CRITICAL"} and project and project.project_manager_id:
        db.add(Notification(
            user_id=project.project_manager_id,
            title=f"AI finding: {title}",
            message=description,
            type=NotificationType.SYSTEM,
            project_id=event.project_id,
            related_entity_type="AI_INSIGHT",
            related_entity_id=item.id,
        ))
    return item
