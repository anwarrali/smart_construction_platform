from __future__ import annotations

from datetime import datetime, timezone
import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import user_has_project_access
from app.models.enums import UserStatus, VoiceAnalysisStatus
from app.models.task import Task
from app.models.user import User
from app.models.voice_action import VoiceActionDraft, VoiceClarification
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import ConstructionVoiceResult, SuggestedActionType
from app.schemas.voice_command import VoiceDraftUpdate
from app.services.audit_service import record_audit
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_action_policy import action_risk


ALLOWED_TRANSITIONS: dict[VoiceAnalysisStatus, set[VoiceAnalysisStatus]] = {
    VoiceAnalysisStatus.UPLOADED: {
        VoiceAnalysisStatus.TRANSCRIBING,
        VoiceAnalysisStatus.CANCELLED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.TRANSCRIBING: {
        VoiceAnalysisStatus.TRANSCRIBED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.TRANSCRIBED: {
        VoiceAnalysisStatus.ANALYZING,
        VoiceAnalysisStatus.CANCELLED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.ANALYZING: {
        VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.NEEDS_CLARIFICATION: {
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
        VoiceAnalysisStatus.CANCELLED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.READY_FOR_CONFIRMATION: {
        VoiceAnalysisStatus.CONFIRMED,
        VoiceAnalysisStatus.CANCELLED,
    },
    VoiceAnalysisStatus.COMPLETED: {
        VoiceAnalysisStatus.CONFIRMED,
        VoiceAnalysisStatus.CANCELLED,
    },
    VoiceAnalysisStatus.CONFIRMED: {
        VoiceAnalysisStatus.EXECUTING,
        VoiceAnalysisStatus.CANCELLED,
    },
    VoiceAnalysisStatus.EXECUTING: {
        VoiceAnalysisStatus.EXECUTED,
        VoiceAnalysisStatus.PARTIALLY_EXECUTED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.FAILED: {
        VoiceAnalysisStatus.UPLOADED,
        VoiceAnalysisStatus.CANCELLED,
    },
}


def transition(command: VoiceAnalysis, target: VoiceAnalysisStatus) -> None:
    if command.status == target:
        return
    if target not in ALLOWED_TRANSITIONS.get(command.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Voice command cannot transition from {command.status.value} to {target.value}",
        )
    command.status = target
    command.row_version += 1


def assert_command_access(
    db: Session, command: VoiceAnalysis, user: User, *, owner_only: bool = False
) -> None:
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="An active account is required")
    if not user_has_project_access(db, user, command.project_id):
        raise HTTPException(status_code=403, detail="Voice command project is not accessible")
    if owner_only and command.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the initiating user may change this command")
    if not owner_only and command.user_id != user.id:
        from app.services.voice_analysis_authorization import can_view_voice_analysis
        if not can_view_voice_analysis(db, user, command):
            raise HTTPException(status_code=403, detail="Voice command is not accessible")


def assert_version(command: VoiceAnalysis, expected: int) -> None:
    if command.row_version != expected:
        raise HTTPException(
            status_code=409,
            detail="Voice command changed. Refresh and confirm the current draft.",
        )


def build_action_drafts(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
) -> None:
    command.normalized_transcript = (
        result.normalized_transcript or result.summary
    ).strip()
    candidates = authorized_voice_tasks(db, user, command.project_id)
    candidate_ids = {task.id for task in candidates}
    suggestions = list(result.suggested_actions)

    # A Worker statement is always evidence. If the model returned only an
    # informational summary, deterministically create the evidence draft.
    if user.role.value == "worker" and not suggestions:
        from app.schemas.voice_analysis import SuggestedAction

        target_id = command.task_id or result.detected_task.task_id
        suggestions = [
            SuggestedAction(
                type=SuggestedActionType.CREATE_FIELD_SUBMISSION,
                target_id=target_id,
                reason="Worker voice report requires Engineer verification",
                payload={"description": result.summary},
                confidence=max(float(result.detected_task.confidence), 0.5),
            )
        ]

    for index, suggestion in enumerate(suggestions):
        target_id = command.task_id or suggestion.target_id
        if target_id not in candidate_ids:
            target_id = None
        task = db.get(Task, target_id) if target_id else None
        missing: list[str] = list(suggestion.missing_fields)
        warnings: list[str] = list(suggestion.warnings)
        if suggestion.type in {
            SuggestedActionType.START_TASK,
            SuggestedActionType.UPDATE_TASK_PROGRESS,
            SuggestedActionType.SUBMIT_TASK_FOR_REVIEW,
            SuggestedActionType.CREATE_FIELD_SUBMISSION,
            SuggestedActionType.ADD_TASK_NOTE,
        } and task is None:
            missing.append("target.taskId")
        if float(suggestion.confidence) < settings.VOICE_MIN_EXECUTION_CONFIDENCE:
            warnings.append("Low AI confidence: review or edit this action before confirmation.")
        if user.role.value == "worker" and suggestion.type != SuggestedActionType.CREATE_FIELD_SUBMISSION:
            warnings.append("Worker reports cannot change official task values.")
            suggestion = suggestion.model_copy(update={
                "type": SuggestedActionType.CREATE_FIELD_SUBMISSION,
                "payload": {"description": result.summary},
            })
        snapshot = None
        if task:
            snapshot = {
                "taskId": str(task.id),
                "status": task.status.value,
                "progressPercentage": float(task.progress_percentage or 0),
                "updatedAt": task.updated_at.isoformat(),
            }
        configured_evidence: list[str] = []
        evidence_policy = task.voice_evidence_requirements if task else {}
        minimum_photos = int((evidence_policy or {}).get("minimumPhotos") or 0)
        if minimum_photos:
            configured_evidence.append(f"PHOTO:{minimum_photos}")
        configured_evidence.extend(
            f"VIEW:{str(view).upper()}" for view in (evidence_policy or {}).get("views", [])
        )
        command.action_drafts.append(VoiceActionDraft(
            voice_analysis_id=command.id,
            client_action_id=(
                suggestion.client_action_id or f"a{index + 1}-{uuid4().hex[:12]}"
            ),
            action_type=suggestion.type.value,
            target_entity_type="TASK" if task else None,
            target_entity_id=task.id if task else None,
            extracted_payload=suggestion.payload_dict(),
            target_snapshot=snapshot,
            confidence=float(suggestion.confidence),
            missing_fields=missing,
            warnings=warnings,
            risk_level=action_risk(suggestion.type).value,
            required_evidence=configured_evidence,
        ))
    if not command.action_drafts and user.role.value != "worker":
        ambiguous = re.search(
            r"(تقريب[اً]? خلصنا|أغلب الشغل|مرحلة متقدمة|almost done|mostly complete)",
            command.raw_transcript or "",
            flags=re.IGNORECASE,
        )
        target_id = command.task_id or result.detected_task.task_id
        task = db.get(Task, target_id) if target_id in candidate_ids else None
        missing = ["progressPercentage"] if ambiguous else []
        if not task:
            missing.append("target.taskId")
        command.action_drafts.append(VoiceActionDraft(
            voice_analysis_id=command.id,
            client_action_id=f"a1-{uuid4().hex[:12]}",
            action_type=(
                SuggestedActionType.UPDATE_TASK_PROGRESS.value
                if ambiguous
                else SuggestedActionType.ADD_TASK_NOTE.value
            ),
            target_entity_type="TASK" if task else None,
            target_entity_id=task.id if task else None,
            extracted_payload={} if ambiguous else {
                "content": command.raw_transcript or result.summary
            },
            target_snapshot={
                "taskId": str(task.id),
                "status": task.status.value,
                "progressPercentage": float(task.progress_percentage or 0),
                "updatedAt": task.updated_at.isoformat(),
            } if task else None,
            confidence=0,
            missing_fields=missing,
            warnings=["No progress percentage was inferred from ambiguous language."] if ambiguous else [],
            risk_level=action_risk(
                SuggestedActionType.UPDATE_TASK_PROGRESS
                if ambiguous else SuggestedActionType.ADD_TASK_NOTE
            ).value,
            required_evidence=[],
        ))
    db.flush()
    create_target_clarifications(db, command, candidates=candidates)
    transition(
        command,
        VoiceAnalysisStatus.NEEDS_CLARIFICATION
        if any(draft.missing_fields for draft in command.action_drafts)
        else VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
    )


def create_target_clarifications(
    db: Session,
    command: VoiceAnalysis,
    *,
    candidates: list[Task] | None = None,
) -> None:
    sequence = len(command.clarifications)
    for draft in command.action_drafts:
        if "target.taskId" in draft.missing_fields:
            sequence += 1
            command.clarifications.append(VoiceClarification(
                voice_action_draft_id=draft.id,
                sequence=sequence,
                field_path="target.taskId",
                question_ar="أي مهمة تقصد؟",
                question_en="Which task do you mean?",
                expected_answer_type="TASK_SELECTION",
                options=[
                    {
                        "value": str(task.id),
                        "label": f"{task.task_code} — {task.name}",
                    }
                    for task in (candidates or [])[:50]
                ],
            ))
        if "progressPercentage" in draft.missing_fields:
            sequence += 1
            command.clarifications.append(VoiceClarification(
                voice_action_draft_id=draft.id,
                sequence=sequence,
                field_path="payload.progressPercentage",
                question_ar="ما نسبة الإنجاز التقريبية لهذه المهمة؟",
                question_en="What is the approximate completion percentage for this task?",
                expected_answer_type="NUMBER",
                options=[
                    {"value": 25, "label": "25%"},
                    {"value": 50, "label": "50%"},
                    {"value": 75, "label": "75%"},
                    {"value": 100, "label": "100%"},
                ],
            ))
    if not command.action_drafts:
        sequence += 1
        command.clarifications.append(VoiceClarification(
            sequence=sequence,
            field_path="intent",
            question_ar="هل تريد إضافة ملاحظة أم الإبلاغ عن مشكلة؟",
            question_en="Do you want to add a note or report an issue?",
            expected_answer_type="TEXT",
            options=[],
        ))


def update_draft(
    db: Session,
    *,
    command: VoiceAnalysis,
    draft: VoiceActionDraft,
    update: VoiceDraftUpdate,
    user: User,
) -> VoiceActionDraft:
    assert_command_access(db, command, user, owner_only=True)
    assert_version(command, update.row_version)
    if command.status not in {
        VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
    }:
        raise HTTPException(status_code=409, detail="This draft is no longer editable")
    if draft.voice_analysis_id != command.id:
        raise HTTPException(status_code=404, detail="Draft action not found")
    if update.target_id:
        allowed = {task.id for task in authorized_voice_tasks(db, user, command.project_id)}
        if update.target_id not in allowed:
            raise HTTPException(status_code=422, detail="Selected task is outside the allowed task list")
        task = db.get(Task, update.target_id)
        draft.target_entity_type = "TASK"
        draft.target_entity_id = task.id
        draft.target_snapshot = {
            "taskId": str(task.id),
            "status": task.status.value,
            "progressPercentage": float(task.progress_percentage or 0),
            "updatedAt": task.updated_at.isoformat(),
        }
        draft.missing_fields = [
            item for item in draft.missing_fields if item != "target.taskId"
        ]
    draft.user_edited_payload = dict(update.payload)
    draft.selected_for_execution = update.selected_for_execution
    command.row_version += 1
    if all(not item.missing_fields for item in command.action_drafts):
        if command.status == VoiceAnalysisStatus.NEEDS_CLARIFICATION:
            transition(command, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
    record_audit(
        db,
        actor_id=user.id,
        action="voice_draft_edited",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={"draft_id": draft.id, "action_type": draft.action_type},
    )
    db.commit()
    db.refresh(draft)
    return draft


def answer_clarification(
    db: Session,
    *,
    command: VoiceAnalysis,
    clarification: VoiceClarification,
    answer: str,
    user: User,
) -> None:
    assert_command_access(db, command, user, owner_only=True)
    if command.status != VoiceAnalysisStatus.NEEDS_CLARIFICATION:
        raise HTTPException(status_code=409, detail="This command is not waiting for clarification")
    if clarification.voice_analysis_id != command.id or clarification.answer_text:
        raise HTTPException(status_code=409, detail="Clarification is unavailable or already answered")
    clean = answer.strip()
    if clarification.expected_answer_type == "TASK_SELECTION":
        try:
            task_id = UUID(clean)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Select a valid task") from exc
        allowed = {task.id for task in authorized_voice_tasks(db, user, command.project_id)}
        if task_id not in allowed:
            raise HTTPException(status_code=422, detail="Selected task is not available")
        draft = db.get(VoiceActionDraft, clarification.voice_action_draft_id)
        task = db.get(Task, task_id)
        draft.target_entity_type = "TASK"
        draft.target_entity_id = task.id
        draft.target_snapshot = {
            "taskId": str(task.id),
            "status": task.status.value,
            "progressPercentage": float(task.progress_percentage or 0),
            "updatedAt": task.updated_at.isoformat(),
        }
        draft.missing_fields = [
            item for item in draft.missing_fields if item != "target.taskId"
        ]
    elif clarification.expected_answer_type == "NUMBER":
        try:
            progress = float(clean.replace("%", "").replace("٪", "").strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Enter a percentage from 0 to 100") from exc
        if not 0 <= progress <= 100:
            raise HTTPException(status_code=422, detail="Progress must be between 0 and 100")
        draft = db.get(VoiceActionDraft, clarification.voice_action_draft_id)
        payload = dict(draft.user_edited_payload or draft.extracted_payload or {})
        payload["progressPercentage"] = progress
        draft.user_edited_payload = payload
        draft.missing_fields = [
            item for item in draft.missing_fields if item != "progressPercentage"
        ]
    clarification.answer_text = clean
    clarification.answer_source = "TEXT"
    clarification.answered_at = datetime.now(timezone.utc)
    command.row_version += 1
    if command.action_drafts and all(not item.missing_fields for item in command.action_drafts):
        transition(command, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
    record_audit(
        db,
        actor_id=user.id,
        action="voice_clarification_answered",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={"clarification_id": clarification.id, "field_path": clarification.field_path},
    )
    db.commit()
