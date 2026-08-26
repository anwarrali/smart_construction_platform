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
    """Every operation voice can propose.

    One entry per *user-visible operation*, not per phrasing: "خلّي موعدها
    الأسبوع الجاي", "أجّل المهمة", "خلي التسليم 15 سبتمبر" and "move the
    deadline" are all `UPDATE_TASK_SCHEDULE`. Each one is bound to the same
    backend operation the web UI calls — see `app.services.voice_capabilities`,
    which is the registry that maps them to permissions, required fields and
    the service that performs them.
    """

    CREATE_TASK = "CREATE_TASK"
    START_TASK = "START_TASK"
    UPDATE_TASK_PROGRESS = "UPDATE_TASK_PROGRESS"
    UPDATE_TASK_SCHEDULE = "UPDATE_TASK_SCHEDULE"
    UPDATE_TASK_ASSIGNMENT = "UPDATE_TASK_ASSIGNMENT"
    UPDATE_TASK_PRIORITY = "UPDATE_TASK_PRIORITY"
    UPDATE_TASK_DETAILS = "UPDATE_TASK_DETAILS"
    DELETE_TASK = "DELETE_TASK"
    SUBMIT_TASK_FOR_REVIEW = "SUBMIT_TASK_FOR_REVIEW"
    UPDATE_ISSUE_STATUS = "UPDATE_ISSUE_STATUS"
    ASSIGN_ISSUE = "ASSIGN_ISSUE"
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


class VoiceRequestKind(str, Enum):
    """What the speaker wants to happen — the first decision the pipeline makes.

    The taxonomy in `VoiceIntent` describes *meaning*; this describes *routing*.
    They are separate because a sentence can be about a task without asking for
    the task to change: "شو حالة الحفر؟" and "ابدأ الحفر" share a subject and
    share nothing else.

    `ACTION` is the default on purpose. Anything the model does not positively
    classify keeps the pre-existing mutation behaviour, so an unclassified
    utterance can never silently lose its confirmation step.
    """

    #: Wants project data changed. Goes through drafts → confirm → execute.
    ACTION = "ACTION"
    #: Wants information back. Answered from the database; nothing to confirm.
    QUESTION = "QUESTION"
    #: Wants to say something to a person, not to record it against a task.
    COMMUNICATION = "COMMUNICATION"
    #: Asserts a fact about the world, which may or may not match the record.
    STATEMENT = "STATEMENT"
    #: Wants an explanation rather than a value. "ليش ما بنقدر نبدأ؟" cannot be
    #: answered by reading one column: it needs the dependency graph, the open
    #: issues and the schedule read together. Routed like a question — it
    #: changes nothing — but answered with reasoning and, where useful, a
    #: recommendation.
    REASONING = "REASONING"


class VoiceQueryTopic(str, Enum):
    """The bounded set of questions the backend can answer from project data.

    Deliberately small and about *shape of answer* rather than wording: the
    model maps any Arabic, English, or mixed phrasing onto one of these, and the
    backend supplies the facts. Adding a phrasing never requires a code change;
    adding a genuinely new kind of answer does.
    """

    TASK_STATUS = "TASK_STATUS"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_ASSIGNEE = "TASK_ASSIGNEE"
    TASK_LOCATION = "TASK_LOCATION"
    TASK_BLOCKERS = "TASK_BLOCKERS"
    TASK_NEXT_STEP = "TASK_NEXT_STEP"
    NEXT_TASK = "NEXT_TASK"
    REMAINING_TASKS = "REMAINING_TASKS"
    NOT_STARTED_TASKS = "NOT_STARTED_TASKS"
    IN_PROGRESS_TASKS = "IN_PROGRESS_TASKS"
    COMPLETED_TASKS = "COMPLETED_TASKS"
    BLOCKED_TASKS = "BLOCKED_TASKS"
    PROJECT_PROGRESS = "PROJECT_PROGRESS"
    OPEN_ISSUES = "OPEN_ISSUES"
    REPORT_READINESS = "REPORT_READINESS"
    #: Site reports — the filed record, not a summary of the project. "اعطيني
    #: آخر تقرير موقع" used to have nowhere to go: the nearest topics were
    #: PROJECT_PROGRESS and REPORT_READINESS, so a request for a specific
    #: document came back as a project summary or as "you have enough updates
    #: to write one". Both are answers to a question nobody asked.
    LATEST_SITE_REPORT = "LATEST_SITE_REPORT"
    SITE_REPORTS = "SITE_REPORTS"
    #: Reasoning topics. These need several facts combined and an explanation,
    #: which is why they are answered differently from a status lookup even
    #: though both are read-only.
    WHY_BLOCKED = "WHY_BLOCKED"
    WHY_DELAYED = "WHY_DELAYED"
    PRIORITY_FOCUS = "PRIORITY_FOCUS"
    RECOMMENDED_NEXT_STEP = "RECOMMENDED_NEXT_STEP"
    UNKNOWN = "UNKNOWN"


class DetectedQuery(StrictVoiceModel):
    """A question, reduced to a topic and (optionally) a subject.

    `task_reference` is free spoken text, never an ID: the model has no
    authority to name a task, and the same authorization-scoped matcher that
    resolves action targets resolves this too.
    """

    topic: VoiceQueryTopic = VoiceQueryTopic.UNKNOWN
    task_reference: str | None = Field(default=None, max_length=250)
    confidence: float = Field(default=0, ge=0, le=1)


