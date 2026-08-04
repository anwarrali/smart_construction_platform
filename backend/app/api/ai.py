from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.action_analyzer import ActionAnalyzer
from app.ai.construction_analysis_service import ConstructionVoiceAnalysisService
from app.ai.action_rules import validate_proposed_action
from app.ai.action_schemas import (
    AnalyzeCommandRequest,
    AnalyzeCommandResponse,
    TranscriptionResponse,
)
from app.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIProviderTimeoutError,
    InvalidAudioError,
)
from app.ai.transcription_service import MAX_AUDIO_BYTES, TranscriptionService, validate_audio
from app.core.config import settings
from app.core.deps import get_current_user, is_worker, user_has_project_access
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.enums import VoiceAnalysisStatus
from app.models.task import Task
from app.models.user import User
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import (
    ActionExecutionResult,
    ConfirmVoiceActionsRequest,
    VoiceAnalysisOut,
    VoiceAnalysisPage,
)
from app.services.audit_service import record_audit
from app.services.file_storage import (
    resolve_private_storage_key,
    save_private_upload,
)
from app.services.voice_action_service import execute_confirmed_actions
from app.services.voice_analysis_authorization import (
    authorized_voice_tasks,
    can_create_voice_analysis,
    can_view_voice_analysis,
)
from app.services.voice_command_service import build_action_drafts, transition
from app.services.voice_context_builder import VoiceContextBuilder
from app.services.voice_action_policy import user_facing_error

router = APIRouter(prefix="/ai", tags=["AI Voice Foundation"])


@router.post("/voice-analyses", response_model=VoiceAnalysisOut, status_code=201)
async def create_voice_analysis(
    project_id: UUID = Form(...),
    task_id: UUID | None = Form(default=None),
    field_submission_id: UUID | None = Form(default=None),
    duration_seconds: int | None = Form(default=None, ge=0, le=7200),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id) if task_id else None
    if not can_create_voice_analysis(db, current_user, project_id, task):
        raise HTTPException(
            status_code=403,
            detail="Only an assigned Worker or Contractor Engineer can analyze this field update",
        )
    if field_submission_id is not None:
        from app.models.field_submission import FieldSubmission
        submission = db.get(FieldSubmission, field_submission_id)
        if (
            not submission or submission.project_id != project_id
            or submission.worker_id != current_user.id
        ):
            raise HTTPException(status_code=403, detail="Field submission context is not accessible")

    content = await _read_limited_audio(audio)
    filename = audio.filename or "recording.m4a"
    content_type = audio.content_type or "application/octet-stream"
    try:
        validate_audio(filename, content_type, content)
    except InvalidAudioError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    await audio.seek(0)
    analysis_id = uuid4()
    storage_key, file_size = await save_private_upload(audio, "audio")
    attachment = Attachment(
        original_filename=filename,
        storage_key=storage_key,
        file_url=f"protected://voice-analysis/{analysis_id}",
        mime_type=content_type,
        file_size_bytes=file_size,
        uploaded_by_id=current_user.id,
        project_id=project_id,
        entity_type="VOICE_ANALYSIS",
        entity_id=analysis_id,
    )
    analysis = VoiceAnalysis(
        id=analysis_id, project_id=project_id, user_id=current_user.id,
        task_id=task.id if task else None, field_submission_id=field_submission_id,
        duration_seconds=duration_seconds, status=VoiceAnalysisStatus.UPLOADED,
        role_at_recording_time=current_user.role.value,
        retention_policy=f"{settings.VOICE_AUDIO_RETENTION_DAYS}_DAYS",
    )
    db.add_all([attachment, analysis])
    db.flush()
    analysis.audio_attachment_id = attachment.id
    record_audit(
        db, actor_id=current_user.id, action="ai_voice_analysis_created",
        entity_type="voice_analysis", entity_id=analysis.id, project_id=project_id,
        details={"task_id": task_id, "field_submission_id": field_submission_id},
    )
    db.commit()
    await _process_analysis(db, analysis, current_user, filename, content_type, content)
    return db.get(VoiceAnalysis, analysis.id)


