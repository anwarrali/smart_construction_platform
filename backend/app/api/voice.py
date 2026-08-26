import logging
from datetime import date, datetime, time, timedelta, timezone
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.ai import _process_analysis, _read_limited_audio
from app.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIProviderTimeoutError,
    InvalidAudioError,
)
from app.ai.construction_analysis_service import ConstructionVoiceAnalysisService
from app.ai.transcription_service import validate_audio
from app.core.config import settings
from app.core.deps import get_current_user, is_worker, user_has_project_access
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.enums import VoiceAnalysisStatus
from app.models.task import Task
from app.models.user import User
from app.models.voice_action import VoiceActionDraft, VoiceClarification, VoiceExecutionLog
from app.models.voice_analysis import VoiceAnalysis
from app.models.ai_governance import AIProviderCall
from app.schemas.voice_analysis import SuggestedActionType
from app.schemas.voice_command import (
    VoiceClarificationAnswer,
    VoiceCommandOut,
    VoiceCommandPage,
    VoiceConfirmRequest,
    VoiceDraftUpdate,
    VoiceExecuteRequest,
    VoiceReportReadinessOut,
    VoiceReportUpdateOut,
    VoiceTaskCandidateOut,
    VoiceTaskCandidatesOut,
    VoiceTranscriptCommandCreate,
)
from app.services.audit_service import record_audit
from app.services.file_storage import save_private_upload
from app.services.voice_analysis_authorization import (
    authorized_voice_tasks,
    can_create_voice_analysis,
)
from app.services.voice_command_service import (
    answer_clarification,
    assert_command_access,
    assert_version,
    transition,
    update_draft,
    interpret_command,
)
from app.services.voice_rules_engine import VoiceRulesEngine
from app.services.voice_context_builder import VoiceContextBuilder
from app.services.voice_capabilities import DESTRUCTIVE
from app.services.voice_conversation_service import find_open_request
from app.services.voice_language import reply_language
from app.services.voice_task_matcher import MAX_CANDIDATES, match_task


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice Commands"])


def _provider_role(user: User) -> str:
    return (
        "worker"
        if is_worker(user)
        else "external_consultant"
        if getattr(user, "engineer_affiliation", None) == "external_consultant"
        else "contractor_engineer"
        if user.role.value == "engineer"
        else user.role.value
    )


def _command(db: Session, command_id: UUID, user: User, *, owner_only: bool = False) -> VoiceAnalysis:
    command = db.get(VoiceAnalysis, command_id)
    if not command:
        raise HTTPException(status_code=404, detail="Voice command not found")
    assert_command_access(db, command, user, owner_only=owner_only)
    return command


