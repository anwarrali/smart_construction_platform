from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import user_has_project_access
from app.core.deps import is_consultant_engineer
from app.models.enums import TaskStatus, UserRole, UserStatus, VoiceAnalysisStatus
from app.models.task import Task
from app.models.attachment import Attachment
from app.ai.action_payload_contract import allowed_fields, rejection_detail
from app.models.user import User
from app.models.voice_action import VoiceActionDraft, VoiceExecutionLog
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import SuggestedAction, SuggestedActionType
from app.services.audit_service import record_audit
from app.services.voice_action_service import _execute_one
from app.services.voice_command_service import transition
from app.services.ai_action_history_service import record_voice_action_version


class VoiceRulesEngine:
    """Deterministic authorization and workflow boundary for AI proposals."""

    _worker_actions = {SuggestedActionType.CREATE_FIELD_SUBMISSION}
    _engineer_actions = {
        SuggestedActionType.CREATE_TASK,
        SuggestedActionType.START_TASK,
        SuggestedActionType.UPDATE_TASK_PROGRESS,
        SuggestedActionType.SUBMIT_TASK_FOR_REVIEW,
        SuggestedActionType.CREATE_ISSUE,
        SuggestedActionType.ADD_TASK_NOTE,
        SuggestedActionType.CREATE_SITE_REPORT_DRAFT,
        SuggestedActionType.CREATE_TASK_MESSAGE,
        SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT,
        SuggestedActionType.SEND_PROJECT_MESSAGE,
        SuggestedActionType.SEND_OWNER_UPDATE,
    }
    _consultant_actions = {
        SuggestedActionType.PREPARE_CONSULTANT_REVIEW,
        SuggestedActionType.CREATE_ISSUE,
    }

    def validate(
        self,
        db: Session,
        *,
        command: VoiceAnalysis,
        draft: VoiceActionDraft,
        actor: User,
    ) -> SuggestedAction:
        if actor.status != UserStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="An active account is required")
        if command.user_id != actor.id:
            raise HTTPException(status_code=403, detail="Only the initiating user may execute this command")
        if not user_has_project_access(db, actor, command.project_id):
            raise HTTPException(status_code=403, detail="Project access is no longer available")
        action_type = SuggestedActionType(draft.action_type)
        allowed = (
            self._worker_actions
            if actor.role == UserRole.WORKER
            else self._engineer_actions
            if actor.role in {UserRole.ENGINEER, UserRole.PROJECT_MANAGER}
            and not is_consultant_engineer(actor)
            else self._consultant_actions
            if is_consultant_engineer(actor)
            else set()
        )
        if action_type not in allowed:
            raise HTTPException(status_code=403, detail="This role cannot execute the proposed voice action")
        if action_type == SuggestedActionType.CREATE_TASK and actor.role != UserRole.PROJECT_MANAGER:
            raise HTTPException(status_code=403, detail="Only the assigned Project Manager can create tasks")
        if draft.missing_fields:
            raise HTTPException(status_code=409, detail="Required clarification is still missing")
        minimum_photos = max(
            (
                int(item.split(":", 1)[1])
                for item in (getattr(draft, "required_evidence", None) or [])
                if item.startswith("PHOTO:")
            ),
            default=0,
        )
        if minimum_photos:
            uploaded = db.query(Attachment.id).filter(
                Attachment.entity_type == "VOICE_ANALYSIS_EVIDENCE",
                Attachment.entity_id == command.id,
                Attachment.mime_type.like("image/%"),
            ).count()
            if uploaded < minimum_photos:
                raise HTTPException(
                    status_code=409,
                    detail=f"Please upload at least {minimum_photos} required photos before confirming this action.",
                )
        if (
            float(draft.confidence) < settings.VOICE_MIN_EXECUTION_CONFIDENCE
            and draft.user_edited_payload is None
        ):
            raise HTTPException(
                status_code=409,
                detail="Low-confidence actions must be reviewed and edited before execution",
            )
        task = self._validated_task(db, command, draft)
        payload = dict(
            draft.user_edited_payload
            if draft.user_edited_payload is not None
            else draft.extracted_payload
        )
        # The allowlist and the AI prompt are generated from one table —
        # see `app.ai.action_payload_contract`. They used to be maintained
        # separately, which is how the model came to emit fields this engine
        # had never been told to expect.
        unknown_keys = set(payload) - allowed_fields(action_type)
        if unknown_keys:
            raise HTTPException(
                status_code=422,
                detail=rejection_detail(action_type, unknown_keys),
            )
        if action_type == SuggestedActionType.START_TASK:
            if task.status != TaskStatus.TODO:
                raise HTTPException(status_code=409, detail="Only a To Do task can be started")
        if action_type == SuggestedActionType.UPDATE_TASK_PROGRESS:
            proposed = float(payload.get("progressPercentage"))
            current = float(task.progress_percentage or 0)
            if not 0 <= proposed <= 100:
                raise HTTPException(status_code=422, detail="Progress must be between 0 and 100")
            if proposed < current and not bool(payload.get("correctionConfirmed")):
                raise HTTPException(
                    status_code=409,
                    detail="A progress decrease requires an explicit correction confirmation",
                )
            if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE}:
                raise HTTPException(status_code=409, detail="Task progress is locked by workflow")
        if action_type == SuggestedActionType.SUBMIT_TASK_FOR_REVIEW:
            if not task.review_required:
                raise HTTPException(status_code=409, detail="This task does not require Consultant review")
            if float(task.progress_percentage or 0) != 100:
                raise HTTPException(status_code=409, detail="Progress must be 100% before review submission")
        return SuggestedAction(
            type=action_type,
            target_id=draft.target_entity_id,
            reason="Confirmed voice command",
            payload=payload,
            confidence=max(float(draft.confidence), settings.VOICE_MIN_EXECUTION_CONFIDENCE),
        )

    @staticmethod
    def _validated_task(
        db: Session, command: VoiceAnalysis, draft: VoiceActionDraft
    ) -> Task | None:
        if not draft.target_entity_id:
            if draft.action_type in {
                SuggestedActionType.CREATE_TASK.value,
                SuggestedActionType.CREATE_ISSUE.value,
                SuggestedActionType.CREATE_SITE_REPORT_DRAFT.value,
                SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT.value,
                SuggestedActionType.SEND_PROJECT_MESSAGE.value,
                SuggestedActionType.SEND_OWNER_UPDATE.value,
            }:
                return None
            raise HTTPException(status_code=422, detail="A target task is required")
        task = db.query(Task).filter(Task.id == draft.target_entity_id).with_for_update().first()
        if not task or task.project_id != command.project_id:
            raise HTTPException(status_code=404, detail="Target task is unavailable")
        snapshot = draft.target_snapshot or {}
        expected_updated = snapshot.get("updatedAt")
        if expected_updated and task.updated_at:
            expected = datetime.fromisoformat(expected_updated.replace("Z", "+00:00"))
            current = task.updated_at
            if current.tzinfo is None and expected.tzinfo is not None:
                current = current.replace(tzinfo=expected.tzinfo)
            if current != expected:
                raise HTTPException(
                    status_code=409,
                    detail="Task changed after review. Refresh the voice command and reconfirm.",
                )
        return task

    def execute(
        self,
        db: Session,
        *,
        command: VoiceAnalysis,
        actor: User,
    ) -> list[dict]:
        if command.status == VoiceAnalysisStatus.EXECUTED:
            return list(command.action_results or [])
        if command.status != VoiceAnalysisStatus.CONFIRMED:
            raise HTTPException(status_code=409, detail="Confirm this voice command before execution")
        transition(command, VoiceAnalysisStatus.EXECUTING)
        db.commit()
        results: list[dict] = []
        priority = {
            SuggestedActionType.START_TASK.value: 10,
            SuggestedActionType.UPDATE_TASK_PROGRESS.value: 20,
            SuggestedActionType.SUBMIT_TASK_FOR_REVIEW.value: 30,
        }
        selected = sorted(
            (item for item in command.action_drafts if item.selected_for_execution),
            key=lambda item: priority.get(item.action_type, 50),
        )
        for index, draft in enumerate(selected):
            if draft.execution_status == "EXECUTED":
                continue
            before = self._task_state(db, draft.target_entity_id)
            try:
                action = self.validate(db, command=command, draft=draft, actor=actor)
                result = _execute_one(
                    db,
                    analysis=command,
                    current_user=actor,
                    action=action,
                    action_index=index,
                )
                draft = db.get(VoiceActionDraft, draft.id)
                if result.entity_id:
                    record_voice_action_version(
                        db,
                        command=command,
                        draft=draft,
                        action=action,
                        actor=actor,
                        result_entity_id=result.entity_id,
                        before_task_state=before,
                    )
                draft.execution_status = "EXECUTED"
                draft.execution_error = None
                serialized = result.model_dump(mode="json", by_alias=True)
                results.append(serialized)
                after = self._task_state(db, draft.target_entity_id)
                # A command may intentionally contain ordered actions for the
                # same task (for example 100% then submit for review). Carry
                # forward only this command's just-committed state; unrelated
                # concurrent changes still fail the snapshot check.
                if after and draft.target_entity_id:
                    for pending in selected[index + 1:]:
                        if pending.target_entity_id == draft.target_entity_id:
                            pending.target_snapshot = {
                                "taskId": str(draft.target_entity_id),
                                **after,
                            }
                db.add(VoiceExecutionLog(
                    voice_analysis_id=command.id,
                    voice_action_draft_id=draft.id,
                    actor_user_id=actor.id,
                    action_type=draft.action_type,
                    target_type=draft.target_entity_type,
                    target_id=draft.target_entity_id,
                    before_state=before,
                    after_state=after,
                    result="EXECUTED",
                ))
                db.commit()
            except HTTPException as exc:
                db.rollback()
                command = db.get(VoiceAnalysis, command.id)
                draft = db.get(VoiceActionDraft, draft.id)
                draft.execution_status = "FAILED"
                draft.execution_error = str(exc.detail)
                results.append({
                    "actionIndex": index,
                    "type": draft.action_type,
                    "success": False,
                    "status": "REJECTED",
                    "message": str(exc.detail),
                })
                db.add(VoiceExecutionLog(
                    voice_analysis_id=command.id,
                    voice_action_draft_id=draft.id,
                    actor_user_id=actor.id,
                    action_type=draft.action_type,
                    target_type=draft.target_entity_type,
                    target_id=draft.target_entity_id,
                    before_state=before,
                    result="REJECTED",
                    error=str(exc.detail),
                ))
                db.commit()
        command = db.get(VoiceAnalysis, command.id)
        command.action_results = results
        successful = sum(item.get("success") is True for item in results)
        transition(
            command,
            VoiceAnalysisStatus.EXECUTED
            if selected and successful == len(selected)
            else VoiceAnalysisStatus.PARTIALLY_EXECUTED,
        )
        record_audit(
            db,
            actor_id=actor.id,
            action="voice_command_executed",
            entity_type="voice_analysis",
            entity_id=command.id,
            project_id=command.project_id,
            details={"successful": successful, "selected": len(selected)},
        )
        db.commit()
        return results

    @staticmethod
    def _task_state(db: Session, task_id: UUID | None) -> dict | None:
        task = db.get(Task, task_id) if task_id else None
        if not task:
            return None
        return {
            "status": task.status.value,
            "progressPercentage": float(task.progress_percentage or 0),
            "updatedAt": task.updated_at.isoformat(),
        }
