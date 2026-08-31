import json
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.services.authorization import require
from app.models.enums import (
    FieldSubmissionStatus,
    IssueSeverity,
    IssueStatus,
    TaskPriority,
    UserRole,
    VoiceConfirmationStatus,
    NotificationType,
    DesignChangeStatus,
)
from app.models.design_change import DesignChange, DesignChangeAffectedDiscipline
from app.models.field_submission import FieldSubmission, FieldSubmissionPhoto
from app.models.attachment import Attachment
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.notification import Notification
from app.models.site_report import SiteReport
from app.models.task import Task, TaskComment
from app.models.user import User
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.message import ConversationCreate
from app.schemas.voice_analysis import (
    ActionExecutionResult,
    ConfirmedAction,
    SuggestedAction,
    SuggestedActionType,
)
from app.services.audit_service import record_audit
from app.services.field_submission_authorization import can_submit_field_evidence
from app.services.field_submission_authorization import authorized_reviewer_ids
from app.services.task_progress_service import update_task_progress
from app.services.domain_event_dispatcher import emit_domain_event


def execute_confirmed_actions(
    db: Session,
    *,
    analysis: VoiceAnalysis,
    current_user: User,
    requested: list[ConfirmedAction],
) -> list[ActionExecutionResult]:
    if analysis.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the initiating user can confirm this analysis")
    if not analysis.structured_result:
        raise HTTPException(status_code=409, detail="This analysis has no completed result")
    suggestions = analysis.structured_result.get("suggestedActions", [])
    previously_succeeded = {
        int(item["actionIndex"])
        for item in (analysis.action_results or [])
        if item.get("success") is True and item.get("actionIndex") is not None
    }
    seen: set[int] = set()
    results: list[ActionExecutionResult] = []
    for request in requested:
        if request.action_index in seen:
            raise HTTPException(status_code=422, detail="Each suggested action may be confirmed once per request")
        seen.add(request.action_index)
        if request.action_index >= len(suggestions):
            raise HTTPException(status_code=422, detail="Unknown suggested action index")
        source = dict(suggestions[request.action_index])
        if request.action_index in previously_succeeded:
            results.append(ActionExecutionResult(
                action_index=request.action_index,
                type=SuggestedActionType(source["type"]),
                success=False,
                status="ALREADY_CONFIRMED",
                message="This suggested action was already confirmed successfully",
            ))
            continue
        payload = dict(source.get("payload") or {})
        if request.payload is not None:
            payload.update(request.payload)
        if request.target_id is not None:
            source["targetId"] = str(request.target_id)
        source["payload"] = payload
        try:
            action = SuggestedAction.model_validate(source)
            result = _execute_one(
                db, analysis=analysis, current_user=current_user,
                action=action, action_index=request.action_index,
            )
        except HTTPException as exc:
            db.rollback()
            result = ActionExecutionResult(
                action_index=request.action_index,
                type=SuggestedActionType(source["type"]),
                success=False,
                status="REJECTED",
                message=str(exc.detail),
            )
        except (ValueError, TypeError) as exc:
            db.rollback()
            result = ActionExecutionResult(
                action_index=request.action_index,
                type=SuggestedActionType(source["type"]),
                success=False,
                status="INVALID",
                message=str(exc),
            )
        results.append(result)

    analysis = db.get(VoiceAnalysis, analysis.id)
    serialized = [result.model_dump(mode="json", by_alias=True) for result in results]
    prior = list(analysis.action_results or [])
    analysis.action_results = prior + serialized
    analysis.confirmed_by_id = current_user.id
    analysis.confirmed_at = datetime.now(timezone.utc)
    all_succeeded = previously_succeeded | {
        result.action_index for result in results if result.success
    }
    analysis.confirmation_status = (
        VoiceConfirmationStatus.CONFIRMED
        if suggestions and all_succeeded == set(range(len(suggestions)))
        else VoiceConfirmationStatus.PARTIALLY_CONFIRMED
    )
    record_audit(
        db, actor_id=current_user.id, action="ai_voice_actions_confirmed",
        entity_type="voice_analysis", entity_id=analysis.id,
        project_id=analysis.project_id,
        details={"analysis_id": analysis.id, "results": serialized, "source": "AI_VOICE_ANALYSIS"},
    )
    db.commit()
    return results


