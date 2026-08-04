from datetime import datetime, timedelta, timezone
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
from app.core.deps import get_current_user, is_worker
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.enums import VoiceAnalysisStatus
from app.models.task import Task
from app.models.user import User
from app.models.voice_action import VoiceActionDraft, VoiceClarification
from app.models.voice_analysis import VoiceAnalysis
from app.models.ai_governance import AIProviderCall
from app.schemas.voice_command import (
    VoiceClarificationAnswer,
    VoiceCommandOut,
    VoiceCommandPage,
    VoiceConfirmRequest,
    VoiceDraftUpdate,
    VoiceExecuteRequest,
    VoiceTranscriptCommandCreate,
)
from app.services.audit_service import record_audit
from app.services.file_storage import save_private_upload
from app.services.voice_analysis_authorization import can_create_voice_analysis
from app.services.voice_command_service import (
    answer_clarification,
    assert_command_access,
    assert_version,
    transition,
    update_draft,
    build_action_drafts,
)
from app.services.voice_rules_engine import VoiceRulesEngine
from app.services.voice_context_builder import VoiceContextBuilder


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
    if recent_count >= 20:
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
            db, user=current_user, project_id=command.project_id, task_id=command.task_id
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
        build_action_drafts(db, command=command, result=result, user=current_user)
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
def clarify_voice_command(
    command_id: UUID,
    data: VoiceClarificationAnswer,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    command = _command(db, command_id, current_user, owner_only=True)
    clarification = db.get(VoiceClarification, data.clarification_id)
    if not clarification:
        raise HTTPException(status_code=404, detail="Clarification not found")
    answer_clarification(
        db,
        command=command,
        clarification=clarification,
        answer=data.answer_text,
        user=current_user,
    )
    return db.get(VoiceAnalysis, command.id)


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
