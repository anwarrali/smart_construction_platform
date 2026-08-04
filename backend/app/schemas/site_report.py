from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from app.models.enums import VoiceProcessingStatus
from app.schemas.user import CamelModel, UserOut

class VoiceRecordingBase(CamelModel):
    audio_file_url: str
    duration_seconds: Optional[int] = None
    transcript_text: Optional[str] = None
    transcript_language: Optional[str] = None
    confidence_score: Optional[float] = None
    status: VoiceProcessingStatus = VoiceProcessingStatus.UPLOADED
    processing_error: Optional[str] = None

class VoiceRecordingCreate(CamelModel):
    project_id: UUID
    linked_task_id: Optional[UUID] = None
    audio_file_url: str
    duration_seconds: Optional[int] = None

class VoiceRecordingOut(VoiceRecordingBase):
    id: UUID
    project_id: UUID
    recorded_by_id: UUID
    created_at: datetime
    updated_at: datetime

class SiteReportBase(CamelModel):
    site_visit_id: Optional[UUID] = None
    report_date: date
    summary_text: Optional[str] = None
    progress_percentage_reported: Optional[float] = None
    weather_conditions: Optional[str] = None
    workers_count: Optional[int] = None
    equipment: Optional[str] = None
    work_completed: Optional[str] = None
    work_in_progress: Optional[str] = None
    delays: Optional[str] = None
    issues_summary: Optional[str] = None
    notes: Optional[str] = None
    review_status: str = "submitted"
    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    voice_recording_id: Optional[UUID] = None

class SiteReportCreate(CamelModel):
    project_id: UUID
    task_id: Optional[UUID] = None
    site_visit_id: Optional[UUID] = None
    report_date: date
    summary_text: Optional[str] = None
    progress_percentage_reported: Optional[float] = None
    weather_conditions: Optional[str] = None
    voice_recording_id: Optional[UUID] = None


class SiteReportUpdate(CamelModel):
    task_id: Optional[UUID] = None
    report_date: Optional[date] = None
    summary_text: Optional[str] = None
    progress_percentage_reported: Optional[float] = None
    weather_conditions: Optional[str] = None
    workers_count: Optional[int] = None
    equipment: Optional[str] = None
    work_completed: Optional[str] = None
    work_in_progress: Optional[str] = None
    delays: Optional[str] = None
    issues_summary: Optional[str] = None
    notes: Optional[str] = None
    review_status: Optional[str] = None

class SiteReportOut(SiteReportBase):
    id: UUID
    project_id: UUID
    task_id: Optional[UUID] = None
    submitted_by_id: UUID
    submitted_by: Optional[UserOut] = None
    voice_recording: Optional[VoiceRecordingOut] = None
    created_at: datetime
    updated_at: datetime
    attachment_count: int = 0