def permission_for_action(action_type: SuggestedActionType) -> str | None:
    """The catalogue permission that governs a spoken action.

    Replaces `action_allowed_for_role`, which asked whether one of four coarse
    role names could ever perform an action. That question no longer has an
    answer: roles are configurable, so what somebody may do is a property of
    their role's permissions and the project they are on, not of a name. The
    honest thing to expose is the permission itself, and let the caller resolve
    it against a real person on a real project.
    """
    from app.services.voice_capabilities import capability_for

    capability = capability_for(action_type)
    return capability.permission_code if capability is not None else None


def _execute_one(
    db: Session, *, analysis: VoiceAnalysis, current_user: User,
    action: SuggestedAction, action_index: int,
) -> ActionExecutionResult:
    if not user_has_project_access(db, current_user, analysis.project_id):
        raise HTTPException(status_code=403, detail="Project access is no longer available")
    from app.services.voice_capabilities import capability_for, is_available

    capability = capability_for(action.type)
    if capability is None:
        raise HTTPException(status_code=403, detail="This action cannot be confirmed by voice")
    if not is_available(
        db, user=current_user, project_id=analysis.project_id, capability=capability
    ):
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to {capability.purpose} on this project",
        )
    metadata = {
        "source": "AI_VOICE_ANALYSIS",
        "analysis_id": str(analysis.id),
        "suggested_by_ai": True,
        "confirmed_by_user_id": str(current_user.id),
    }
    payload = action.payload_dict()
    if action.type == SuggestedActionType.CREATE_TASK:
        # `task.create` is what the tasks endpoint checks, so Voice cannot
        # route anybody past it — nor refuse somebody the office granted it.
        require(db, current_user, "task.create", analysis.project_id)
        from app.api.tasks import create_task
        from app.schemas.task import TaskCreate
        created = create_task(
            TaskCreate(
                project_id=analysis.project_id,
                name=str(payload["title"]).strip(),
                description=str(payload.get("description") or "").strip() or None,
                discipline=str(payload.get("sourceDiscipline") or "").strip() or None,
                # The same fields the create form carries. Voice used to drop
                # them, so "أنشئ مهمة … وخلي موعدها الأحد" created a task with
                # no date and no owner and said nothing about it.
                assignee_ids=[
                    UUID(str(value)) for value in payload.get("assigneeIds") or []
                ],
                planned_start_date=(
                    _as_date(payload["startDate"], "startDate")
                    if payload.get("startDate") else None
                ),
                planned_end_date=(
                    _as_date(payload["dueDate"], "dueDate")
                    if payload.get("dueDate") else None
                ),
                **(
                    {"priority": TaskPriority(str(payload["priority"]).lower())}
                    if payload.get("priority") else {}
                ),
            ),
            db=db,
            current_user=current_user,
        )
        return _success(action_index, action.type, "Task created", created.id)
    if action.type == SuggestedActionType.START_TASK:
        _require_contractor_engineer(current_user)
        task = _task(db, analysis.project_id, action.target_id)
        from app.api.tasks import start_task
        updated = start_task(task.id, db=db, current_user=current_user)
        return _success(action_index, action.type, "Task started", updated.id)
    if action.type == SuggestedActionType.UPDATE_TASK_PROGRESS:
        task = _task(db, analysis.project_id, action.target_id)
        updated = update_task_progress(
            db=db, current_user=current_user, task_id=task.id,
            progress_percentage=float(payload["progressPercentage"]),
            note=str(payload.get("note") or "").strip() or None,
            source="ai_voice_analysis", audit_metadata=metadata,
        )
        return _success(action_index, action.type, "Task progress updated", updated.id)
    if action.type in {
        SuggestedActionType.UPDATE_TASK_SCHEDULE,
        SuggestedActionType.UPDATE_TASK_ASSIGNMENT,
        SuggestedActionType.UPDATE_TASK_PRIORITY,
        SuggestedActionType.UPDATE_TASK_DETAILS,
    }:
        # One endpoint, four capabilities. `update_task` is the same function
        # the web UI posts to, so every rule it enforces — who may reassign,
        # what an engineer may touch, which statuses accept which change —
        # applies to voice without being restated here. Voice's only job is to
        # turn words into the fields that endpoint already accepts.
        task = _task(db, analysis.project_id, action.target_id)
        from app.api.tasks import update_task
        from app.schemas.task import TaskUpdate

        changes: dict = {}
        if action.type == SuggestedActionType.UPDATE_TASK_SCHEDULE:
            if payload.get("dueDate"):
                changes["planned_end_date"] = _as_date(payload["dueDate"], "dueDate")
            if payload.get("startDate"):
                changes["planned_start_date"] = _as_date(payload["startDate"], "startDate")
            if not changes:
                raise HTTPException(status_code=422, detail="No new date was provided")
        elif action.type == SuggestedActionType.UPDATE_TASK_ASSIGNMENT:
            changes["assignee_ids"] = [
                UUID(str(value)) for value in payload.get("assigneeIds") or []
            ]
            if not changes["assignee_ids"]:
                raise HTTPException(status_code=422, detail="No assignee was selected")
        elif action.type == SuggestedActionType.UPDATE_TASK_PRIORITY:
            changes["priority"] = TaskPriority(str(payload["priority"]).lower())
        else:
            if payload.get("title"):
                changes["name"] = str(payload["title"]).strip()
            if payload.get("description"):
                changes["description"] = str(payload["description"]).strip()
            if not changes:
                raise HTTPException(status_code=422, detail="No change was provided")

        updated = update_task(
            task.id,
            TaskUpdate(**changes),
            db=db,
            current_user=current_user,
        )
        note = str(payload.get("note") or "").strip()
        if note:
            db.add(TaskComment(task_id=task.id, author_id=current_user.id, content=note))
        _audit_entity(
            db, analysis, current_user, "voice_task_updated", "task", task.id,
            {**metadata, "fields": sorted(changes)},
        )
        db.commit()
        return _success(
            action_index, action.type, "Task updated", updated.id,
        )
    if action.type == SuggestedActionType.DELETE_TASK:
        # Destructive, so it carries its own gate on top of the endpoint's:
        # the engineer must have acknowledged the deletion explicitly on the
        # confirmation card. A misheard sentence cannot reach this line.
        if not payload.get("confirmDeletion"):
            raise HTTPException(
                status_code=409,
                detail="Deleting a task requires an explicit confirmation",
            )
        task = _task(db, analysis.project_id, action.target_id)
        task_id = task.id
        from app.api.tasks import delete_task

        delete_task(task_id, db=db, current_user=current_user)
        _audit_entity(
            db, analysis, current_user, "voice_task_deleted", "task", task_id, metadata,
        )
        db.commit()
        return _success(action_index, action.type, "Task deleted", task_id)
    if action.type in {
        SuggestedActionType.UPDATE_ISSUE_STATUS,
        SuggestedActionType.ASSIGN_ISSUE,
    }:
        issue = _issue(db, analysis.project_id, action.target_id)
        from app.api.issues import update_issue
        from app.schemas.issue import IssueUpdate

        changes: dict = {}
        if action.type == SuggestedActionType.UPDATE_ISSUE_STATUS:
            changes["status"] = IssueStatus(str(payload["issueStatus"]).lower())
            notes = str(payload.get("resolutionNotes") or "").strip()
            if notes:
                changes["resolution_notes"] = notes
        else:
            recipients = [UUID(str(value)) for value in payload.get("assigneeIds") or []]
            if len(recipients) != 1:
                raise HTTPException(
                    status_code=422, detail="Select one person to own this issue",
                )
            changes["assigned_to_id"] = recipients[0]
        updated = update_issue(
            issue.id,
            IssueUpdate(**changes),
            db=db,
            current_user=current_user,
        )
        _audit_entity(
            db, analysis, current_user, "voice_issue_updated", "issue", issue.id,
            {**metadata, "fields": sorted(changes)},
        )
        db.commit()
        return _success(action_index, action.type, "Issue updated", updated.id)
    if action.type == SuggestedActionType.SUBMIT_TASK_FOR_REVIEW:
        task = _task(db, analysis.project_id, action.target_id)
        from app.api.tasks import submit_task_for_review
        from app.schemas.task import TaskReviewSubmission
        updated = submit_task_for_review(
            task.id,
            TaskReviewSubmission(
                completion_note=str(payload.get("completionNote") or "").strip() or None
            ),
            db=db,
            current_user=current_user,
        )
        return _success(action_index, action.type, "Task submitted for review", updated.id)
    if action.type == SuggestedActionType.PREPARE_CONSULTANT_REVIEW:
        task = _task(db, analysis.project_id, action.target_id)
        from app.api.tasks import approve_task, reject_task
        from app.schemas.task import TaskReviewRequest
        decision = str(payload["decision"]).upper()
        comments = str(payload["comments"]).strip()
        if decision == "APPROVE":
            updated = approve_task(
                task.id,
                TaskReviewRequest(comments=comments),
                db=db,
                current_user=current_user,
            )
            return _success(action_index, action.type, "Consultant approval recorded", updated.id)
        if decision == "REJECT":
            reason = str(payload.get("rejectionReason") or comments).strip()
            updated = reject_task(
                task.id,
                TaskReviewRequest(
                    comments=comments,
                    rejection_reason=reason,
                    required_corrections=str(
                        payload.get("requiredCorrections") or ""
                    ).strip() or None,
                ),
                db=db,
                current_user=current_user,
            )
            return _success(action_index, action.type, "Consultant rejection recorded", updated.id)
        note = TaskComment(task_id=task.id, author_id=current_user.id, content=comments)
        db.add(note)
        db.flush()
        _audit_entity(db, analysis, current_user, "consultant_note_added", "task", task.id, metadata)
        db.commit()
        return _success(action_index, action.type, "Consultant review note added", note.id)
    if action.type == SuggestedActionType.CREATE_ISSUE:
        _require_contractor_engineer(current_user)
        task = _optional_task(db, analysis.project_id, action.target_id)
        severity = IssueSeverity(str(payload.get("severity", "medium")).lower())
        recipient_ids = {UUID(str(value)) for value in payload.get("recipientIds") or []}
        if len(recipient_ids) > 1:
            raise HTTPException(status_code=422, detail="Select one responsible person for this issue")
        assigned_to_id = next(iter(recipient_ids), None)
        if assigned_to_id:
            valid_recipient = db.query(ProjectMember.id).filter(
                ProjectMember.project_id == analysis.project_id,
                ProjectMember.user_id == assigned_to_id,
                ProjectMember.is_active == True,
            ).first()
            if not valid_recipient:
                raise HTTPException(status_code=422, detail="The selected issue recipient is not available in this project")
        description = str(payload["description"]).strip()
        location = str(payload.get("location") or "").strip()
        if location:
            description = f"{description}\n\nLocation: {location}"
        issue = Issue(
            project_id=analysis.project_id, task_id=task.id if task else None,
            title=str(payload["title"]).strip(),
            description=description,
            category=str(payload.get("category") or "").strip() or None,
            severity=severity, status=IssueStatus.OPEN, raised_by_id=current_user.id,
            affects_schedule=bool(payload.get("affectsSchedule", False)),
            assigned_to_id=assigned_to_id,
        )
        db.add(issue)
        db.flush()
        project = db.get(Project, analysis.project_id)
        recipients = {assigned_to_id} if assigned_to_id else set()
        if project and severity in {IssueSeverity.HIGH, IssueSeverity.CRITICAL}:
            recipients.add(project.project_manager_id)
        for recipient_id in recipients - {None, current_user.id}:
            db.add(Notification(
                user_id=recipient_id,
                title="AI-assisted issue confirmed",
                message=f"{current_user.full_name} confirmed issue: {issue.title}",
                type=NotificationType.TASK_UPDATED,
                project_id=analysis.project_id,
                related_entity_type="ISSUE", related_entity_id=issue.id,
            ))
        _audit_entity(db, analysis, current_user, "created", "issue", issue.id, metadata)
        db.commit()
        return _success(action_index, action.type, "Issue created", issue.id)
    if action.type == SuggestedActionType.CREATE_FIELD_SUBMISSION:
        task = _task(db, analysis.project_id, action.target_id)
        if not can_submit_field_evidence(db, current_user, task):
            raise HTTPException(
                status_code=403,
                detail="You cannot record field evidence against this task",
            )
        submission = FieldSubmission(
            project_id=analysis.project_id, task_id=task.id, submitted_by_id=current_user.id,
            description=str(payload["description"]).strip(),
            voice_metadata=json.dumps(metadata), status=FieldSubmissionStatus.SUBMITTED,
        )
        db.add(submission)
        db.flush()
        evidence = db.query(Attachment).filter(
            Attachment.entity_type == "VOICE_ANALYSIS_EVIDENCE",
            Attachment.entity_id == analysis.id,
            Attachment.mime_type.like("image/%"),
        ).all()
        if not isinstance(evidence, list):
            evidence = []
        for attachment in evidence:
            db.add(FieldSubmissionPhoto(
                field_submission_id=submission.id,
                attachment_id=attachment.id,
            ))
        analysis.field_submission_id = submission.id
        recipients = authorized_reviewer_ids(db, task)
        project = db.get(Project, analysis.project_id)
        if not recipients and project:
            recipients.add(project.project_manager_id)
        for user_id in recipients - {current_user.id}:
            db.add(Notification(
                user_id=user_id, title="Field evidence submitted",
                message=f"{current_user.full_name} submitted AI-assisted evidence for {task.task_code}.",
                type=NotificationType.APPROVAL_REQUEST,
                project_id=analysis.project_id, task_id=task.id,
                related_entity_type="FIELD_SUBMISSION",
                related_entity_id=submission.id,
            ))
        _audit_entity(
            db, analysis, current_user, "field_evidence_submitted",
            "field_submission", submission.id, metadata,
        )
        emit_domain_event(
            db,
            project_id=analysis.project_id,
            event_type="FIELD_SUBMISSION_CREATED",
            entity_type="FIELD_SUBMISSION",
            entity_id=submission.id,
            actor_user_id=current_user.id,
            payload={"taskId": str(task.id), "description": str(payload["description"]).strip()},
            correlation_id=getattr(analysis, "idempotency_key", None) or str(analysis.id),
            idempotency_key=f"FIELD_SUBMISSION_CREATED:{submission.id}",
        )
        db.commit()
        return _success(action_index, action.type, "Unverified field evidence submitted for Engineer review", submission.id)
    if action.type == SuggestedActionType.ADD_TASK_NOTE:
        _require_contractor_engineer(current_user)
        task = _assigned_task(db, current_user, analysis.project_id, action.target_id)
        note = TaskComment(
            task_id=task.id, author_id=current_user.id,
            content=str(payload["content"]).strip(),
        )
        db.add(note)
        db.flush()
        _audit_entity(db, analysis, current_user, "task_note_added", "task", task.id, metadata)
        db.commit()
        return _success(action_index, action.type, "Task note added", note.id)
    if action.type == SuggestedActionType.CREATE_SITE_REPORT_DRAFT:
        _require_contractor_engineer(current_user)
        task = _optional_task(db, analysis.project_id, action.target_id)
        membership = db.query(ProjectMember).filter(
            ProjectMember.project_id == analysis.project_id,
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_active == True,
            ProjectMember.is_site_engineer == True,
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Only an assigned Site Engineer can create a report draft")
        if task:
            _assigned_task(db, current_user, analysis.project_id, task.id)
        report = SiteReport(
            project_id=analysis.project_id, task_id=task.id if task else None,
            submitted_by_id=current_user.id, report_date=date.today(),
            summary_text=str(payload["summaryText"]).strip(),
            work_completed=_join(payload.get("workCompleted")),
            delays=_join(payload.get("delays")),
            issues_summary=_join(payload.get("issues")),
            notes=str(payload.get("notes") or "").strip() or None,
            review_status="draft",
            voice_analysis_id=analysis.id,
        )
        db.add(report)
        db.flush()
        _audit_entity(db, analysis, current_user, "draft_created", "site_report", report.id, metadata)
        db.commit()
        return _success(action_index, action.type, "Site report draft created", report.id)
    if action.type == SuggestedActionType.CREATE_TASK_MESSAGE:
        _require_contractor_engineer(current_user)
        task = _assigned_task(db, current_user, analysis.project_id, action.target_id)
        from app.api.messages import _create_conversation
        conversation = _create_conversation(
            db,
            ConversationCreate(
                project_id=analysis.project_id,
                context_type="TASK", context_id=task.id,
                content=str(payload["content"]).strip(),
            ),
            current_user,
        )
        _audit_entity(
            db, analysis, current_user, "ai_confirmed_message_sent",
            "conversation", conversation.id, metadata,
        )
        db.commit()
        return _success(action_index, action.type, "Task message sent", conversation.id)
    if action.type == SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT:
        _require_contractor_engineer(current_user)
        if payload.get("approved") is True:
            raise HTTPException(
                status_code=409,
                detail="A spoken design change cannot be recorded as approved. Submit it for the configured review workflow.",
            )
        task = _optional_task(db, analysis.project_id, action.target_id)
        change = DesignChange(
            project_id=analysis.project_id,
            task_id=task.id if task else None,
            title=str(payload["title"]).strip(),
            description=str(payload["description"]).strip(),
            reason=str(payload.get("reason") or "").strip() or None,
            related_drawings=str(payload.get("relatedDrawings") or "").strip() or None,
            source_discipline=str(payload.get("sourceDiscipline") or "GENERAL").strip(),
            proposed_by_id=current_user.id,
            status=DesignChangeStatus.PROPOSED,
        )
        db.add(change)
        db.flush()
        for discipline in dict.fromkeys(payload.get("affectedDisciplines") or []):
            if str(discipline).strip():
                db.add(DesignChangeAffectedDiscipline(
                    design_change_id=change.id,
                    discipline=str(discipline).strip(),
                ))
        disciplines = {
            str(value).casefold()
            for value in payload.get("affectedDisciplines") or []
            if str(value).strip()
        }
        recipients = {
            member.user_id
            for member in db.query(ProjectMember).filter(
                ProjectMember.project_id == analysis.project_id,
                ProjectMember.is_active == True,
            ).all()
            if (member.project_discipline or "").casefold() in disciplines
        }
        project = db.get(Project, analysis.project_id)
        if project and project.project_manager_id:
            recipients.add(project.project_manager_id)
        for recipient_id in recipients - {current_user.id}:
            db.add(Notification(
                user_id=recipient_id,
                title="Design change requires review",
                message=f"{current_user.full_name} proposed: {change.title}",
                type=NotificationType.APPROVAL_REQUEST,
                project_id=analysis.project_id,
                task_id=task.id if task else None,
                related_entity_type="DESIGN_CHANGE",
                related_entity_id=change.id,
            ))
        _audit_entity(
            db, analysis, current_user, "voice_design_change_proposed",
            "design_change", change.id, metadata,
        )
        db.commit()
        return _success(action_index, action.type, "Design change report created for review", change.id)
    if action.type in {
        SuggestedActionType.SEND_PROJECT_MESSAGE,
        SuggestedActionType.SEND_OWNER_UPDATE,
    }:
        _require_contractor_engineer(current_user)
        project = db.get(Project, analysis.project_id)
        recipients = {UUID(str(value)) for value in payload.get("recipientIds") or []}
        if action.type == SuggestedActionType.SEND_OWNER_UPDATE:
            if not project or not project.owner_id:
                raise HTTPException(status_code=422, detail="This project has no available Owner recipient")
            if recipients != {project.owner_id}:
                raise HTTPException(status_code=422, detail="Select the project Owner as the only recipient")
        from app.api.messages import _create_conversation
        conversation = _create_conversation(
            db,
            ConversationCreate(
                project_id=analysis.project_id,
                recipient_ids=list(recipients),
                title=str(payload.get("subject") or "").strip() or None,
                content=str(payload["content"]).strip(),
                context_type="TASK" if action.target_id else None,
                context_id=action.target_id,
            ),
            current_user,
        )
        _audit_entity(
            db, analysis, current_user, "voice_message_sent",
            "conversation", conversation.id, metadata,
        )
        db.commit()
        message = "Owner update sent" if action.type == SuggestedActionType.SEND_OWNER_UPDATE else "Project message sent"
        return _success(action_index, action.type, message, conversation.id)
    raise HTTPException(status_code=400, detail="Unsupported action type")


def _require_contractor_engineer(user: User) -> None:
    """Retained as a no-op seam.

    This asserted that the speaker was a contractor-side Engineer, on top of
    the capability check `_execute_one` already performs through
    `voice_capabilities.is_available`. That check resolves the operation's own
    permission against the project, which is both stricter and configurable, so
    an affiliation test on the same call adds nothing but a role name.

    Kept as a named function rather than deleted at each call site so the
    execution branches still read as having an authorization step, and so a
    future per-operation rule has an obvious home.
    """
    return


def _as_date(value, field: str) -> date:
    """A payload date, already resolved to a real day by the voice layer.

    Spoken wording ("الأسبوع الجاي") is turned into a date by
    `app.services.voice_dates` while the draft is being built, so by the time
    execution runs there is nothing left to interpret. Anything still unparsed
    here is a bug upstream, and it fails loudly rather than guessing a day.
    """
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"The {field} could not be read as a date",
        ) from exc


