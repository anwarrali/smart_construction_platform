from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class VoiceActionType(str, Enum):
    UPDATE_TASK_PROGRESS = "update_task_progress"
    UPDATE_TASK_STATUS = "update_task_status"
    CREATE_ISSUE = "create_issue"
    CREATE_SITE_REPORT = "create_site_report"
    ADD_TASK_COMMENT = "add_task_comment"
    SUBMIT_TASK_FOR_REVIEW = "submit_task_for_review"
    UNKNOWN = "unknown"


class VoiceAction(CamelModel):
    action_type: VoiceActionType = VoiceActionType.UNKNOWN
    project_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    task_reference: Optional[str] = Field(default=None, max_length=300)
    progress_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[str] = Field(default=None, max_length=50)
    issue_title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=4000)
    confidence: float = Field(default=0, ge=0, le=1)
    requires_confirmation: bool = True
    requires_clarification: bool = False


class TaskCandidate(CamelModel):
    id: UUID
    task_code: str
    name: str
    status: str
    progress_percentage: float
    discipline: Optional[str] = None


class AnalyzeCommandRequest(CamelModel):
    transcript: str = Field(min_length=1, max_length=8000)
    project_id: UUID


class ActionRuleResult(CamelModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_clarification: bool = False


class AnalyzeCommandResponse(CamelModel):
    transcript: str
    proposed_action: VoiceAction
    validation: ActionRuleResult
    can_execute: bool = False
    requires_confirmation: bool = True
    requires_clarification: bool = False
    task_candidates: list[TaskCandidate] = Field(default_factory=list)
    selected_task: Optional[TaskCandidate] = None
    confirmation_token: Optional[str] = None


class ConfirmActionRequest(CamelModel):
    confirmation_token: str = Field(min_length=20)


class ConfirmActionResponse(CamelModel):
    success: bool = True
    message: str
    task: TaskCandidate


class TranscriptionResponse(CamelModel):
    transcript: str
    language: str
    success: bool = True
    model: str
