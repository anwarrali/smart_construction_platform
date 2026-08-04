from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.deps import is_main_contractor_engineer, user_has_project_access
from app.models.ai_governance import AIActionVersion
from app.models.design_change import DesignChange
from app.models.enums import TaskStatus, UserRole
from app.models.field_submission import FieldSubmission
from app.models.issue import Issue
from app.models.project import Project
from app.models.site_report import SiteReport
from app.models.task import Task
from app.models.user import User
from app.models.voice_action import VoiceActionDraft
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import SuggestedAction, SuggestedActionType
from app.services.audit_service import record_audit
from app.services.task_progress_service import _refresh_project_progress
from app.services.domain_event_dispatcher import emit_domain_event


TASK_ACTIONS = {
    SuggestedActionType.START_TASK,
    SuggestedActionType.UPDATE_TASK_PROGRESS,
    SuggestedActionType.SUBMIT_TASK_FOR_REVIEW,
    SuggestedActionType.PREPARE_CONSULTANT_REVIEW,
    SuggestedActionType.ADD_TASK_NOTE,
}

CREATED_ENTITY_TYPES = {
    SuggestedActionType.CREATE_TASK: ("TASK", Task),
    SuggestedActionType.CREATE_ISSUE: ("ISSUE", Issue),
    SuggestedActionType.CREATE_FIELD_SUBMISSION: ("FIELD_SUBMISSION", FieldSubmission),
    SuggestedActionType.CREATE_SITE_REPORT_DRAFT: ("SITE_REPORT", SiteReport),
    SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT: ("DESIGN_CHANGE", DesignChange),
}


def task_state(task: Task | None) -> dict | None:
    if not task:
        return None
    return {
        "id": str(task.id),
        "status": task.status.value,
        "progressPercentage": float(task.progress_percentage or 0),
        "reviewStatus": task.review_status,
        "reviewedById": str(task.reviewed_by_id) if task.reviewed_by_id else None,
        "updatedAt": task.updated_at.isoformat() if task.updated_at else None,
    }


def _entity_state(entity) -> dict | None:
    if entity is None:
        return None
    state = {"id": str(entity.id)}
    for field in ("status", "title", "description", "review_status", "task_id", "project_id"):
        value = getattr(entity, field, None)
        if hasattr(value, "value"):
            value = value.value
        if isinstance(value, UUID):
            value = str(value)
        if value is not None:
            state[field] = value
    return state


def record_voice_action_version(
    db: Session,
    *,
    command: VoiceAnalysis,
    draft: VoiceActionDraft,
    action: SuggestedAction,
    actor: User,
    result_entity_id: UUID,
    before_task_state: dict | None,
) -> AIActionVersion:
    request_id = f"{command.id}:{draft.client_action_id}"
    existing = db.query(AIActionVersion).filter(
        AIActionVersion.actor_user_id == actor.id,
        AIActionVersion.request_id == request_id,
    ).first()
    if existing:
        return existing

    if action.type in TASK_ACTIONS:
        entity_type = "TASK"
        entity_id = draft.target_entity_id or result_entity_id
        after_state = task_state(db.get(Task, entity_id))
        before_state = before_task_state
    elif action.type in CREATED_ENTITY_TYPES:
        entity_type, model = CREATED_ENTITY_TYPES[action.type]
        entity_id = result_entity_id
        before_state = None
        after_state = _entity_state(db.get(model, entity_id))
    else:
        entity_type = draft.target_entity_type or "AI_ACTION_RESULT"
        entity_id = result_entity_id
        before_state = before_task_state
        after_state = None

    version = AIActionVersion(
        project_id=command.project_id,
        actor_user_id=actor.id,
        voice_analysis_id=command.id,
        source="MOBILE_VOICE" if command.audio_attachment_id else "MOBILE_JSON_SIMULATION",
        intent=action.type.value,
        original_input=command.raw_transcript,
        ai_interpretation=command.structured_result or {},
        final_command={
            "actionType": action.type.value,
            "targetId": str(action.target_id) if action.target_id else None,
            "payload": action.payload_dict(),
        },
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        approval_info={
            "confirmedById": str(command.confirmed_by_id) if command.confirmed_by_id else None,
            "confirmedAt": command.confirmed_at.isoformat() if command.confirmed_at else None,
        },
        result="APPLIED",
        request_id=request_id,
        correlation_id=command.idempotency_key or str(command.id),
        undo_policy=(
            "AUTOMATIC_PROGRESS_COMPENSATION"
            if action.type == SuggestedActionType.UPDATE_TASK_PROGRESS
            else "MANUAL_REVIEW"
        ),
        metadata_json={"draftId": str(draft.id), "clientActionId": draft.client_action_id},
    )
    db.add(version)
    db.flush()
    return version


