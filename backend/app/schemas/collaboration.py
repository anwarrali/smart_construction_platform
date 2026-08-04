from datetime import datetime, time
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.user import CamelModel


class OwnerRequestCreate(CamelModel):
    project_id: UUID
    title: str = Field(min_length=2, max_length=250)
    description: str = Field(min_length=2, max_length=10000)
    category: str = Field(max_length=50)
    discipline: str | None = Field(default=None, max_length=50)
    floor: str | None = Field(default=None, max_length=120)
    room: str | None = Field(default=None, max_length=120)
    related_document_id: UUID | None = None
    priority: str = Field(default="NORMAL", max_length=20)
    due_at: datetime | None = None


class OwnerRequestAction(CamelModel):
    status: str | None = Field(default=None, max_length=40)
    response_text: str | None = Field(default=None, max_length=10000)
    clarification_text: str | None = Field(default=None, max_length=10000)
    assigned_to_id: UUID | None = None


class OwnerRequestOut(CamelModel):
    id: UUID; project_id: UUID; created_by_id: UUID; assigned_to_id: UUID | None = None
    title: str; description: str; category: str; discipline: str | None = None
    floor: str | None = None; room: str | None = None; related_document_id: UUID | None = None
    priority: str; status: str; response_text: str | None = None; clarification_text: str | None = None
    acknowledged_at: datetime | None = None; responded_at: datetime | None = None; due_at: datetime | None = None
    converted_design_change_id: UUID | None = None; created_at: datetime; updated_at: datetime


class ConvertRequestToDesignChange(CamelModel):
    title: str | None = Field(default=None, max_length=250)
    description: str | None = Field(default=None, max_length=10000)
    reason: str | None = Field(default=None, max_length=4000)
    affected_disciplines: list[str] = Field(default_factory=list, max_length=20)


class SiteVisitCreate(CamelModel):
    project_id: UUID; engineer_id: UUID | None = None
    title: str = Field(min_length=2, max_length=250)
    scheduled_start: datetime; scheduled_end: datetime
    visit_type: str = Field(max_length=50)
    location: str | None = Field(default=None, max_length=250)
    notes: str | None = Field(default=None, max_length=10000)
    participant_ids: list[UUID] = Field(default_factory=list, max_length=100)
    allow_conflict: bool = False

    @model_validator(mode="after")
    def validate_dates(self):
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduledEnd must be after scheduledStart")
        return self


class SiteVisitUpdate(CamelModel):
    scheduled_start: datetime | None = None; scheduled_end: datetime | None = None
    status: str | None = Field(default=None, max_length=30)
    reschedule_reason: str | None = Field(default=None, max_length=4000)
    notes: str | None = Field(default=None, max_length=10000)
    participant_ids: list[UUID] | None = Field(default=None, max_length=100)
    allow_conflict: bool = False


class SiteVisitOut(CamelModel):
    id: UUID; project_id: UUID; engineer_id: UUID; created_by_id: UUID
    title: str; scheduled_start: datetime; scheduled_end: datetime; visit_type: str
    location: str | None = None; notes: str | None = None; status: str
    reschedule_reason: str | None = None; completed_at: datetime | None = None; cancelled_at: datetime | None = None
    participant_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime; updated_at: datetime


class ReminderRuleUpsert(CamelModel):
    target_type: str = Field(default="IMPORTANT_COMMUNICATION", max_length=40)
    priority: str = Field(max_length=20)
    first_reminder_minutes: int = Field(ge=1, le=43200)
    repeat_interval_minutes: int = Field(ge=1, le=43200)
    maximum_reminders: int = Field(default=3, ge=0, le=20)
    escalation_recipient_id: UUID | None = None
    quiet_hours_start: time | None = None; quiet_hours_end: time | None = None
    enabled: bool = True


class MessageAccountabilityAction(CamelModel):
    action: str = Field(max_length=30)


class ActivityItem(CamelModel):
    id: UUID; occurred_at: datetime; action: str; entity_type: str
    entity_id: UUID | None = None; actor_id: UUID | None = None; details: dict = Field(default_factory=dict)
