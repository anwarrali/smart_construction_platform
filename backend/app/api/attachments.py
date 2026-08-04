from datetime import datetime
from pathlib import PurePosixPath
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.deps import (
    accessible_project_ids,
    get_current_user,
    user_has_project_access,
    is_main_contractor_engineer,
    is_consultant_engineer,
    is_worker,
)
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.design_change import DesignChange
from app.models.issue import Issue
from app.models.site_report import SiteReport
from app.models.task import Task, TaskReview
from app.models.user import User
from app.models.enums import UserRole, TaskStatus
from app.models.collaboration import OwnerRequest
from app.schemas.attachment import AttachmentOut
from app.services.audit_service import record_audit
from app.services.file_storage import delete_upload, save_upload

router = APIRouter(prefix="/attachments", tags=["Attachments"])
ENTITY_MODELS = {
    "ISSUE": Issue,
    "SITE_REPORT": SiteReport,
    "DESIGN_CHANGE": DesignChange,
    "TASK": Task,
    "TASK_REVIEW": TaskReview,
    "OWNER_REQUEST": OwnerRequest,
}


def _entity_or_404(
    db: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    project_id: uuid.UUID,
    current_user: User,
    for_write: bool = False,
):
    if is_worker(current_user):
        raise HTTPException(
            status_code=403,
            detail="Workers must upload photos through the field evidence workflow",
        )
    model = ENTITY_MODELS.get(entity_type)
    if not model:
        raise HTTPException(status_code=400, detail="Unsupported attachment entityType")
    entity = db.get(model, entity_id)
    related_task = entity.task if entity_type == "TASK_REVIEW" and entity else (entity if entity_type == "TASK" else None)
    entity_project_id = related_task.project_id if related_task else (entity.project_id if entity else None)
    if not entity or entity_project_id != project_id:
        raise HTTPException(status_code=404, detail="Related project entity not found")
    if related_task and current_user.role == UserRole.ENGINEER:
        if is_main_contractor_engineer(current_user):
            if not any(assignee.id == current_user.id for assignee in related_task.assignees):
                raise HTTPException(status_code=403, detail="This task is not assigned to you")
            if entity_type == "TASK_REVIEW":
                raise HTTPException(status_code=403, detail="Contractor Engineers cannot alter Consultant review attachments")
            if for_write and related_task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE, TaskStatus.CANCELLED}:
                raise HTTPException(status_code=409, detail="Task evidence is locked in the current workflow state")
        elif is_consultant_engineer(current_user):
            from app.api.tasks import _can_consult_task
            if not _can_consult_task(db, current_user, related_task):
                raise HTTPException(status_code=403, detail="You cannot review this task discipline")
            if for_write and entity_type != "TASK_REVIEW":
                raise HTTPException(status_code=403, detail="Consultants cannot replace contractor evidence")
            if entity_type == "TASK_REVIEW" and entity.status not in {"pending", "in_review", "clarification_requested"}:
                raise HTTPException(status_code=409, detail="Finalized review attachments are locked")
        else:
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    elif current_user.role == UserRole.ENGINEER and is_consultant_engineer(current_user):
        if entity_type == "ISSUE":
            if entity.task_id:
                task = db.get(Task, entity.task_id)
                discipline = current_user.engineer_profile.discipline.value if current_user.engineer_profile else None
                if not task or task.discipline != discipline:
                    raise HTTPException(status_code=403, detail="This issue is outside your discipline")
            if for_write and entity.raised_by_id != current_user.id:
                raise HTTPException(status_code=403, detail="You can only add evidence to your own observation")
        elif entity_type == "SITE_REPORT":
            if entity.task_id:
                task = db.get(Task, entity.task_id)
                discipline = current_user.engineer_profile.discipline.value if current_user.engineer_profile else None
                if not task or task.discipline != discipline:
                    raise HTTPException(status_code=403, detail="This report is outside your discipline")
            if for_write:
                raise HTTPException(status_code=403, detail="Consultants cannot alter contractor site reports")
        else:
            raise HTTPException(status_code=403, detail="Consultants cannot attach files to this entity type")
    return entity