@router.get("/voice-analyses", response_model=VoiceAnalysisPage)
def list_voice_analyses(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(VoiceAnalysis).filter(
        VoiceAnalysis.project_id == project_id,
        VoiceAnalysis.user_id == current_user.id,
    )
    return VoiceAnalysisPage(
        items=query.order_by(VoiceAnalysis.created_at.desc()).limit(100).all(),
        total=query.count(),
    )


@router.get("/voice-analyses/{analysis_id}", response_model=VoiceAnalysisOut)
def get_voice_analysis(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _analysis_or_404(db, current_user, analysis_id)


@router.get("/voice-analyses/{analysis_id}/audio")
def get_voice_analysis_audio(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = _analysis_or_404(db, current_user, analysis_id)
    attachment = db.get(Attachment, analysis.audio_attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Audio is no longer available")
    path = resolve_private_storage_key(attachment.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio is no longer available")
    return FileResponse(
        path, media_type=attachment.mime_type, filename=attachment.original_filename,
    )


@router.post("/voice-analyses/{analysis_id}/retry", response_model=VoiceAnalysisOut)
async def retry_voice_analysis(
    analysis_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = _analysis_or_404(db, current_user, analysis_id)
    if analysis.status != VoiceAnalysisStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed analyses can be retried")
    attachment = db.get(Attachment, analysis.audio_attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Retained audio is unavailable")
    path = resolve_private_storage_key(attachment.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Retained audio is unavailable")
    analysis.retry_count += 1
    analysis.error_code = None
    analysis.error_detail = None
    analysis.status = VoiceAnalysisStatus.UPLOADED
    db.commit()
    await _process_analysis(
        db, analysis, current_user, attachment.original_filename,
        attachment.mime_type, path.read_bytes(),
    )
    return db.get(VoiceAnalysis, analysis.id)


@router.post(
    "/voice-analyses/{analysis_id}/confirm",
    response_model=list[ActionExecutionResult],
)
def confirm_voice_analysis(
    analysis_id: UUID,
    request: ConfirmVoiceActionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = _analysis_or_404(db, current_user, analysis_id)
    if analysis.status not in {
        VoiceAnalysisStatus.COMPLETED,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
    }:
        raise HTTPException(status_code=409, detail="Analysis is not ready for confirmation")
    return execute_confirmed_actions(
        db, analysis=analysis, current_user=current_user, requested=request.actions,
    )


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    project_id: UUID | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    content = await _read_limited_audio(audio)
    try:
        return await run_in_threadpool(
            TranscriptionService().transcribe,
            filename=audio.filename or "recording.m4a",
            content_type=audio.content_type or "application/octet-stream",
            content=content,
        )
    except InvalidAudioError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/analyze-command", response_model=AnalyzeCommandResponse)
async def analyze_command(
    request: AnalyzeCommandRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, request.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    try:
        proposed = await run_in_threadpool(ActionAnalyzer().analyze, request.transcript)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    proposed, validation = validate_proposed_action(
        proposed,
        selected_project_id=request.project_id,
        user_role=current_user.role.value,
    )
    return AnalyzeCommandResponse(
        transcript=request.transcript,
        proposed_action=proposed,
        validation=validation,
        can_execute=False,
        requires_confirmation=proposed.requires_confirmation,
    )


async def _read_limited_audio(audio: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await audio.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Audio file exceeds the 25 MB limit.",
            )
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")
    return b"".join(chunks)


async def _process_analysis(
    db: Session,
    analysis: VoiceAnalysis,
    current_user: User,
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    try:
        transition(analysis, VoiceAnalysisStatus.TRANSCRIBING)
        db.commit()
        transcription = await run_in_threadpool(
            TranscriptionService().transcribe,
            filename=filename, content_type=content_type, content=content,
        )
        analysis = db.get(VoiceAnalysis, analysis.id)
        analysis.raw_transcript = transcription.transcript
        analysis.detected_language = transcription.language
        transition(analysis, VoiceAnalysisStatus.TRANSCRIBED)
        record_audit(
            db, actor_id=current_user.id, action="voice_transcription_completed",
            entity_type="voice_analysis", entity_id=analysis.id,
            project_id=analysis.project_id,
            details={"model": transcription.model, "language": transcription.language},
        )
        transition(analysis, VoiceAnalysisStatus.ANALYZING)
        db.commit()
        context = VoiceContextBuilder().build(
            db, user=current_user, project_id=analysis.project_id,
            task_id=analysis.task_id,
        )
        task_context = context["tasks"]
        result = await run_in_threadpool(
            ConstructionVoiceAnalysisService().analyze,
            transcript=transcription.transcript,
            user_role=(
                "worker"
                if is_worker(current_user)
                else "external_consultant"
                if getattr(current_user, "engineer_affiliation", None) == "external_consultant"
                else "contractor_engineer"
                if current_user.role.value == "engineer"
                else current_user.role.value
            ),
            authorized_tasks=task_context,
            application_context=context,
        )
        analysis = db.get(VoiceAnalysis, analysis.id)
        analysis.structured_result = result.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
        analysis.provider_metadata = {
            "transcriptionProvider": "openai",
            "transcriptionModel": transcription.model,
            "analysisProvider": "openai",
            "analysisModel": settings.OPENAI_ANALYSIS_MODEL,
        }
        build_action_drafts(
            db, command=analysis, result=result, user=current_user,
        )
        analysis.completed_at = datetime.now(timezone.utc)
        record_audit(
            db, actor_id=current_user.id, action="voice_interpretation_completed",
            entity_type="voice_analysis", entity_id=analysis.id,
            project_id=analysis.project_id,
            details={
                "analysis_model": settings.OPENAI_ANALYSIS_MODEL,
                "action_count": len(result.suggested_actions),
            },
        )
        db.commit()
    except (AIConfigurationError, AIProviderTimeoutError, AIProviderError, ValueError) as exc:
        db.rollback()
        analysis = db.get(VoiceAnalysis, analysis.id)
        if analysis.status != VoiceAnalysisStatus.FAILED:
            try:
                transition(analysis, VoiceAnalysisStatus.FAILED)
            except HTTPException:
                analysis.status = VoiceAnalysisStatus.FAILED
        support_log_id = uuid4().hex
        if isinstance(exc, AIProviderTimeoutError):
            analysis.error_code = "VOICE_TIMEOUT"
        else:
            analysis.error_code = "VOICE_PROCESSING_FAILED"
        friendly = user_facing_error(analysis.error_code)
        analysis.error_detail = friendly["description"]
        analysis.provider_metadata = {
            **(analysis.provider_metadata or {}),
            "supportLogId": support_log_id,
            "retryable": friendly["retryable"],
            "suggestedAction": friendly["suggestedAction"],
        }
        record_audit(
            db, actor_id=current_user.id, action="voice_ai_processing_failed",
            entity_type="voice_analysis", entity_id=analysis.id,
            project_id=analysis.project_id,
            details={
                "error_code": analysis.error_code,
                "support_log_id": support_log_id,
                "exception_type": type(exc).__name__,
            },
        )
        db.commit()


def _analysis_or_404(db: Session, user: User, analysis_id: UUID) -> VoiceAnalysis:
    analysis = db.get(VoiceAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Voice analysis not found")
    if not can_view_voice_analysis(db, user, analysis):
        raise HTTPException(status_code=403, detail="You cannot access this voice analysis")
    return analysis
