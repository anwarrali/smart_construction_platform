from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.models.enums import VoiceAnalysisStatus, VoiceConfirmationStatus
from app.schemas.user import CamelModel


class SuggestedActionType(str, Enum):
    UPDATE_TASK_PROGRESS = "UPDATE_TASK_PROGRESS"
    CREATE_ISSUE = "CREATE_ISSUE"
    CREATE_FIELD_SUBMISSION = "CREATE_FIELD_SUBMISSION"
    ADD_TASK_NOTE = "ADD_TASK_NOTE"
    CREATE_SITE_REPORT_DRAFT = "CREATE_SITE_REPORT_DRAFT"
    CREATE_TASK_MESSAGE = "CREATE_TASK_MESSAGE"


class ProblemType(str, Enum):
    DELAY = "DELAY"
    MATERIAL_DELAY = "MATERIAL_DELAY"
    DEFECT = "DEFECT"
    SAFETY = "SAFETY"
    DESIGN_CONFLICT = "DESIGN_CONFLICT"
    BLOCKED_WORK = "BLOCKED_WORK"
    EQUIPMENT = "EQUIPMENT"
    ACCESS = "ACCESS"
    DEPENDENCY = "DEPENDENCY"
    OTHER = "OTHER"


class ConfidenceModel(CamelModel):
    confidence: float = Field(ge=0, le=1)


class DetectedTask(ConfidenceModel):
    task_id: UUID | None = None
    task_title: str | None = Field(default=None, max_length=250)


class DetectedProgress(ConfidenceModel):
    mentioned: bool = False
    percentage: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def consistent(self):
        if not self.mentioned:
            self.percentage = None
        return self


class DetectedDiscipline(ConfidenceModel):
    value: str | None = Field(default=None, max_length=50)


class DetectedLocation(CamelModel):
    text: str | None = Field(default=None, max_length=500)


class DetectedProblem(ConfidenceModel):
    type: ProblemType
    description: str = Field(min_length=2, max_length=2000)
    severity: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")


class DetectedMaterial(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    status: str | None = Field(default=None, max_length=100)


class SuggestedAction(ConfidenceModel):
    type: SuggestedActionType
    reason: str = Field(min_length=2, max_length=1000)
    target_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        payload = self.payload
        if self.type == SuggestedActionType.UPDATE_TASK_PROGRESS:
            if self.target_id is None:
                raise ValueError("UPDATE_TASK_PROGRESS requires targetId")
            value = payload.get("progressPercentage")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
                raise ValueError("progressPercentage must be between 0 and 100")
        elif self.type == SuggestedActionType.CREATE_ISSUE:
            if not str(payload.get("title", "")).strip() or not str(payload.get("description", "")).strip():
                raise ValueError("CREATE_ISSUE requires title and description")
        elif self.type == SuggestedActionType.CREATE_FIELD_SUBMISSION:
            if self.target_id is None or not str(payload.get("description", "")).strip():
                raise ValueError("CREATE_FIELD_SUBMISSION requires a task and description")
        elif self.type in {SuggestedActionType.ADD_TASK_NOTE, SuggestedActionType.CREATE_TASK_MESSAGE}:
            if self.target_id is None or not str(payload.get("content", "")).strip():
                raise ValueError(f"{self.type.value} requires a task and content")
        elif self.type == SuggestedActionType.CREATE_SITE_REPORT_DRAFT:
            if not str(payload.get("summaryText", "")).strip():
                raise ValueError("CREATE_SITE_REPORT_DRAFT requires summaryText")
        return self


class ConstructionVoiceResult(CamelModel):
    summary: str = Field(min_length=1, max_length=3000)
    detected_task: DetectedTask
    progress: DetectedProgress
    discipline: DetectedDiscipline
    location: DetectedLocation
    work_completed: list[str] = Field(default_factory=list, max_length=30)
    problems: list[DetectedProblem] = Field(default_factory=list, max_length=20)
    materials: list[DetectedMaterial] = Field(default_factory=list, max_length=30)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list, max_length=10)


class ConfirmedAction(CamelModel):
    action_index: int = Field(ge=0)
    target_id: UUID | None = None
    payload: dict[str, Any] | None = None


class ConfirmVoiceActionsRequest(CamelModel):
    actions: list[ConfirmedAction] = Field(min_length=1, max_length=10)


class ActionExecutionResult(CamelModel):
    action_index: int
    type: SuggestedActionType
    success: bool
    status: str
    message: str
    entity_id: UUID | None = None


class VoiceAnalysisOut(CamelModel):
    id: UUID
    project_id: UUID
    user_id: UUID
    task_id: UUID | None = None
    field_submission_id: UUID | None = None
    audio_attachment_id: UUID | None = None
    duration_seconds: int | None = None
    raw_transcript: str | None = None
    detected_language: str | None = None
    status: VoiceAnalysisStatus
    structured_result: ConstructionVoiceResult | None = None
    provider_metadata: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: str | None = None
    retry_count: int
    completed_at: datetime | None = None
    confirmation_status: VoiceConfirmationStatus
    confirmed_at: datetime | None = None
    confirmed_by_id: UUID | None = None
    action_results: list[ActionExecutionResult] | None = None
    retention_policy: str
    created_at: datetime
    updated_at: datetime


class VoiceAnalysisPage(CamelModel):
    items: list[VoiceAnalysisOut]
    total: int
