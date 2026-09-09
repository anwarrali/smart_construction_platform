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
from app.schemas.site_report import SiteReportOut, SiteReportCreate, SiteReportUpdate, SiteReportReviewRequest
from app.core.deps import (
    get_current_user,
    user_has_project_access,
    accessible_project_ids,
)
from app.services import rbac, work_scope
from app.services.file_storage import delete_upload
from app.services.private_storage import private_storage
from app.models.enums import VoiceProcessingStatus
from app.models.enums import UserRole, NotificationType
from app.services.authorization import has_permission, require, manageable_project
from app.models.project import Project
from app.models.project import ProjectMember
from app.models.notification import Notification
from app.models.task import Task
from app.models.attachment import Attachment
from app.services.audit_service import record_audit
from app.services.notification_service import (
    CATEGORY_DIRECT, CATEGORY_WORKFLOW, PRIORITY_IMPORTANT, PRIORITY_NORMAL, notify,
)

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
    # The "Active Engineer organization side is required" refusal is gone. It
    # rejected any Engineer who was neither contractor-side nor
    # consultant-side — which, in a consulting office, is the office's own
    # engineers. There is no reason to hide a project's reports from staff the
    # office put on that project; discipline narrowing below still applies.
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(SiteReport)
    # "Sees every project" is `platform.view_all_projects`, which
    # `accessible_project_ids` already answers by returning None. Reading the
    # role instead meant two things went wrong: an administrator whose
    # permission had been explicitly revoked still bypassed the filter, and a
    # non-administrator who had been *granted* it got `None or []` — an empty
    # list, so they saw nothing at all.
    accessible_ids = accessible_project_ids(db, current_user)
    if accessible_ids is not None:
        query = query.filter(SiteReport.project_id.in_(accessible_ids))
    # The client sees finished work, not drafts. A relationship on this
    # project, not an identity on the account.
    if rbac.is_client_participant(db, current_user, project_id):
        query = query.filter(SiteReport.review_status.in_(["submitted", "approved"]))
    if project_id:
        query = query.filter(SiteReport.project_id == project_id)
        query = work_scope.narrow_to_disciplines(
            query, SiteReport.task_id, db, current_user, project_id,
        )
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
    query = work_scope.narrow_to_disciplines(
        db.query(SiteReport).filter(SiteReport.project_id == project_id),
        SiteReport.task_id, db, current_user, project_id,
    )
    if rbac.is_client_participant(db, current_user, project_id):
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
    if rbac.is_client_participant(db, current_user, rep.project_id) and rep.review_status not in {"submitted", "approved"}:
        raise HTTPException(status_code=403, detail="Clients can view submitted or finalized site reports only")
    if rep.task_id and not work_scope.task_is_in_scope(
        db, current_user, rep.project_id, db.get(Task, rep.task_id)
    ):
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
    # Who may file a report is configurable; which project they may file it
    # against, and the contractor-side and discipline-assignment rules below,
    # are not — `require` re-checks project access for a project-scoped code.
    # `site_report.submit` plus the site-engineer assignment below is the whole
    # decision. The affiliation check that used to sit here refused any Engineer
    # who was not contractor-side, which in a consulting office excludes the
    # office's own site engineers — the people the feature is for.
    require(db, current_user, "site_report.submit", proj_uuid)
    if not user_has_project_access(db, current_user, proj_uuid):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    # Site responsibility is the narrowing, and it is an assignment on the
    # membership — any number of people may carry it, of any discipline. It
    # used to be asked only of accounts whose legacy role was ENGINEER, so an
    # office that gave `site_report.submit` to a role it created skipped the
    # check entirely. Everybody who is narrowed is narrowed the same way now:
    # holding `task.view_all` means you are not.
    if not work_scope.sees_all_tasks(db, current_user, proj_uuid):
        if not work_scope.is_site_engineer(db, current_user, proj_uuid):
            raise HTTPException(
                status_code=403,
                detail="Only members carrying site responsibility can file field reports",
            )
    linked_task = db.query(Task).filter(Task.id == task_uuid, Task.project_id == proj_uuid).first() if task_uuid else None
    if task_uuid and not linked_task:
        raise HTTPException(status_code=400, detail="taskId must belong to the selected project")
    if linked_task and not work_scope.sees_all_tasks(db, current_user, proj_uuid) and not any(
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
        if not work_scope.sees_all_tasks(db, current_user, proj_uuid) and visit.engineer_id != current_user.id:
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
        # Which discipline this visit covered. Without it a project with three
        # site engineers produces three reports a day that cannot be told
        # apart, filtered, or routed to the right reviewer.
        discipline_id=work_scope.report_discipline_id(
            db, current_user, proj_uuid, linked_task,
        ),
    )
    
    db.add(new_report)
    db.flush()
    project = db.get(Project, proj_uuid)
    if review_status == "submitted" and project and project.project_manager_id and project.project_manager_id != current_user.id:
        notify(
            db, user_id=project.project_manager_id,
            title="Site report awaiting your verification",
            message=f"A new Site Report was submitted for {project.name}.",
            notification_type=NotificationType.REPORT_READY,
            category=CATEGORY_WORKFLOW, priority=PRIORITY_NORMAL, requires_action=True,
            project_id=proj_uuid, entity_type="SITE_REPORT", entity_id=new_report.id,
            # One "awaiting verification" per report; the follow-ups come from
            # the reminder sweep, not from re-notifying here.
            dedupe_key=f"site-report-verify:{new_report.id}",
            message_key="siteReport.awaitingVerification",
            message_params={"project": project.name},
        )
    
    # Store photos through the generic contextual attachment system.
    for index, photo in enumerate(photos):
        storage_key, file_size = await private_storage.save(photo, "site-reports")
        asset = Attachment(
            original_filename=photo.filename or f"site-report-{index + 1}.jpg",
            storage_key=storage_key,
            mime_type=photo.content_type or "application/octet-stream",
            project_id=proj_uuid,
            uploaded_by_id=current_user.id,
            file_url=f"private://{storage_key}",
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
@router.put("/reports/{report_id}/review", response_model=SiteReportOut)
def review_site_report(
    report_id: uuid.UUID,
    data: SiteReportReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SiteReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Site report not found")
    # The capability is configurable (`site_report.verify`), but
    # `manageable_project` still pins it to the Project Manager actually
    # assigned to this project — a grant can never let a PM verify a report
    # on someone else's project, and it re-checks project access for every
    # other role. Admin, which holds no default here, can still be granted
    # the permission explicitly through Access Control without this check
    # narrowing them to a single project (the PM-only branch inside
    # `manageable_project` only applies to `UserRole.PROJECT_MANAGER`).
    manageable_project(db, current_user, report.project_id, "site_report.verify")
    if report.review_status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a submitted site report awaiting verification can be reviewed",
        )
    reason = (data.rejection_reason or "").strip()
    if not data.approved and not reason:
        raise HTTPException(status_code=400, detail="A rejection reason is required")

    report.review_status = "approved" if data.approved else "rejected"
    report.reviewed_by_id = current_user.id
    report.reviewed_at = datetime.now(timezone.utc)
    report.rejection_reason = reason if not data.approved else None

    if data.approved:
        title, message = "Site report verified", f"Your site report for {report.report_date} was verified by {current_user.full_name}."
    else:
        title, message = "Site report rejected", f"Your site report for {report.report_date} was rejected by {current_user.full_name}: {reason}"
    if report.submitted_by_id != current_user.id:
        notify(
            db, user_id=report.submitted_by_id, title=title, message=message,
            notification_type=NotificationType.REPORT_READY,
            category=CATEGORY_DIRECT,
            # A rejection needs the author to do something; an approval is
            # information they should see but need not act on.
            priority=PRIORITY_IMPORTANT if not data.approved else PRIORITY_NORMAL,
            requires_action=not data.approved,
            project_id=report.project_id,
            entity_type="SITE_REPORT", entity_id=report.id,
            message_key="siteReport.rejected" if not data.approved else "siteReport.verified",
            message_params={"date": str(report.report_date),
                            "reviewer": current_user.full_name, "reason": reason},
        )
    record_audit(db, actor_id=current_user.id,
                 action="site_report_verified" if data.approved else "site_report_rejected",
                 entity_type="site_report", entity_id=report.id, project_id=report.project_id,
                 details={"rejection_reason": reason} if not data.approved else None)
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
    if report.review_status != "draft":
        raise HTTPException(status_code=409, detail="Submitted or reviewed reports cannot be overwritten")
    if data.review_status and data.review_status not in {"draft", "submitted"}:
        raise HTTPException(status_code=400, detail="reviewStatus must be draft or submitted")
    if "task_id" in data.model_fields_set and data.task_id:
        task = db.query(Task).filter(Task.id == data.task_id, Task.project_id == report.project_id).first()
        if not task:
            raise HTTPException(status_code=400, detail="taskId must belong to the report project")
        if not work_scope.sees_all_tasks(db, current_user, report.project_id) and not any(
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
            notify(
                db, user_id=project.project_manager_id,
                title="Site report awaiting your verification",
                message=f"A Site Report was submitted for {project.name}.",
                notification_type=NotificationType.REPORT_READY,
                category=CATEGORY_WORKFLOW, priority=PRIORITY_NORMAL, requires_action=True,
                project_id=report.project_id, entity_type="SITE_REPORT", entity_id=report.id,
                dedupe_key=f"site-report-verify:{report.id}",
                message_key="siteReport.awaitingVerification",
                message_params={"project": project.name},
            )
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
    # The id comparison already implies the role: `project_manager_id` is
    # validated to be an active PROJECT_MANAGER wherever it is written.
    can_delete = (
        (current_user.id == report.submitted_by_id and report.review_status == "draft")
        or bool(project and project.project_manager_id == current_user.id)
        or has_permission(db, current_user, "site_report.verify", report.project_id)
    )
    if not can_delete:
        raise HTTPException(status_code=403, detail="You cannot delete this site report")
    for asset in db.query(Attachment).filter(Attachment.entity_type == "SITE_REPORT", Attachment.entity_id == report.id).all():
        # Same split as `delete_attachment`: private for anything stored since
        # the move, the old public tree for rows the backfill has not reached.
        if asset.file_url.startswith("private://") or private_storage.exists(asset.storage_key):
            private_storage.delete(asset.storage_key)
        else:
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
    
    audio_key, _ = await private_storage.save(audio, "audio")
    
    # Create voice recording
    vr = VoiceRecording(
        project_id=proj_uuid,
        recorded_by_id=current_user.id,
        linked_task_id=task_uuid,
        audio_file_url=f"private://{audio_key}",
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
