from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
import uuid

from app.db.database import get_db
from app.services.authorization import require
from app.models.user import User
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.core.deps import get_current_user
from app.core.deps import user_has_project_access, accessible_project_ids, is_main_contractor_engineer, is_consultant_engineer
from app.services.file_storage import save_upload, delete_upload
from app.models.enums import UserRole, DocumentType, TaskStatus, NotificationType
from app.models.project import Project
from app.models.task import Task
from app.models.notification import Notification
from app.services.audit_service import record_audit

router = APIRouter(prefix="/documents", tags=["Documents"])


def _consultant_document_scope(query, db: Session, current_user: User, project_id: uuid.UUID):
    if not current_user.engineer_profile:
        raise HTTPException(status_code=403, detail="Consultant specialization is required")
    discipline = current_user.engineer_profile.discipline.value
    authorized_tasks = db.query(Task.id).filter(
        Task.project_id == project_id,
        Task.discipline == discipline,
    )
    return query.filter(or_(Document.task_id.is_(None), Document.task_id.in_(authorized_tasks)))


def _owner_document_scope(query):
    """Owners see official project files and evidence from approved completed work only."""
    return query.filter(or_(
        and_(
            Document.task_id.is_(None),
            Document.document_type.in_([DocumentType.CONTRACT, DocumentType.PERMIT]),
        ),
        Document.task.has(and_(
            Task.status == TaskStatus.DONE,
            Task.review_status == "approved",
        )),
    ))

