from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.enums import VoiceAnalysisStatus
from app.schemas.voice_analysis import StrictVoiceModel, SuggestedActionType


class VoiceDraftUpdate(StrictVoiceModel):
    target_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    selected_for_execution: bool = True
    row_version: int = Field(ge=1)


class VoiceDraftOut(StrictVoiceModel):
    id: UUID
    client_action_id: str
    #: Position in the analysis's `suggestedActions`. Clients must bind a
    #: reviewed action to its draft by this (or by `id`), never by the
    #: draft's position in the serialized list.
    sequence: int
    action_type: SuggestedActionType
    target_entity_type: str | None = None
    target_entity_id: UUID | None = None
    extracted_payload: dict[str, Any]
    user_edited_payload: dict[str, Any] | None = None
    target_snapshot: dict[str, Any] | None = None
    confidence: float
    missing_fields: list[str]
    warnings: list[str]
    risk_level: str
    required_evidence: list[str]
    selected_for_execution: bool
    execution_status: str
    execution_error: str | None = None
    created_at: datetime
    updated_at: datetime


class VoiceClarificationAnswer(StrictVoiceModel):
    clarification_id: UUID
    answer_text: str = Field(min_length=1, max_length=2000)


class VoiceClarificationOut(StrictVoiceModel):
    id: UUID
    voice_action_draft_id: UUID | None = None
    sequence: int
    field_path: str
    question_ar: str
    question_en: str
    expected_answer_type: str
    options: list[dict[str, Any]]
    answer_text: str | None = None
    answer_source: str | None = None
    answered_at: datetime | None = None


class VoiceConfirmRequest(StrictVoiceModel):
    selected_draft_ids: list[UUID] = Field(min_length=1, max_length=10)
    row_version: int = Field(ge=1)
    detailed_confirmation: bool = False


class VoiceExecuteRequest(StrictVoiceModel):
    row_version: int = Field(ge=1)


class VoiceTranscriptCommandCreate(StrictVoiceModel):
    """Authenticated test/development input; identity and permissions stay server-derived."""

    transcript: str = Field(min_length=2, max_length=8000)
    project_id: UUID
    task_id: UUID | None = None
    source: Literal["mobile_voice_simulation", "api_json_test"] = "mobile_voice_simulation"
    idempotency_key: str = Field(min_length=8, max_length=100)
    client_context: dict[str, Any] = Field(default_factory=dict)


class VoiceCommandOut(StrictVoiceModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    task_id: UUID | None = None
    field_submission_id: UUID | None = None
    audio_attachment_id: UUID | None = None
    role_at_recording_time: str | None = None
    duration_seconds: int | None = None
    raw_transcript: str | None = None
    normalized_transcript: str | None = None
    detected_language: str | None = None
    status: VoiceAnalysisStatus
    structured_result: dict[str, Any] | None = None
    provider_metadata: dict[str, Any] | None = None
    overall_confidence: float | None = None
    error_code: str | None = None
    error_detail: str | None = None
    row_version: int
    action_drafts: list[VoiceDraftOut] = Field(default_factory=list)
    clarifications: list[VoiceClarificationOut] = Field(default_factory=list)
    action_results: list[dict[str, Any]] | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def derive_confidence(self):
        if self.overall_confidence is None and self.action_drafts:
            self.overall_confidence = min(item.confidence for item in self.action_drafts)
        return self


class VoiceCommandPage(StrictVoiceModel):
    items: list[VoiceCommandOut]
    page: int
    page_size: int
    total: int