def undo_status(db: Session, action: AIActionVersion) -> tuple[bool, str | None]:
    if action.result != "APPLIED":
        return False, "Only successfully applied actions can be reverted."
    if action.undo_policy != "AUTOMATIC_PROGRESS_COMPENSATION":
        return False, "Manual review required for this action type."
    if db.query(AIActionVersion.id).filter(AIActionVersion.reverted_action_id == action.id).first():
        return False, "This action already has a compensating revert."
    newer = db.query(AIActionVersion.id).filter(
        AIActionVersion.entity_type == action.entity_type,
        AIActionVersion.entity_id == action.entity_id,
        AIActionVersion.created_at > action.created_at,
        AIActionVersion.result == "APPLIED",
    ).first()
    if newer:
        return False, "A newer dependent AI action exists for this entity."
    task = db.get(Task, action.entity_id) if action.entity_type == "TASK" else None
    if not task:
        return False, "The affected task is no longer available."
    after = action.after_state or {}
    if float(task.progress_percentage or 0) != float(after.get("progressPercentage", -1)):
        return False, "The task changed after this AI action."
    if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE}:
        return False, "The task is locked by a review or completion workflow."
    return True, None


def revert_action(
    db: Session,
    *,
    action: AIActionVersion,
    actor: User,
    request_id: str,
    reason: str,
) -> AIActionVersion:
    duplicate = db.query(AIActionVersion).filter(
        AIActionVersion.actor_user_id == actor.id,
        AIActionVersion.request_id == request_id,
    ).first()
    if duplicate:
        return duplicate
    if not user_has_project_access(db, actor, action.project_id):
        raise HTTPException(status_code=403, detail="Project access is required")
    project = db.get(Project, action.project_id)
    is_pm = bool(actor.role == UserRole.PROJECT_MANAGER and project and project.project_manager_id == actor.id)
    if actor.id != action.actor_user_id and actor.role != UserRole.ADMIN and not is_pm:
        raise HTTPException(status_code=403, detail="Only the original actor, project manager, or administrator can revert this action")
    task = db.query(Task).filter(Task.id == action.entity_id).with_for_update().first()
    available, unavailable_reason = undo_status(db, action)
    if not available:
        raise HTTPException(status_code=409, detail=unavailable_reason or "Manual review required")
    if not (is_pm or actor.role == UserRole.ADMIN or (is_main_contractor_engineer(actor) and any(item.id == actor.id for item in task.assignees))):
        raise HTTPException(status_code=403, detail="Current task authorization no longer permits this revert")

    current = task_state(task)
    before = action.before_state or {}
    try:
        previous_status = TaskStatus(before["status"])
        previous_progress = float(before["progressPercentage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Manual review required: the original state is incomplete") from exc
    task.progress_percentage = previous_progress
    task.status = previous_status
    _refresh_project_progress(db, task.project_id)
    db.flush()
    compensated = task_state(task)
    revert = AIActionVersion(
        project_id=action.project_id,
        actor_user_id=actor.id,
        voice_analysis_id=action.voice_analysis_id,
        parent_action_id=action.id,
        reverted_action_id=action.id,
        source="AI_ACTION_REVERT",
        intent="REVERT_AI_ACTION",
        original_input=reason.strip(),
        ai_interpretation={},
        final_command={"revertActionId": str(action.id), "reason": reason.strip()},
        entity_type=action.entity_type,
        entity_id=action.entity_id,
        before_state=current,
        after_state=compensated,
        approval_info={"authorizedById": str(actor.id)},
        result="APPLIED",
        request_id=request_id,
        correlation_id=action.correlation_id,
        undo_policy="MANUAL_REVIEW",
        metadata_json={"compensatingAction": True},
    )
    db.add(revert)
    db.flush()
    emit_domain_event(
        db,
        project_id=task.project_id,
        event_type="AI_ACTION_REVERTED",
        entity_type="TASK",
        entity_id=task.id,
        actor_user_id=actor.id,
        payload={"revertedActionId": str(action.id), "before": current, "after": compensated},
        correlation_id=action.correlation_id,
        idempotency_key=f"AI_ACTION_REVERTED:{revert.id}",
    )
    record_audit(
        db,
        actor_id=actor.id,
        action="ai_action_reverted",
        entity_type="task",
        entity_id=task.id,
        project_id=task.project_id,
        details={
            "revertedActionId": str(action.id),
            "revertActionId": str(revert.id),
            "before": current,
            "after": compensated,
            "correlationId": action.correlation_id,
            "reason": reason.strip(),
        },
    )
    db.commit()
    db.refresh(revert)
    return revert
