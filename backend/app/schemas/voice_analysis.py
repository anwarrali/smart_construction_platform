from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.models.enums import VoiceAnalysisStatus, VoiceConfirmationStatus
from app.schemas.user import CamelModel


class StrictVoiceModel(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class SuggestedActionType(str, Enum):
    CREATE_TASK = "CREATE_TASK"
    START_TASK = "START_TASK"
    UPDATE_TASK_PROGRESS = "UPDATE_TASK_PROGRESS"
    SUBMIT_TASK_FOR_REVIEW = "SUBMIT_TASK_FOR_REVIEW"
    CREATE_ISSUE = "CREATE_ISSUE"
    CREATE_FIELD_SUBMISSION = "CREATE_FIELD_SUBMISSION"
    ADD_TASK_NOTE = "ADD_TASK_NOTE"
    CREATE_SITE_REPORT_DRAFT = "CREATE_SITE_REPORT_DRAFT"
    CREATE_TASK_MESSAGE = "CREATE_TASK_MESSAGE"
    PREPARE_CONSULTANT_REVIEW = "PREPARE_CONSULTANT_REVIEW"
    CREATE_DESIGN_CHANGE_REPORT = "CREATE_DESIGN_CHANGE_REPORT"
    SEND_PROJECT_MESSAGE = "SEND_PROJECT_MESSAGE"
    SEND_OWNER_UPDATE = "SEND_OWNER_UPDATE"


class VoiceIntent(str, Enum):
    """Semantic taxonomy. Only SuggestedActionType values are executable handlers."""

    START_TASK = "START_TASK"
    PAUSE_TASK = "PAUSE_TASK"
    RESUME_TASK = "RESUME_TASK"
    UPDATE_TASK_PROGRESS = "UPDATE_TASK_PROGRESS"
    RECORD_COMPLETED_WORK = "RECORD_COMPLETED_WORK"
    RECORD_COMPLETED_QUANTITY = "RECORD_COMPLETED_QUANTITY"
    COMPLETE_TASK = "COMPLETE_TASK"
    SUBMIT_TASK_FOR_REVIEW = "SUBMIT_TASK_FOR_REVIEW"
    ADD_TASK_NOTE = "ADD_TASK_NOTE"
    REPORT_TASK_DELAY = "REPORT_TASK_DELAY"
    REPORT_TASK_BLOCKER = "REPORT_TASK_BLOCKER"
    REQUEST_TASK_INFORMATION = "REQUEST_TASK_INFORMATION"
    CREATE_WORKER_FIELD_REPORT = "CREATE_WORKER_FIELD_REPORT"
    CREATE_WORKER_COMPLETION_CLAIM = "CREATE_WORKER_COMPLETION_CLAIM"
    CREATE_WORKER_PROGRESS_CLAIM = "CREATE_WORKER_PROGRESS_CLAIM"
    CREATE_WORKER_BLOCKER_REPORT = "CREATE_WORKER_BLOCKER_REPORT"
    CREATE_WORKER_SAFETY_REPORT = "CREATE_WORKER_SAFETY_REPORT"
    CREATE_WORKER_MATERIAL_REPORT = "CREATE_WORKER_MATERIAL_REPORT"
    REQUEST_ENGINEER_REVIEW = "REQUEST_ENGINEER_REVIEW"
    CREATE_ISSUE = "CREATE_ISSUE"
    REPORT_DEFECT = "REPORT_DEFECT"
    REPORT_REWORK = "REPORT_REWORK"
    REPORT_DESIGN_CONFLICT = "REPORT_DESIGN_CONFLICT"
    REPORT_DRAWING_CONFLICT = "REPORT_DRAWING_CONFLICT"
    REPORT_SAFETY_ISSUE = "REPORT_SAFETY_ISSUE"
    REPORT_QUALITY_ISSUE = "REPORT_QUALITY_ISSUE"
    REPORT_MATERIAL_SHORTAGE = "REPORT_MATERIAL_SHORTAGE"
    REPORT_EQUIPMENT_PROBLEM = "REPORT_EQUIPMENT_PROBLEM"
    REPORT_SITE_CONDITION = "REPORT_SITE_CONDITION"
    REPORT_DESIGN_CHANGE = "REPORT_DESIGN_CHANGE"
    REQUEST_DESIGN_CHANGE = "REQUEST_DESIGN_CHANGE"
    REQUEST_CONSULTANT_CLARIFICATION = "REQUEST_CONSULTANT_CLARIFICATION"
    CREATE_RFI = "CREATE_RFI"
    UPDATE_MILESTONE = "UPDATE_MILESTONE"
    REPORT_MILESTONE_PROGRESS = "REPORT_MILESTONE_PROGRESS"
    REPORT_FLOOR_COMPLETION = "REPORT_FLOOR_COMPLETION"
    REPORT_ZONE_COMPLETION = "REPORT_ZONE_COMPLETION"
    SEND_MESSAGE = "SEND_MESSAGE"
    SEND_PROJECT_UPDATE = "SEND_PROJECT_UPDATE"
    SEND_OWNER_UPDATE = "SEND_OWNER_UPDATE"
    SEND_ENGINEER_UPDATE = "SEND_ENGINEER_UPDATE"
    SEND_CONSULTANT_UPDATE = "SEND_CONSULTANT_UPDATE"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    VERIFY_WORKER_REPORT = "VERIFY_WORKER_REPORT"
    PREPARE_CONSULTANT_APPROVAL = "PREPARE_CONSULTANT_APPROVAL"
    PREPARE_CONSULTANT_REJECTION = "PREPARE_CONSULTANT_REJECTION"
    CREATE_SITE_DIARY_ENTRY = "CREATE_SITE_DIARY_ENTRY"
    CREATE_DAILY_REPORT = "CREATE_DAILY_REPORT"
    CREATE_OBSERVATION = "CREATE_OBSERVATION"
    STORE_PRIVATE_NOTE = "STORE_PRIVATE_NOTE"
    STORE_PROJECT_NOTE = "STORE_PROJECT_NOTE"
    STORE_TASK_NOTE = "STORE_TASK_NOTE"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class ActionRiskLevel(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


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


class ConfidenceModel(StrictVoiceModel):
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


class DetectedLocation(StrictVoiceModel):
    text: str | None = Field(default=None, max_length=500)


class DetectedProblem(ConfidenceModel):
    type: ProblemType
    description: str = Field(min_length=2, max_length=2000)
    severity: str | None = Field(default=None, pattern="^(low|medium|high|critical)$")


class DetectedMaterial(StrictVoiceModel):
    name: str = Field(min_length=1, max_length=200)
    status: str | None = Field(default=None, max_length=100)


class SuggestedActionPayload(StrictVoiceModel):
    """Closed schema shared by every supported voice-action proposal."""

    progress_percentage: float | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=2000)
    correction_confirmed: bool | None = None
    completion_note: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    severity: str | None = Field(
        default=None, pattern="^(low|medium|high|critical)$"
    )
    affects_schedule: bool | None = None
    content: str | None = Field(default=None, max_length=4000)
    summary_text: str | None = Field(default=None, max_length=4000)
    work_completed: list[str] | None = Field(default=None, max_length=30)
    delays: list[str] | None = Field(default=None, max_length=30)
    issues: list[str] | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=4000)
    decision: str | None = Field(
        default=None, pattern="^(APPROVE|REJECT|NOTE)$"
    )
    comments: str | None = Field(default=None, max_length=4000)
    rejection_reason: str | None = Field(default=None, max_length=4000)
    required_corrections: str | None = Field(default=None, max_length=4000)
    recipient_ids: list[UUID] | None = Field(default=None, max_length=20)
    recipient_roles: list[str] | None = Field(default=None, max_length=20)
    subject: str | None = Field(default=None, max_length=300)
    approved: bool | None = None
    source_discipline: str | None = Field(default=None, max_length=80)
    affected_disciplines: list[str] | None = Field(default=None, max_length=20)
    related_drawings: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=500)
    crew: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, ge=0)
    quantity_unit: str | None = Field(default=None, max_length=40)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class SuggestedAction(ConfidenceModel):
    client_action_id: str | None = Field(default=None, max_length=80)
    type: SuggestedActionType
    reason: str = Field(min_length=2, max_length=1000)
    target_id: UUID | None = None
    payload: SuggestedActionPayload = Field(default_factory=SuggestedActionPayload)
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    evidence_phrases: list[str] = Field(default_factory=list, max_length=20)
    risk_level: ActionRiskLevel = ActionRiskLevel.LOW
    required_evidence: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_payload(self):
        payload = self.payload.as_dict()
        if self.type in {
            SuggestedActionType.START_TASK,
            SuggestedActionType.SUBMIT_TASK_FOR_REVIEW,
            SuggestedActionType.PREPARE_CONSULTANT_REVIEW,
        }:
            if self.target_id is None:
                raise ValueError(f"{self.type.value} requires targetId")
            if self.type == SuggestedActionType.PREPARE_CONSULTANT_REVIEW:
                decision = str(payload.get("decision") or "").upper()
                if decision not in {"APPROVE", "REJECT", "NOTE"}:
                    raise ValueError("Consultant review decision must be APPROVE, REJECT, or NOTE")
                if not str(payload.get("comments") or "").strip():
                    raise ValueError("Consultant review requires comments")
        elif self.type == SuggestedActionType.UPDATE_TASK_PROGRESS:
            if self.target_id is None:
                raise ValueError("UPDATE_TASK_PROGRESS requires targetId")
            value = payload.get("progressPercentage")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
                raise ValueError("progressPercentage must be between 0 and 100")
        elif self.type == SuggestedActionType.CREATE_ISSUE:
            if not str(payload.get("title", "")).strip() or not str(payload.get("description", "")).strip():
                raise ValueError("CREATE_ISSUE requires title and description")
        elif self.type == SuggestedActionType.CREATE_TASK:
            if not str(payload.get("title", "")).strip():
                raise ValueError("CREATE_TASK requires title")
        elif self.type == SuggestedActionType.CREATE_FIELD_SUBMISSION:
            if self.target_id is None or not str(payload.get("description", "")).strip():
                raise ValueError("CREATE_FIELD_SUBMISSION requires a task and description")
        elif self.type in {SuggestedActionType.ADD_TASK_NOTE, SuggestedActionType.CREATE_TASK_MESSAGE}:
            if self.target_id is None or not str(payload.get("content", "")).strip():
                raise ValueError(f"{self.type.value} requires a task and content")
        elif self.type == SuggestedActionType.CREATE_SITE_REPORT_DRAFT:
            if not str(payload.get("summaryText", "")).strip():
                raise ValueError("CREATE_SITE_REPORT_DRAFT requires summaryText")
        elif self.type == SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT:
            if not str(payload.get("title", "")).strip() or not str(payload.get("description", "")).strip():
                raise ValueError("CREATE_DESIGN_CHANGE_REPORT requires title and description")
            if payload.get("approved") is True:
                raise ValueError("Voice cannot record a design change as approved")
        elif self.type in {
            SuggestedActionType.SEND_PROJECT_MESSAGE,
            SuggestedActionType.SEND_OWNER_UPDATE,
        }:
            if not str(payload.get("content", "")).strip():
                raise ValueError(f"{self.type.value} requires message content")
            if not payload.get("recipientIds"):
                raise ValueError(f"{self.type.value} requires selected recipients")
        return self

    def payload_dict(self) -> dict[str, Any]:
        return self.payload.as_dict()


