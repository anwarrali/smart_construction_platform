from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import Field

from app.schemas.user import CamelModel

ActionType = Literal["ISSUE", "DESIGN_CHANGE", "SITE_REPORT", "PROJECT_STATUS_QUESTION", "GENERAL_PROJECT_NOTE"]


class ActionProposal(CamelModel):
    project_id: UUID
    action_type: ActionType
    title: Optional[str] = None
    summary: str = Field(min_length=1, max_length=4000)
    discipline: Optional[str] = None
    related_disciplines: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    proposed_fields: dict[str, Any] = Field(default_factory=dict)


class ActionProposalValidationOut(CamelModel):
    proposal_id: UUID
    status: Literal["needs_confirmation", "ready_for_submission"]
    proposal: ActionProposal
    allowed_submission_endpoint: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