@router.get("", response_model=List[DocumentOut])
def list_documents(
    project_id: Optional[uuid.UUID] = None,
    document_type: Optional[DocumentType] = None,
    task_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == UserRole.ENGINEER:
        if not (is_main_contractor_engineer(current_user) or is_consultant_engineer(current_user)):
            raise HTTPException(status_code=403, detail="Active Engineer organization side is required")
        if not project_id:
            raise HTTPException(status_code=400, detail="Engineer document queries require a selected project")
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(Document)
    if current_user.role != UserRole.ADMIN:
        accessible_ids = accessible_project_ids(db, current_user) or []
        query = query.filter(Document.project_id.in_(accessible_ids))
    if current_user.role == UserRole.OWNER:
        query = _owner_document_scope(query)
    if project_id:
        query = query.filter(Document.project_id == project_id)
        if is_consultant_engineer(current_user):
            query = _consultant_document_scope(query, db, current_user, project_id)
    if document_type:
        query = query.filter(Document.document_type == document_type)
    if task_id:
        query = query.filter(Document.task_id == task_id)
    if search:
        query = query.filter(Document.title.ilike(f"%{search.strip()}%"))
    return query.all()

@router.get("/project/{project_id}", response_model=List[DocumentOut])
def get_documents_by_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    query = db.query(Document).filter(Document.project_id == project_id)
    if current_user.role == UserRole.OWNER:
        query = _owner_document_scope(query)
    if is_consultant_engineer(current_user):
        query = _consultant_document_scope(query, db, current_user, project_id)
    return query.all()

@router.get("/search", response_model=List[DocumentOut])
def search_documents(
    query: str,
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Document).filter(Document.title.ilike(f"%{query}%") | Document.notes.ilike(f"%{query}%"))
    if current_user.role != UserRole.ADMIN:
        q = q.filter(Document.project_id.in_(accessible_project_ids(db, current_user) or []))
    if current_user.role == UserRole.OWNER:
        q = _owner_document_scope(q)
    if project_id:
        q = q.filter(Document.project_id == project_id)
        if is_consultant_engineer(current_user):
            q = _consultant_document_scope(q, db, current_user, project_id)
    return q.all()

@router.get("/{document_id}", response_model=DocumentOut)
def get_document_by_id(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not user_has_project_access(db, current_user, doc.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")
    if current_user.role == UserRole.OWNER and not _owner_document_scope(
        db.query(Document).filter(Document.id == doc.id)
    ).first():
        raise HTTPException(status_code=403, detail="Owners can view finalized and approved documents only")
    if is_consultant_engineer(current_user) and doc.task_id:
        scoped = _consultant_document_scope(db.query(Document), db, current_user, doc.project_id).filter(Document.id == doc.id).first()
        if not scoped:
            raise HTTPException(status_code=403, detail="This document is outside your discipline")
    return doc

@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    title: str = Form(...),
    document_type: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        proj_uuid = uuid.UUID(project_id)
        task_uuid = uuid.UUID(task_id) if task_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid projectId or taskId")
    require(db, current_user, "document.upload", proj_uuid)
    if current_user.role == UserRole.ENGINEER and not is_main_contractor_engineer(current_user):
        raise HTTPException(status_code=403, detail="Consultant review files must be uploaded as review attachments")
    
    if not user_has_project_access(db, current_user, proj_uuid):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    task = db.query(Task).filter(Task.id == task_uuid, Task.project_id == proj_uuid).first() if task_uuid else None
    if task_uuid and not task:
        raise HTTPException(status_code=400, detail="taskId must belong to the selected project")
    if task and current_user.role == UserRole.ENGINEER and not any(
        assignee.id == current_user.id for assignee in task.assignees
    ):
        raise HTTPException(status_code=403, detail="You can only attach documents to a task assigned to you")
    file_url, file_size = await save_upload(file, "documents")
    try:
        doc_type = DocumentType((document_type or "other").lower())
    except ValueError:
        delete_upload(file_url)
        raise HTTPException(status_code=400, detail="Unsupported documentType")
    
    new_doc = Document(
        project_id=proj_uuid,
        task_id=task_uuid,
        uploaded_by_id=current_user.id,
        title=title,
        document_type=doc_type,
        file_url=file_url,
        file_size_bytes=file_size,
        mime_type=file.content_type,
        version=1,
        notes=notes
    )
    
    db.add(new_doc)
    db.flush()
    project = db.get(Project, proj_uuid)
    recipients = {project.project_manager_id if project else None}
    if task:
        recipients.update(task.assignee_ids)
    for recipient in recipients - {None, current_user.id}:
        db.add(Notification(
            user_id=recipient,
            title="Document uploaded",
            message=f"{title} was uploaded to {project.name if project else 'the project'}.",
            type=NotificationType.SYSTEM,
            project_id=proj_uuid,
            task_id=task_uuid,
            related_entity_type="DOCUMENT",
            related_entity_id=new_doc.id,
        ))
    record_audit(db, actor_id=current_user.id, action="document_uploaded", entity_type="task" if task_uuid else "document",
                 entity_id=task_uuid or new_doc.id, project_id=proj_uuid,
                 details={"document_id": new_doc.id, "title": title})
    db.commit()
    db.refresh(new_doc)
    return new_doc

@router.delete("/{document_id}")
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    project = db.get(Project, doc.project_id)
    if current_user.role != UserRole.ADMIN and current_user.id != doc.uploaded_by_id and (not project or project.project_manager_id != current_user.id):
        raise HTTPException(status_code=403, detail="You cannot delete this document")
    if current_user.role == UserRole.ENGINEER:
        if not is_main_contractor_engineer(current_user):
            raise HTTPException(status_code=403, detail="Active Main Contractor Engineer access required")
        if doc.task_id:
            task = db.get(Task, doc.task_id)
            if not task or not any(assignee.id == current_user.id for assignee in task.assignees):
                raise HTTPException(status_code=403, detail="This document is outside your assigned work")
            if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE}:
                raise HTTPException(status_code=403, detail="Submitted task evidence cannot be deleted")
    record_audit(db, actor_id=current_user.id, action="document_deleted", entity_type="document",
                 entity_id=doc.id, project_id=doc.project_id)
    delete_upload(doc.file_url)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}

@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not user_has_project_access(db, current_user, doc.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")
    if current_user.role == UserRole.OWNER and not _owner_document_scope(
        db.query(Document).filter(Document.id == doc.id)
    ).first():
        raise HTTPException(status_code=403, detail="Owners can download finalized and approved documents only")
    if is_consultant_engineer(current_user) and doc.task_id:
        scoped = _consultant_document_scope(db.query(Document), db, current_user, doc.project_id).filter(Document.id == doc.id).first()
        if not scoped:
            raise HTTPException(status_code=403, detail="This document is outside your discipline")
    return {"url": doc.file_url}
