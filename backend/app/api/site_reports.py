from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import uuid
from datetime import date, datetime, time, timezone

from app.db.database import get_db
from app.models.user import User, EngineerProfile
from app.models.site_report import SiteReport
from app.models.voice_recording import VoiceRecording
from app.schemas.site_report import SiteReportOut, SiteReportCreate, SiteReportUpdate
from app.core.deps import (
    get_current_user,
    user_has_project_access,
    accessible_project_ids,
    is_main_contractor_engineer,
    is_consultant_engineer,
)
from app.services.file_storage import save_upload, delete_upload
from app.models.enums import VoiceProcessingStatus
from app.models.enums import UserRole, NotificationType
from app.models.project import Project
from app.models.project import ProjectMember
from app.models.notification import Notification
from app.models.task import Task
from app.models.attachment import Attachment
from app.services.audit_service import record_audit

router = APIRouter(tags=["Site Reports"])

@router.get("/site-reports", response_model=List[SiteReportOut])
@router.get("/reports", response_model=List[SiteReportOut])
def list_site_reports(
    project_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    discipline: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    submitted_by_id: Optional[uuid.UUID] = None,
    has_attachments: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == UserRole.ENGINEER:
        if not (is_main_contractor_engineer(current_user) or is_consultant_engineer(current_user)):
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
        if not project_id:
            raise HTTPException(status_code=400, detail="Engineer report queries require a selected project")
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(SiteReport)
    if current_user.role.value != "admin":
        query = query.filter(SiteReport.project_id.in_(accessible_project_ids(db, current_user) or []))
    if current_user.role == UserRole.OWNER:
        query = query.filter(SiteReport.review_status.in_(["submitted", "approved"]))
    if project_id:
        query = query.filter(SiteReport.project_id == project_id)
        if is_consultant_engineer(current_user):
            discipline = current_user.engineer_profile.discipline if current_user.engineer_profile else None
            discipline_task_ids = db.query(Task.id).filter(Task.project_id == project_id, Task.discipline == (discipline.value if discipline else ""))
            query = query.filter((SiteReport.task_id.is_(None)) | SiteReport.task_id.in_(discipline_task_ids))
    if status:
        query = query.filter(SiteReport.review_status == status)
    if discipline:
        query = query.join(User, User.id == SiteReport.submitted_by_id).join(
            EngineerProfile, EngineerProfile.user_id == User.id
        ).filter(EngineerProfile.discipline == discipline)
    if date_from:
        query = query.filter(SiteReport.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.filter(SiteReport.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if submitted_by_id:
        query = query.filter(SiteReport.submitted_by_id == submitted_by_id)
    attachment_exists = db.query(Attachment.id).filter(Attachment.entity_type == "SITE_REPORT", Attachment.entity_id == SiteReport.id).exists()
    if has_attachments is not None:
        query = query.filter(attachment_exists if has_attachments else ~attachment_exists)
    items = query.order_by(SiteReport.report_date.desc()).all()
    counts = dict(db.query(Attachment.entity_id, func.count(Attachment.id)).filter(
        Attachment.entity_type == "SITE_REPORT", Attachment.entity_id.in_([item.id for item in items])
    ).group_by(Attachment.entity_id).all()) if items else {}
    for item in items:
        item.attachment_count = counts.get(item.id, 0)
    return items

@router.get("/site-reports/project/{project_id}", response_model=List[SiteReportOut])
@router.get("/reports/project/{project_id}", response_model=List[SiteReportOut])
def get_site_reports_by_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    if current_user.role == UserRole.ENGINEER and not (
        is_main_contractor_engineer(current_user) or is_consultant_engineer(current_user)
    ):
        raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    query = db.query(SiteReport).filter(SiteReport.project_id == project_id)
    if is_consultant_engineer(current_user):
        discipline = current_user.engineer_profile.discipline if current_user.engineer_profile else None
        discipline_task_ids = db.query(Task.id).filter(Task.project_id == project_id, Task.discipline == (discipline.value if discipline else ""))
        query = query.filter((SiteReport.task_id.is_(None)) | SiteReport.task_id.in_(discipline_task_ids))
    if current_user.role == UserRole.OWNER:
        query = query.filter(SiteReport.review_status.in_(["submitted", "approved"]))
    items = query.order_by(SiteReport.report_date.desc()).all()
    counts = dict(db.query(Attachment.entity_id, func.count(Attachment.id)).filter(
        Attachment.entity_type == "SITE_REPORT",
        Attachment.entity_id.in_([item.id for item in items]),
    ).group_by(Attachment.entity_id).all()) if items else {}
    for item in items:
        item.attachment_count = counts.get(item.id, 0)
    return items

@router.get("/site-reports/{report_id}", response_model=SiteReportOut)
@router.get("/reports/{report_id}", response_model=SiteReportOut)
def get_site_report_by_id(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rep = db.query(SiteReport).filter(SiteReport.id == report_id).first()
    if not rep:
        raise HTTPException(status_code=404, detail="Site report not found")
    if not user_has_project_access(db, current_user, rep.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this report")
    if current_user.role == UserRole.OWNER and rep.review_status not in {"submitted", "approved"}:
        raise HTTPException(status_code=403, detail="Owners can view submitted or finalized site reports only")
    if is_consultant_engineer(current_user) and rep.task_id:
        task = db.get(Task, rep.task_id)
        discipline = current_user.engineer_profile.discipline.value if current_user.engineer_profile else None
        if not task or task.discipline != discipline:
            raise HTTPException(status_code=403, detail="This report is outside your discipline")
    rep.attachment_count = db.query(Attachment).filter(Attachment.entity_type == "SITE_REPORT", Attachment.entity_id == rep.id).count()
    return rep

@router.post("/reports/submit", response_model=SiteReportOut)
@router.post("/site-reports/submit", response_model=SiteReportOut)
async def submit_site_report(
    project_id: str = Form(...),
    report_date: str = Form(...),
    content: str = Form(...),
    report_type: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    site_visit_id: Optional[str] = Form(None),
    weather_conditions: Optional[str] = Form(None),
    workers_count: Optional[int] = Form(None),
    equipment: Optional[str] = Form(None),
    work_completed: Optional[str] = Form(None),
    work_in_progress: Optional[str] = Form(None),
    delays: Optional[str] = Form(None),
    issues_summary: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    review_status: str = Form("submitted"),
    photos: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        proj_uuid = uuid.UUID(project_id)
        task_uuid = uuid.UUID(task_id) if task_id else None
        visit_uuid = uuid.UUID(site_visit_id) if site_visit_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid projectId")
    if current_user.role not in {UserRole.ENGINEER, UserRole.PROJECT_MANAGER}:
        raise HTTPException(status_code=403, detail="Only assigned engineers or the Project Manager can submit site reports")
    if current_user.role == UserRole.ENGINEER and not is_main_contractor_engineer(current_user):
        raise HTTPException(status_code=403, detail="Active Main Contractor Engineer access required")
    if not user_has_project_access(db, current_user, proj_uuid):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    if current_user.role == UserRole.ENGINEER:
        assignment = db.query(ProjectMember).filter(
            ProjectMember.project_id == proj_uuid,
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_active == True,
            ProjectMember.is_site_engineer == True,
        ).first()
        if not assignment:
            raise HTTPException(status_code=403, detail="Only engineers assigned as Site Engineers can submit field reports")
    linked_task = db.query(Task).filter(Task.id == task_uuid, Task.project_id == proj_uuid).first() if task_uuid else None
    if task_uuid and not linked_task:
        raise HTTPException(status_code=400, detail="taskId must belong to the selected project")
    if linked_task and current_user.role == UserRole.ENGINEER and not any(
        assignee.id == current_user.id for assignee in linked_task.assignees
    ):
        raise HTTPException(status_code=403, detail="You can only report against a task assigned to you")
    if review_status not in {"draft", "submitted"}:
        raise HTTPException(status_code=400, detail="reviewStatus must be draft or submitted")
    
    try:
        parsed_date = date.fromisoformat(report_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="reportDate must use YYYY-MM-DD format")
        
    if visit_uuid:
        from app.models.collaboration import SiteVisit
        visit = db.query(SiteVisit).filter(SiteVisit.id == visit_uuid, SiteVisit.project_id == proj_uuid).first()
        if not visit:
            raise HTTPException(status_code=400, detail="siteVisitId must belong to the selected project")
        if current_user.role == UserRole.ENGINEER and visit.engineer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only the scheduled engineer can report this visit")
        if db.query(SiteReport).filter(SiteReport.site_visit_id == visit_uuid).first():
            raise HTTPException(status_code=409, detail="This site visit already has a site report")
    new_report = SiteReport(
        project_id=proj_uuid,
        task_id=task_uuid,
        site_visit_id=visit_uuid,
        submitted_by_id=current_user.id,
        report_date=parsed_date,
        summary_text=content,
        progress_percentage_reported=None,
        weather_conditions=weather_conditions,
        workers_count=workers_count,
        equipment=equipment,
        work_completed=work_completed,
        work_in_progress=work_in_progress,
        delays=delays,
        issues_summary=issues_summary,
        notes=notes,
        review_status=review_status,
    )
    
    db.add(new_report)
    db.flush()
    project = db.get(Project, proj_uuid)
    if review_status == "submitted" and project and project.project_manager_id and project.project_manager_id != current_user.id:
        db.add(Notification(user_id=project.project_manager_id, title="Site Report Requires Review",
            message=f"A new Site Report was submitted for {project.name}.", type=NotificationType.REPORT_READY,
            project_id=proj_uuid, related_entity_type="SITE_REPORT", related_entity_id=new_report.id))
    
    # Store photos through the generic contextual attachment system.
    for index, photo in enumerate(photos):
        file_url, file_size = await save_upload(photo, "site-reports")
        asset = Attachment(
            original_filename=photo.filename or f"site-report-{index + 1}.jpg",
            storage_key=file_url.split("/uploads/", 1)[-1],
            mime_type=photo.content_type or "application/octet-stream",
            project_id=proj_uuid,
            uploaded_by_id=current_user.id,
            file_url=file_url,
            file_size_bytes=file_size,
            entity_type="SITE_REPORT",
            entity_id=new_report.id,
        )
        db.add(asset)
    record_audit(db, actor_id=current_user.id, action="created", entity_type="site_report",
                 entity_id=new_report.id, project_id=new_report.project_id)
    db.commit()
    db.refresh(new_report)
    return new_report

@router.put("/site-reports/{report_id}/review", response_model=SiteReportOut)
def review_site_report(
    report_id: uuid.UUID,
    approved: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SiteReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Site report not found")
    project = db.get(Project, report.project_id)
    if current_user.role != UserRole.PROJECT_MANAGER or not project or project.project_manager_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can review site reports")
    report.review_status = "approved" if approved else "rejected"
    report.reviewed_by_id = current_user.id
    report.reviewed_at = datetime.now(timezone.utc)
    db.add(Notification(user_id=report.submitted_by_id, title="Site report reviewed",
                        message=f"Your site report was {report.review_status}", type=NotificationType.REPORT_READY,
                        project_id=report.project_id, related_entity_type="SITE_REPORT", related_entity_id=report.id))
    record_audit(db, actor_id=current_user.id, action=f"{report.review_status}", entity_type="site_report",
                 entity_id=report.id, project_id=report.project_id)
    db.commit()
    db.refresh(report)
    return report


@router.put("/site-reports/{report_id}", response_model=SiteReportOut)
@router.put("/reports/{report_id}", response_model=SiteReportOut)
def update_site_report_draft(
    report_id: uuid.UUID,
    data: SiteReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SiteReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Site report not found")
    if not user_has_project_access(db, current_user, report.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this report")
    if current_user.id != report.submitted_by_id:
        raise HTTPException(status_code=403, detail="You can only edit site reports you created")
    if current_user.role == UserRole.ENGINEER and not is_main_contractor_engineer(current_user):
        raise HTTPException(status_code=403, detail="Active Main Contractor Engineer access required")
    if report.review_status != "draft":
        raise HTTPException(status_code=409, detail="Submitted or reviewed reports cannot be overwritten")
    if data.review_status and data.review_status not in {"draft", "submitted"}:
        raise HTTPException(status_code=400, detail="reviewStatus must be draft or submitted")
    if "task_id" in data.model_fields_set and data.task_id:
        task = db.query(Task).filter(Task.id == data.task_id, Task.project_id == report.project_id).first()
        if not task:
            raise HTTPException(status_code=400, detail="taskId must belong to the report project")
        if current_user.role == UserRole.ENGINEER and not any(
            assignee.id == current_user.id for assignee in task.assignees
        ):
            raise HTTPException(status_code=403, detail="You can only link a task assigned to you")
    for field in (
        "task_id", "report_date", "summary_text", "progress_percentage_reported",
        "weather_conditions", "workers_count", "equipment", "work_completed",
        "work_in_progress", "delays", "issues_summary", "notes",
    ):
        if field in data.model_fields_set:
            setattr(report, field, getattr(data, field))
    if data.review_status:
        report.review_status = data.review_status
    if report.review_status == "submitted":
        project = db.get(Project, report.project_id)
        if project and project.project_manager_id and project.project_manager_id != current_user.id:
            db.add(Notification(user_id=project.project_manager_id, title="Site Report Requires Review",
                message=f"A Site Report was submitted for {project.name}.", type=NotificationType.REPORT_READY,
                project_id=report.project_id, related_entity_type="SITE_REPORT", related_entity_id=report.id))
    record_audit(db, actor_id=current_user.id,
                 action="submitted" if report.review_status == "submitted" else "draft_updated",
                 entity_type="site_report", entity_id=report.id, project_id=report.project_id)
    db.commit()
    db.refresh(report)
    return report

@router.delete("/site-reports/{report_id}")
def delete_site_report(report_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = db.get(SiteReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Site report not found")
    project = db.get(Project, report.project_id)
    can_delete = (current_user.id == report.submitted_by_id and report.review_status == "draft") or current_user.role == UserRole.ADMIN or (
        current_user.role == UserRole.PROJECT_MANAGER and project and project.project_manager_id == current_user.id)
    if not can_delete:
        raise HTTPException(status_code=403, detail="You cannot delete this site report")
    for asset in db.query(Attachment).filter(Attachment.entity_type == "SITE_REPORT", Attachment.entity_id == report.id).all():
        delete_upload(asset.file_url)
        db.delete(asset)
    db.delete(report)
    db.commit()
    return {"message": "Site report deleted"}

@router.post("/voice-recording/upload")
async def upload_voice_recording(
    audio: UploadFile = File(...),
    project_id: str = Form(...),
    task_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        proj_uuid = uuid.UUID(project_id)
        task_uuid = uuid.UUID(task_id) if task_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid projectId or taskId")
    if not user_has_project_access(db, current_user, proj_uuid):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    
    audio_url, _ = await save_upload(audio, "audio")
    
    # Create voice recording
    vr = VoiceRecording(
        project_id=proj_uuid,
        recorded_by_id=current_user.id,
        linked_task_id=task_uuid,
        audio_file_url=audio_url,
        duration_seconds=None,
        transcript_text=None,
        transcript_language=None,
        confidence_score=None,
        status=VoiceProcessingStatus.UPLOADED
    )
    
    db.add(vr)
    db.commit()
    db.refresh(vr)
    
    return {
        "voiceRecordingId": vr.id,
        "status": vr.status.value,
        "transcript": None,
        "siteReportId": None
    }