@router.get("", response_model=List[AttachmentOut])
def list_attachments(
    project_id: Optional[uuid.UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[uuid.UUID] = None,
    uploaded_by_id: Optional[uuid.UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Attachment)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(Attachment.project_id.in_(accessible_project_ids(db, current_user) or []))
    if current_user.role == UserRole.ENGINEER:
        if not project_id:
            raise HTTPException(status_code=400, detail="Engineer attachment queries require a selected project")
        if is_main_contractor_engineer(current_user):
            assigned_task_ids = db.query(Task.id).filter(Task.assignees.any(User.id == current_user.id))
            query = query.filter(or_(Attachment.entity_type.notin_(["TASK", "TASK_REVIEW"]),
                                     and_(Attachment.entity_type == "TASK", Attachment.entity_id.in_(assigned_task_ids))))
        elif is_consultant_engineer(current_user):
            from app.api.tasks import _can_consult_task
            candidate_tasks = db.query(Task).filter(
                Task.project_id == project_id, Task.review_required == True,
                Task.id.in_(db.query(TaskReview.task_id)),
            ).all()
            reviewable_task_ids = [
                task.id for task in candidate_tasks if _can_consult_task(db, current_user, task)
            ]
            review_ids = db.query(TaskReview.id).filter(TaskReview.task_id.in_(reviewable_task_ids))
            issue_ids = db.query(Issue.id).filter(
                Issue.project_id == project_id,
                or_(Issue.task_id.is_(None), Issue.task_id.in_(reviewable_task_ids)),
            )
            report_ids = db.query(SiteReport.id).filter(
                SiteReport.project_id == project_id,
                or_(SiteReport.task_id.is_(None), SiteReport.task_id.in_(reviewable_task_ids)),
            )
            query = query.filter(or_(
                and_(Attachment.entity_type == "TASK", Attachment.entity_id.in_(reviewable_task_ids)),
                and_(Attachment.entity_type == "TASK_REVIEW", Attachment.entity_id.in_(review_ids)),
                and_(Attachment.entity_type == "ISSUE", Attachment.entity_id.in_(issue_ids)),
                and_(Attachment.entity_type == "SITE_REPORT", Attachment.entity_id.in_(report_ids)),
            ))
        else:
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
    elif is_worker(current_user):
        query = query.filter(
            Attachment.entity_type == "FIELD_SUBMISSION",
            Attachment.uploaded_by_id == current_user.id,
        )
    if project_id:
        query = query.filter(Attachment.project_id == project_id)
    if entity_type:
        query = query.filter(Attachment.entity_type == entity_type.upper())
    if entity_id:
        query = query.filter(Attachment.entity_id == entity_id)
    if uploaded_by_id:
        query = query.filter(Attachment.uploaded_by_id == uploaded_by_id)
    if date_from:
        query = query.filter(Attachment.created_at >= date_from)
    if date_to:
        query = query.filter(Attachment.created_at <= date_to)
    return query.order_by(Attachment.created_at.desc()).all()


@router.post("/upload", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    entity_type: str = Form(...),
    entity_id: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        project_uuid, entity_uuid = uuid.UUID(project_id), uuid.UUID(entity_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid projectId or entityId")
    normalized_type = entity_type.upper()
    if not user_has_project_access(db, current_user, project_uuid):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    _entity_or_404(db, normalized_type, entity_uuid, project_uuid, current_user, for_write=True)
    file_url, file_size = await save_upload(file, "attachments")
    attachment = Attachment(
        original_filename=file.filename or "file",
        storage_key=PurePosixPath(file_url.split("/uploads/", 1)[-1]).as_posix(),
        file_url=file_url,
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=file_size,
        uploaded_by_id=current_user.id,
        project_id=project_uuid,
        entity_type=normalized_type,
        entity_id=entity_uuid,
    )
    db.add(attachment)
    db.flush()
    record_audit(db, actor_id=current_user.id, action="attachment_uploaded", entity_type=normalized_type.lower(),
                 entity_id=entity_uuid, project_id=project_uuid, details={"attachment_id": attachment.id, "filename": attachment.original_filename})
    db.commit()
    db.refresh(attachment)
    return attachment


@router.delete("/{attachment_id}")
def delete_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if not user_has_project_access(db, current_user, attachment.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this attachment")
    entity = _entity_or_404(
        db,
        attachment.entity_type,
        attachment.entity_id,
        attachment.project_id,
        current_user,
    )
    if current_user.role.value not in {"admin", "project_manager"} and attachment.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="You cannot delete this attachment")
    if (
        current_user.role == UserRole.ENGINEER
        and attachment.entity_type in {"TASK", "TASK_REVIEW"}
        and (
            (attachment.entity_type == "TASK" and entity.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE})
            or (attachment.entity_type == "TASK_REVIEW" and entity.status in {"approved", "rejected"})
        )
    ):
        raise HTTPException(status_code=403, detail="Submitted task evidence cannot be deleted")
    record_audit(db, actor_id=current_user.id, action="attachment_deleted", entity_type=attachment.entity_type.lower(),
                 entity_id=attachment.entity_id, project_id=attachment.project_id, details={"attachment_id": attachment.id})
    delete_upload(attachment.file_url)
    db.delete(attachment)
    db.commit()
    return {"message": "Attachment deleted"}