@router.post("/commands", response_model=VoiceCommandOut, status_code=201)
async def create_voice_command(
    project_id: UUID = Form(...),
    task_id: UUID | None = Form(default=None),
    duration_seconds: int | None = Form(default=None, ge=1),
    idempotency_key: str | None = Form(default=None, min_length=8, max_length=100),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not settings.VOICE_FEATURE_ENABLED:
        raise HTTPException(status_code=503, detail="Voice reporting is not enabled")
    if duration_seconds and duration_seconds > settings.VOICE_MAX_DURATION_SECONDS:
        raise HTTPException(status_code=413, detail="Recording exceeds the configured duration limit")
    if idempotency_key:
        existing = db.query(VoiceAnalysis).filter(
            VoiceAnalysis.user_id == current_user.id,
            VoiceAnalysis.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return existing
    recent_count = db.query(VoiceAnalysis.id).filter(
        VoiceAnalysis.user_id == current_user.id,
        VoiceAnalysis.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
    ).count()
    if recent_count >= 50:
        raise HTTPException(
            status_code=429,
            detail="Voice processing limit reached. Try again later.",
        )
    task = db.get(Task, task_id) if task_id else None
    if not can_create_voice_analysis(db, current_user, project_id, task):
        raise HTTPException(status_code=403, detail="Voice reporting is not allowed in this context")
    content = await _read_limited_audio(audio)
    filename = audio.filename or "recording.m4a"
    content_type = audio.content_type or "application/octet-stream"
    try:
        validate_audio(filename, content_type, content)
    except InvalidAudioError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    await audio.seek(0)
    command_id = uuid4()
    storage_key, file_size = await save_private_upload(audio, "audio")
    attachment = Attachment(
        original_filename=filename,
        storage_key=storage_key,
        file_url=f"protected://voice-command/{command_id}",
        mime_type=content_type,
        file_size_bytes=file_size,
        uploaded_by_id=current_user.id,
        project_id=project_id,
        entity_type="VOICE_ANALYSIS",
        entity_id=command_id,
    )
    command = VoiceAnalysis(
        id=command_id,
        project_id=project_id,
        user_id=current_user.id,
        task_id=task.id if task else None,
        role_at_recording_time=current_user.role.value,
        duration_seconds=duration_seconds,
        idempotency_key=idempotency_key,
        status=VoiceAnalysisStatus.UPLOADED,
        retention_policy=f"{settings.VOICE_AUDIO_RETENTION_DAYS}_DAYS",
    )
    db.add_all([attachment, command])
    db.flush()
    command.audio_attachment_id = attachment.id
    record_audit(
        db,
        actor_id=current_user.id,
        action="voice_audio_uploaded",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=project_id,
        details={
            "task_id": task_id,
            "mime_type": content_type,
            "size_bytes": file_size,
            "duration_seconds": duration_seconds,
        },
    )
    db.commit()
    await _process_analysis(
        db, command, current_user, filename, content_type, content,
    )
    return db.get(VoiceAnalysis, command.id)


@router.post("/commands/from-transcript", response_model=VoiceCommandOut, status_code=201)
async def create_voice_command_from_transcript(
    payload: VoiceTranscriptCommandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the production interpretation/draft pipeline without pretending audio was recorded."""
    if not settings.VOICE_TRANSCRIPT_SIMULATION_ENABLED:
        raise HTTPException(status_code=404, detail="Transcript simulation is disabled")
    transcript = payload.transcript.strip()
    if len(transcript) < 2:
        raise HTTPException(status_code=422, detail="Transcript must contain meaningful text")
    existing = db.query(VoiceAnalysis).filter(
        VoiceAnalysis.user_id == current_user.id,
        VoiceAnalysis.idempotency_key == payload.idempotency_key,
    ).first()
    if existing:
        return existing
    task = db.get(Task, payload.task_id) if payload.task_id else None
    if not can_create_voice_analysis(db, current_user, payload.project_id, task):
        raise HTTPException(status_code=403, detail="You cannot create a voice command for this project or task")
    command = VoiceAnalysis(
        project_id=payload.project_id,
        user_id=current_user.id,
        task_id=payload.task_id,
        role_at_recording_time=current_user.role.value,
        idempotency_key=payload.idempotency_key,
        raw_transcript=transcript,
        normalized_transcript=transcript,
        status=VoiceAnalysisStatus.TRANSCRIBED,
        retention_policy="NO_AUDIO_JSON_SIMULATION",
        provider_metadata={
            "source": payload.source,
            "clientContextKeys": sorted(payload.client_context)[:20],
        },
    )
    db.add(command)
    db.flush()
    record_audit(
        db,
        actor_id=current_user.id,
        action="voice_json_simulation_submitted",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={"source": payload.source, "idempotencyKey": payload.idempotency_key},
    )
    transition(command, VoiceAnalysisStatus.ANALYZING)
    db.commit()
    started = perf_counter()
    metric = AIProviderCall(
        project_id=command.project_id,
        voice_analysis_id=command.id,
        correlation_id=payload.idempotency_key,
        reason="VOICE_TRANSCRIPT_INTERPRETATION",
        provider="openai",
        model=settings.OPENAI_ANALYSIS_MODEL,
        success="PENDING",
        metadata_json={"source": payload.source},
    )
    db.add(metric)
    db.commit()
    try:
        context = VoiceContextBuilder().build(
            db, user=current_user, project_id=command.project_id,
            task_id=command.task_id,
            pending=find_open_request(
                db, user=current_user, project_id=command.project_id,
                exclude_id=command.id,
            ),
        )
        result = await run_in_threadpool(
            ConstructionVoiceAnalysisService().analyze,
            transcript=transcript,
            user_role=_provider_role(current_user),
            authorized_tasks=context["tasks"],
            application_context=context,
        )
        command = db.get(VoiceAnalysis, command.id)
        metric = db.get(AIProviderCall, metric.id)
        command.structured_result = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        command.provider_metadata = {
            **(command.provider_metadata or {}),
            "analysisProvider": "openai",
            "analysisModel": settings.OPENAI_ANALYSIS_MODEL,
        }
        interpret_command(db, command=command, result=result, user=current_user)
        command.completed_at = datetime.now(timezone.utc)
        metric.success = "SUCCESS"
        metric.latency_ms = int((perf_counter() - started) * 1000)
        record_audit(
            db,
            actor_id=current_user.id,
            action="voice_interpretation_completed",
            entity_type="voice_analysis",
            entity_id=command.id,
            project_id=command.project_id,
            details={"actionCount": len(result.suggested_actions), "source": payload.source},
        )
        db.commit()
        db.refresh(command)
        return command
    except (AIConfigurationError, AIProviderTimeoutError, AIProviderError, ValueError) as exc:
        db.rollback()
        command = db.get(VoiceAnalysis, command.id)
        metric = db.get(AIProviderCall, metric.id)
        command.status = VoiceAnalysisStatus.FAILED
        command.row_version += 1
        command.error_code = "VOICE_TIMEOUT" if isinstance(exc, AIProviderTimeoutError) else "VOICE_PROCESSING_FAILED"
        command.error_detail = (
            "AI analysis timed out. The original transcript was preserved; retry is safe."
            if isinstance(exc, AIProviderTimeoutError)
            else "AI analysis is temporarily unavailable. No project data was changed."
        )
        metric.success = "FAILED"
        metric.error_code = command.error_code
        metric.latency_ms = int((perf_counter() - started) * 1000)
        record_audit(
            db,
            actor_id=current_user.id,
            action="voice_ai_processing_failed",
            entity_type="voice_analysis",
            entity_id=command.id,
            project_id=command.project_id,
            details={"errorCode": command.error_code, "source": payload.source},
        )
        db.commit()
        db.refresh(command)
        return command


@router.get("/task-candidates", response_model=VoiceTaskCandidatesOut)
def voice_task_candidates(
    project_id: UUID,
    q: str | None = Query(default=None, max_length=1000),
    limit: int = Query(default=MAX_CANDIDATES, ge=1, le=MAX_CANDIDATES),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rank the tasks this user may act on against what they said.

    Backs the "choose another task" path, and any client that wants to show
    alternatives before confirming. It ranks *only* what
    `authorized_voice_tasks` already returned, so no query string can widen the
    set beyond this user's role, project, and assignment scope — an empty
    result for an inaccessible project is indistinguishable from an empty one
    for an accessible project with no tasks, which is the intended behaviour.
    """
    tasks = authorized_voice_tasks(db, current_user, project_id)
    outcome = match_task(q, tasks, limit=limit)
    return VoiceTaskCandidatesOut(
        resolved_task_id=outcome.resolved_task_id,
        confidence=outcome.confidence,
        candidates=[
            VoiceTaskCandidateOut(
                task_id=match.task_id,
                task_code=match.task_code,
                name=match.name,
                status=match.status,
                progress_percentage=match.progress_percentage,
                discipline=match.discipline,
                score=round(match.score, 3),
                reasons=match.reasons,
            )
            for match in outcome.candidates
        ],
    )


@router.get("/report-readiness", response_model=VoiceReportReadinessOut)
def voice_report_readiness(
    project_id: UUID,
    report_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The day's confirmed voice updates, shaped for the report agent.

    Only executed actions appear. An unconfirmed draft or a rejected one is not
    project knowledge, and letting either reach a report — or later, a RAG
    index — would make a spoken guess indistinguishable from a verified fact.
    """
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Project access is not available")
    day = report_date or datetime.now(timezone.utc).date()
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    logs = db.query(VoiceExecutionLog).join(
        VoiceAnalysis, VoiceExecutionLog.voice_analysis_id == VoiceAnalysis.id
    ).filter(
        VoiceAnalysis.project_id == project_id,
        VoiceExecutionLog.actor_user_id == current_user.id,
        VoiceExecutionLog.result == "EXECUTED",
        VoiceExecutionLog.created_at >= start,
        VoiceExecutionLog.created_at < start + timedelta(days=1),
    ).order_by(VoiceExecutionLog.created_at).all()

    updates: list[VoiceReportUpdateOut] = []
    disciplines: set[str] = set()
    task_ids: set[UUID] = set()
    for log in logs:
        task = db.get(Task, log.target_id) if log.target_id else None
        if task:
            task_ids.add(task.id)
            if task.discipline:
                disciplines.add(task.discipline)
        command = db.get(VoiceAnalysis, log.voice_analysis_id)
        updates.append(VoiceReportUpdateOut(
            voice_command_id=log.voice_analysis_id,
            action_type=log.action_type,
            task_id=task.id if task else None,
            task_code=task.task_code if task else None,
            task_name=task.name if task else None,
            discipline=task.discipline if task else None,
            before_state=log.before_state,
            after_state=log.after_state,
            summary=(command.structured_result or {}).get("summary") if command else None,
            reported_by_id=log.actor_user_id,
            reported_at=log.created_at,
        ))
    return VoiceReportReadinessOut(
        project_id=project_id,
        report_date=day,
        # Two independent updates is the point at which a day's activity is
        # worth a report rather than a note. The threshold lives here, not in
        # the client, so every surface offers the report at the same moment.
        ready=len(updates) >= 2,
        update_count=len(updates),
        task_count=len(task_ids),
        disciplines=sorted(disciplines),
        updates=updates,
    )


@router.get("/commands/history", response_model=VoiceCommandPage)
def voice_command_history(
    project_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(VoiceAnalysis).filter(VoiceAnalysis.user_id == current_user.id)
    if project_id:
        query = query.filter(VoiceAnalysis.project_id == project_id)
    total = query.count()
    return VoiceCommandPage(
        items=query.order_by(VoiceAnalysis.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all(),
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/commands/{command_id}", response_model=VoiceCommandOut)
def get_voice_command(
    command_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _command(db, command_id, current_user)


@router.put(
    "/commands/{command_id}/draft-actions/{draft_id}",
    response_model=VoiceCommandOut,
)
def edit_voice_draft(
    command_id: UUID,
    draft_id: UUID,
    data: VoiceDraftUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = _command(db, command_id, current_user, owner_only=True)
    draft = db.get(VoiceActionDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft action not found")
    update_draft(
        db, command=command, draft=draft, update=data, user=current_user,
    )
    return db.get(VoiceAnalysis, command.id)


@router.post("/commands/{command_id}/clarifications", response_model=VoiceCommandOut)
async def clarify_voice_command(
    command_id: UUID,
    data: VoiceClarificationAnswer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer one clarification, and always come back with the next state.

    Two kinds of question end up here and they need different work:

      * one attached to a **draft** — "أي مهمة تقصد؟", "لأي تاريخ؟" — where the
        answer is a field, and `answer_clarification` fills it in;
      * one attached to **nothing** — "ما فهمت قصدك، ممكن توضحيلي؟" — where the
        answer is *more speech* and there is no field to put it in.

    The second kind used to be a dead end: the answer was recorded, nothing
    read it, and the response carried a command with no unanswered question, no
    draft and a stale reply — so every client rendered nothing and the
    conversation looked frozen. It is now re-interpreted together with the
    original request, exactly as if the engineer had said both sentences in one
    breath, which is what they meant.
    """
    command = _command(db, command_id, current_user, owner_only=True)
    clarification = db.get(VoiceClarification, data.clarification_id)
    if not clarification:
        raise HTTPException(status_code=404, detail="Clarification not found")
    original = command.raw_transcript or command.normalized_transcript or ""
    needs_interpretation = answer_clarification(
        db,
        command=command,
        clarification=clarification,
        answer=data.answer_text,
        user=current_user,
    )
    if needs_interpretation:
        await _interpret_clarified_request(
            db, command=db.get(VoiceAnalysis, command_id), user=current_user,
            original=original, answer=data.answer_text,
        )
    return db.get(VoiceAnalysis, command_id)


async def _interpret_clarified_request(
    db: Session,
    *,
    command: VoiceAnalysis,
    user: User,
    original: str,
    answer: str,
) -> None:
    """Read the request and its clarification together, as one request.

    Failure here must never be silent either: the engineer answered a question
    and is waiting. A provider outage becomes a sentence saying so, the details
    go to the log, and the command still carries something to render.
    """
    combined = " ".join(part.strip() for part in (original, answer) if part.strip())
    language = str(
        (command.provider_metadata or {}).get("replyLanguage")
        or reply_language(combined, command.detected_language)
    )
    logger.info(
        "re-interpreting voice command %s with its clarification answer", command.id,
    )
    try:
        context = VoiceContextBuilder().build(
            db, user=user, project_id=command.project_id,
            task_id=command.task_id, pending=command,
            # The question this answer answers, so a two-word reply is read as
            # the reply it is.
            pending_open_question=True,
        )
        result = await run_in_threadpool(
            ConstructionVoiceAnalysisService().analyze,
            transcript=combined,
            user_role=_provider_role(user),
            authorized_tasks=context["tasks"],
            application_context=context,
        )
        command = db.get(VoiceAnalysis, command.id)
        command.raw_transcript = combined
        command.structured_result = {
            **result.model_dump(mode="json", by_alias=True, exclude_none=True),
        }
        interpret_command(db, command=command, result=result, user=user)
        db.commit()
    except (AIConfigurationError, AIProviderTimeoutError, AIProviderError, ValueError) as error:
        db.rollback()
        command = db.get(VoiceAnalysis, command.id)
        logger.warning(
            "clarified voice command %s could not be re-interpreted: %s",
            command.id, error,
        )
        arabic = "ما قدرت أكمل الطلب حالياً. جرّب تحكيلي مرة تانية."
        english = "I could not finish that just now. Try telling me again."
        command.structured_result = {
            **(command.structured_result or {}),
            "answer": {
                "topic": "UNRESOLVED",
                "text": arabic if language.startswith("ar") else english,
                "language": language,
                "textAr": arabic,
                "textEn": english,
                "data": {},
                "candidates": [],
            },
        }
        command.row_version += 1
        db.commit()


@router.post("/commands/{command_id}/evidence", status_code=201)
async def upload_voice_evidence(
    command_id: UUID,
    evidence_type: str = Form(default="PHOTO", max_length=40),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = _command(db, command_id, current_user, owner_only=True)
    if command.status not in {
        VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
    }:
        raise HTTPException(status_code=409, detail="Evidence can no longer be added to this action")
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload a supported project photo")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The selected photo is empty")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Each evidence photo must be 10 MB or smaller")
    await file.seek(0)
    storage_key, file_size = await save_private_upload(file, "voice-evidence")
    attachment = Attachment(
        original_filename=file.filename or "evidence.jpg",
        storage_key=storage_key,
        file_url=f"protected://voice-evidence/{command.id}",
        mime_type=content_type,
        file_size_bytes=file_size,
        uploaded_by_id=current_user.id,
        project_id=command.project_id,
        entity_type="VOICE_ANALYSIS_EVIDENCE",
        entity_id=command.id,
    )
    db.add(attachment)
    record_audit(
        db,
        actor_id=current_user.id,
        action="voice_evidence_uploaded",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={"evidence_type": evidence_type.upper(), "mime_type": content_type},
    )
    db.commit()
    return {
        "id": str(attachment.id),
        "type": evidence_type.upper(),
        "filename": attachment.original_filename,
        "sizeBytes": attachment.file_size_bytes,
    }


@router.get("/commands/{command_id}/evidence")
def list_voice_evidence(
    command_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = _command(db, command_id, current_user)
    items = db.query(Attachment).filter(
        Attachment.entity_type == "VOICE_ANALYSIS_EVIDENCE",
        Attachment.entity_id == command.id,
    ).order_by(Attachment.created_at).all()
    return [{
        "id": str(item.id),
        "filename": item.original_filename,
        "mimeType": item.mime_type,
        "sizeBytes": item.file_size_bytes,
    } for item in items]


@router.post("/commands/{command_id}/confirm", response_model=VoiceCommandOut)
def confirm_voice_command(
    command_id: UUID,
    data: VoiceConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = db.query(VoiceAnalysis).filter(
        VoiceAnalysis.id == command_id
    ).with_for_update().first()
    if not command:
        raise HTTPException(status_code=404, detail="Voice command not found")
    assert_command_access(db, command, current_user, owner_only=True)
    assert_version(command, data.row_version)
    if command.status == VoiceAnalysisStatus.CONFIRMED:
        return command
    if command.status != VoiceAnalysisStatus.READY_FOR_CONFIRMATION:
        raise HTTPException(status_code=409, detail="Voice command is not ready for confirmation")
    selected = set(data.selected_draft_ids)
    known = {draft.id for draft in command.action_drafts}
    if not selected.issubset(known):
        raise HTTPException(status_code=422, detail="Unknown draft action selected")
    for draft in command.action_drafts:
        draft.selected_for_execution = draft.id in selected
        if draft.selected_for_execution and draft.missing_fields:
            raise HTTPException(status_code=409, detail="Selected action still requires clarification")
        draft.execution_status = "CONFIRMED" if draft.selected_for_execution else "REMOVED"
    if any(
        draft.selected_for_execution and draft.risk_level == "HIGH"
        for draft in command.action_drafts
    ) and not data.detailed_confirmation:
        raise HTTPException(
            status_code=409,
            detail="Review the full impact and explicitly confirm this high-risk action.",
        )
    for draft in command.action_drafts:
        if (
            draft.selected_for_execution
            and SuggestedActionType(draft.action_type) in DESTRUCTIVE
        ):
            # A deletion carries its acknowledgement in its own payload, so the
            # rules engine can refuse one that never had it — including on a
            # replayed or forged execute call, which never passes through this
            # endpoint's checkbox at all.
            draft.user_edited_payload = {
                **dict(draft.user_edited_payload or draft.extracted_payload or {}),
                "confirmDeletion": True,
            }
    transition(command, VoiceAnalysisStatus.CONFIRMED)
    command.confirmed_by_id = current_user.id
    command.confirmed_at = datetime.now(timezone.utc)
    record_audit(
        db,
        actor_id=current_user.id,
        action="voice_command_confirmed",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={"selected_draft_ids": list(selected)},
    )
    db.commit()
    db.refresh(command)
    return command


@router.post("/commands/{command_id}/execute", response_model=VoiceCommandOut)
def execute_voice_command(
    command_id: UUID,
    data: VoiceExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = db.query(VoiceAnalysis).filter(
        VoiceAnalysis.id == command_id
    ).with_for_update().first()
    if not command:
        raise HTTPException(status_code=404, detail="Voice command not found")
    assert_command_access(db, command, current_user, owner_only=True)
    if command.status == VoiceAnalysisStatus.EXECUTED:
        return command
    assert_version(command, data.row_version)
    VoiceRulesEngine().execute(db, command=command, actor=current_user)
    return db.get(VoiceAnalysis, command.id)


@router.post("/commands/{command_id}/cancel", response_model=VoiceCommandOut)
def cancel_voice_command(
    command_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = _command(db, command_id, current_user, owner_only=True)
    if command.status == VoiceAnalysisStatus.CANCELLED:
        return command
    if command.status in {
        VoiceAnalysisStatus.EXECUTED,
        VoiceAnalysisStatus.PARTIALLY_EXECUTED,
        VoiceAnalysisStatus.EXECUTING,
    }:
        raise HTTPException(status_code=409, detail="An executing or executed command cannot be cancelled")
    transition(command, VoiceAnalysisStatus.CANCELLED)
    record_audit(
        db,
        actor_id=current_user.id,
        action="voice_command_cancelled",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
    )
    db.commit()
    db.refresh(command)
    return command