class ConstructionVoiceResult(StrictVoiceModel):
    schema_version: str = Field(default="2.0", pattern=r"^2\.0$")
    prompt_version: str = Field(default="construction_voice_assistant_v2", max_length=80)
    original_transcript: str | None = Field(default=None, max_length=10000)
    detected_language: str | None = Field(default=None, max_length=30)
    normalized_transcript: str | None = Field(default=None, max_length=10000)
    overall_confidence: float = Field(default=0, ge=0, le=1)
    requires_clarification: bool = False
    human_summary_ar: str | None = Field(default=None, max_length=3000)
    human_summary_en: str | None = Field(default=None, max_length=3000)
    summary: str = Field(min_length=1, max_length=3000)
    detected_intents: list[VoiceIntent] = Field(default_factory=list, max_length=10)
    clarification_questions: list[str] = Field(default_factory=list, max_length=10)
    detected_task: DetectedTask
    progress: DetectedProgress
    discipline: DetectedDiscipline
    location: DetectedLocation
    work_completed: list[str] = Field(default_factory=list, max_length=30)
    problems: list[DetectedProblem] = Field(default_factory=list, max_length=20)
    materials: list[DetectedMaterial] = Field(default_factory=list, max_length=30)
    suggested_actions: list[SuggestedAction] = Field(default_factory=list, max_length=10)


class ConfirmedAction(StrictVoiceModel):
    action_index: int = Field(ge=0)
    target_id: UUID | None = None
    payload: dict[str, Any] | None = None


class ConfirmVoiceActionsRequest(StrictVoiceModel):
    actions: list[ConfirmedAction] = Field(min_length=1, max_length=10)


class ActionExecutionResult(StrictVoiceModel):
    action_index: int
    type: SuggestedActionType
    success: bool
    status: str
    message: str
    entity_id: UUID | None = None


class VoiceAnalysisOut(StrictVoiceModel):
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


class VoiceAnalysisPage(StrictVoiceModel):
    items: list[VoiceAnalysisOut]
    total: int