class DetectedTask(ConfidenceModel):
    task_id: UUID | None = None
    task_title: str | None = Field(default=None, max_length=250)


class DetectedProgress(ConfidenceModel):
    mentioned: bool = False
    percentage: float | None = Field(default=None, ge=0, le=100)
    #: True when the figure was inferred from words rather than spoken as a
    #: number — "خلصنا نص الشغل" is a defensible 50%, "خلص تقريباً كله" is not a
    #: defensible 95%. Approximate figures are proposed but never executed
    #: without the engineer editing or confirming them explicitly.
    approximate: bool = False

    @model_validator(mode="after")
    def consistent(self):
        if not self.mentioned:
            self.percentage = None
            self.approximate = False
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
    #: Schedule fields. Spoken wording, not a date: "الأسبوع الجاي" is what the
    #: model heard, and `app.services.voice_dates` turns it into a day. The
    #: resolved ISO date is written back into `due_date` / `start_date` before
    #: the engineer ever sees the confirmation card, so the card shows a real
    #: date and the model never does arithmetic.
    due_date: str | None = Field(default=None, max_length=60)
    start_date: str | None = Field(default=None, max_length=60)
    priority: str | None = Field(
        default=None, pattern="^(low|medium|high|critical)$"
    )
    #: People, always as identifiers the backend supplied — never names.
    assignee_ids: list[UUID] | None = Field(default=None, max_length=20)
    #: Issue workflow.
    issue_status: str | None = Field(
        default=None, pattern="^(open|in_progress|resolved|closed)$"
    )
    resolution_notes: str | None = Field(default=None, max_length=4000)
    #: Set only by the engineer's explicit confirmation of a destructive
    #: action. The model may never set it, and the rules engine refuses to
    #: delete without it.
    confirm_deletion: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        """The payload as plain JSON-safe values.

        `mode="json"` matters: recipients and assignees are UUIDs, and a raw
        `UUID` survives every in-process hop right up to the moment something
        writes it into a JSONB column — where it fails the insert and takes the
        surrounding request with it. That is what used to make a *sent* message
        look like a failed one: the conversation was created, the audit row that
        followed it could not be serialized, and the engineer saw an error for
        something that had already happened.
        """
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


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
        """Keep the safety invariants; let incompleteness through as a question.

        This validator used to reject any proposal whose payload was missing a
        required field — no task on a progress update, no title on an issue —
        by raising. Raising here does not produce a helpful message: it fails
        the *whole* structured parse, so an engineer who said "بدي أرفع مشكلة"
        without saying what the problem was got "AI analysis is temporarily
        unavailable" instead of "شو المشكلة؟". A field the speaker did not say
        is a conversational gap, and the pipeline now asks for it — see
        `app.services.voice_action_requirements`, which computes exactly the
        same requirements and turns each one into a question, and the rules
        engine, which still refuses to execute a draft that has any outstanding.

        What stays enforced here is the one class of rule that is not about
        completeness: a value the model must never be allowed to assert at all.
        """
        if self.type == SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT:
            # Voice can propose a design change; it can never record one as
            # already approved. Corrected rather than rejected so the proposal
            # still reaches the engineer for review.
            if self.payload.approved is True:
                self.payload.approved = False
                self.warnings = [
                    *self.warnings,
                    "A design change recorded by voice always starts unapproved.",
                ]
        if self.type == SuggestedActionType.PREPARE_CONSULTANT_REVIEW:
            decision = str(self.payload.decision or "").upper()
            if decision and decision not in {"APPROVE", "REJECT", "NOTE"}:
                # An unrecognised decision is treated as unsaid, which makes it
                # a question. Never inferred: nobody's approval is guessed.
                self.payload.decision = None
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
    #: The routing decision. Defaults to ACTION so every previously-working
    #: utterance keeps its existing path through drafts and confirmation.
    request_kind: VoiceRequestKind = VoiceRequestKind.ACTION
    query: DetectedQuery = Field(default_factory=DetectedQuery)
    detected_intents: list[VoiceIntent] = Field(default_factory=list, max_length=10)
    #: The operation this request maps to when the speaker is **not** allowed to
    #: perform it. Set instead of proposing, so the assistant can decline in a
    #: sentence — "ما عندك صلاحية تعدّل مواعيد المهام" — rather than pretending
    #: not to have understood, which is what an unclassifiable-utterance reply
    #: looks like to somebody who spoke perfectly clearly.
    blocked_capability: SuggestedActionType | None = None
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
    """What happened to one confirmed action.

    `message` is the backend's own words and stays in English for logs and
    support. `user_message` is what the engineer hears — their language, no
    field names, no status codes — and `error_code` is the stable classification
    behind it. Clients render `user_message` and never `message`; see
    `app.services.voice_action_errors` for how a raised failure becomes both.
    """

    action_index: int
    type: SuggestedActionType
    success: bool
    status: str
    message: str
    entity_id: UUID | None = None
    error_code: str | None = None
    user_message: str | None = None


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
