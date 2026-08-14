from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field
from app.schemas.user import CamelModel


class AIInsightReview(CamelModel):
    status: str
    note: str | None = Field(default=None, max_length=4000)


class AIInsightCreateTask(CamelModel):
    title: str | None = Field(default=None, max_length=250)
    description: str | None = Field(default=None, max_length=4000)
    discipline: str | None = Field(default=None, max_length=50)


class AIInsightOut(CamelModel):
    id: UUID; project_id: UUID; model_revision_id: UUID | None = None
    insight_type: str; category: str; severity: str; confidence: float
    title: str; description: str; reason: str; recommended_action: str
    potential_impact: str | None = None; evidence_json: dict[str, Any]; affected_json: dict[str, Any]
    message_key: str | None = None
    #: Facts for the localized rendering; empty for rows written before this.
    message_params_json: dict[str, Any] = Field(default_factory=dict)
    related_task_ids_json: list; related_issue_ids_json: list; related_evidence_ids_json: list
    source_engine: str; status: str; review_note: str | None = None
    reviewed_by_id: UUID | None = None; reviewed_at: datetime | None = None; resolved_at: datetime | None = None
    applied_entity_type: str | None = None; applied_entity_id: UUID | None = None
    created_at: datetime; updated_at: datetime