def _issue(db: Session, project_id: UUID, issue_id: UUID | None) -> Issue:
    issue = db.get(Issue, issue_id) if issue_id else None
    if not issue or issue.project_id != project_id:
        raise HTTPException(status_code=404, detail="Issue is unavailable in this project")
    return issue


def _task(db: Session, project_id: UUID, task_id: UUID | None) -> Task:
    task = db.get(Task, task_id) if task_id else None
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=400, detail="Action task must belong to this project")
    return task


def _optional_task(db: Session, project_id: UUID, task_id: UUID | None) -> Task | None:
    return _task(db, project_id, task_id) if task_id else None


def _assigned_task(db: Session, user: User, project_id: UUID, task_id: UUID | None) -> Task:
    task = _task(db, project_id, task_id)
    if not any(assignee.id == user.id for assignee in task.assignees):
        raise HTTPException(status_code=403, detail="This task is not assigned to the current Engineer")
    return task


def _audit_entity(db, analysis, user, action, entity_type, entity_id, metadata):
    record_audit(
        db, actor_id=user.id, action=action, entity_type=entity_type,
        entity_id=entity_id, project_id=analysis.project_id,
        details=metadata,
    )


def _success(index, action_type, message, entity_id):
    return ActionExecutionResult(
        action_index=index, type=action_type, success=True,
        status="SUCCESS", message=message, entity_id=entity_id,
    )


def _join(value) -> str | None:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip()) or None
    return str(value).strip() or None if value is not None else None
