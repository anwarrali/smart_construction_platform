from __future__ import annotations

import logging

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
from app.services.voice_action_errors import (
    ASSIGNEE_NOT_ELIGIBLE,
    ASSIGNEE_REQUIRED,
    TARGET_TASK_NOT_FOUND,
    VoiceActionError,
    classify,
    missing_field_failure,
    success_message,
)
from app.services.voice_capabilities import capability_for, is_available, voice_role


logger = logging.getLogger(__name__)


class VoiceRulesEngine:
    """Deterministic authorization and workflow boundary for AI proposals."""


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
        # The registry is the one list of who may do what — see
        # `app.services.voice_capabilities`. It used to be repeated here as
        # three sets, which is how a new capability could reach execution
        # without anybody deciding which roles it belonged to.
        capability = capability_for(action_type)
        if capability is None or voice_role(actor) not in capability.roles:
            # The reason is named rather than generic, because this string is
            # what support reads in the execution log when somebody asks why a
            # spoken instruction did nothing.
            raise HTTPException(
                status_code=403,
                detail=(
                    "Only the assigned Project Manager can perform this action"
                    if capability is not None and capability.roles == {"project_manager"}
                    else "This role cannot execute the proposed voice action"
                ),
            )
        if not is_available(
            db, user=actor, project_id=command.project_id, capability=capability
        ):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action on this project",
            )
        if draft.missing_fields:
            # Named rather than generic. "لسه في معلومة ناقصة" is true of every
            # incomplete draft and useful for none of them; the outstanding
            # field already has a question written in the engineer's language,
            # and the refusal says exactly that.
            raise missing_field_failure(list(draft.missing_fields))
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
        if action_type == SuggestedActionType.UPDATE_TASK_ASSIGNMENT:
            self._validated_assignees(db, command, payload)
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
    def _validated_assignees(db: Session, command: VoiceAnalysis, payload: dict) -> None:
        """Refuse an assignment the tasks API is going to refuse anyway.

        The check itself is not new — `app.api.tasks` has always enforced it,
        and still does. What is new is *where the engineer hears about it*: the
        same rule applied here turns a 400 whose sentence the client could not
        show into a reason in their own language, naming the person and saying
        who may hold work. Nothing is widened; a name that passes here is
        validated again by the endpoint that performs the change.
        """
        from app.services.voice_entity_resolution import assignable_people

        proposed = [str(value) for value in payload.get("assigneeIds") or []]
        if not proposed:
            raise VoiceActionError(
                ASSIGNEE_REQUIRED,
                detail="No assignee was selected for this task",
                status_code=422,
            )
        eligible = {
            str(person.user_id): person
            for person in assignable_people(db, project_id=command.project_id)
        }
        refused = [value for value in proposed if value not in eligible]
        if not refused:
            return
        raise VoiceActionError(
            ASSIGNEE_NOT_ELIGIBLE,
            detail=(
                "Every assignee must be an active Engineer, Worker, Consultant, "
                "or this project's assigned Project Manager"
            ),
            status_code=400,
        )

    @staticmethod
    def _validated_task(
        db: Session, command: VoiceAnalysis, draft: VoiceActionDraft
    ) -> Task | None:
        capability = capability_for(draft.action_type)
        if capability is not None and capability.needs_issue:
            # Issue capabilities target an issue, and `app.api.issues.update_issue`
            # validates it — including who is allowed to change what on it.
            if not draft.target_entity_id:
                raise HTTPException(status_code=422, detail="A target issue is required")
            return None
        if not draft.target_entity_id:
            if capability is not None and not capability.needs_task:
                return None
            raise HTTPException(status_code=422, detail="A target task is required")
        task = db.query(Task).filter(Task.id == draft.target_entity_id).with_for_update().first()
        if not task or task.project_id != command.project_id:
            raise VoiceActionError(
                TARGET_TASK_NOT_FOUND,
                detail="Target task is unavailable",
                status_code=404,
            )
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
        # Every sentence this run produces is in the language the command was
        # spoken in, which the interpretation step recorded.
        language = str(
            (command.provider_metadata or {}).get("replyLanguage") or "en"
        )
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
                # Only ever said once the operation returned: the assistant
                # reports what the backend confirmed, never what it proposed.
                result = result.model_copy(update={
                    "user_message": success_message(draft.action_type, language),
                })
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
                # The raised sentence is developer English written for logs.
                # Classifying it here is what turns "At least one authorized
                # recipient is required" into "لمين بدك أبعت الرسالة؟" instead
                # of the client's one generic "something went wrong".
                failure = classify(exc)
                logger.info(
                    "voice action %s rejected: %s (%s)",
                    draft.action_type, failure.error_code, exc.detail,
                )
                results.append({
                    "actionIndex": index,
                    "type": draft.action_type,
                    "success": False,
                    "status": "REJECTED",
                    "message": str(exc.detail),
                    "errorCode": failure.error_code,
                    "userMessage": failure.text_for(language),
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
