from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.voice_analysis import StrictVoiceModel


class AIActionOut(StrictVoiceModel):
    id: UUID
    project_id: UUID
    actor_user_id: UUID
    voice_analysis_id: UUID | None = None
    parent_action_id: UUID | None = None
    reverted_action_id: UUID | None = None
    source: str
    intent: str
    original_input: str | None = None
    ai_interpretation: dict[str, Any]
    final_command: dict[str, Any]
    entity_type: str
    entity_id: UUID
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    approval_info: dict[str, Any]
    result: str
    error: str | None = None
    request_id: str
    correlation_id: str
    undo_policy: str
    metadata_json: dict[str, Any]
    undo_available: bool = False
    undo_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class AIActionPage(StrictVoiceModel):
    items: list[AIActionOut]
    page: int
    page_size: int
    total: int


class AIActionRevertRequest(StrictVoiceModel):
    request_id: str = Field(min_length=8, max_length=160)
    reason: str = Field(min_length=3, max_length=1000)


class AIActionRevertResult(StrictVoiceModel):
    action: AIActionOut
    message: str
