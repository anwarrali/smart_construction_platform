from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
import uuid

from app.db.database import get_db
from app.services.authorization import has_permission, require
from app.models.user import User
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.core.deps import get_current_user
from app.core.deps import user_has_project_access, accessible_project_ids
from app.services.document_access import (
    assert_document_readable, readable_document_ids, readable_document_ids_across,
    readable_documents_query,
)
from app.api.downloads import stored_file_response
from app.services.file_storage import delete_upload
from app.services.private_storage import private_storage
from app.models.enums import UserRole, DocumentType, TaskStatus, NotificationType
from app.models.project import Project
from app.models.task import Task
from app.models.notification import Notification
from app.services.audit_service import record_audit
from app.services.file_intelligence import (
    Classification, classify_document, identify_format, text_sample,
)
from pathlib import Path

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


# Every endpoint below narrows through `app.services.document_access`, which
# RAG retrieval and the AI tool layer also use. The role branches that used to
# be repeated here — Owner scope, consultant discipline scope — moved there
# with the redesign, together with the new external-party scope. Keeping one
# implementation is what stops the retrieval path (the one nobody audits) from
# granting access the download endpoint would refuse.

@router.get("", response_model=List[DocumentOut])
def list_documents(
    project_id: Optional[uuid.UUID] = None,
    document_type: Optional[DocumentType] = None,
    task_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if project_id and not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    if project_id:
        query = readable_documents_query(db, current_user, project_id)
    else:
        # Across every project this person can reach. `accessible_project_ids`
        # returns None for somebody who sees all projects, which for a document
        # list means "resolve each one on its own terms" rather than "no
        # filter" — a document's readability is a per-project question now.
        accessible_ids = accessible_project_ids(db, current_user)
        if accessible_ids is None:
            accessible_ids = [row[0] for row in db.query(Project.id).all()]
        readable_ids = readable_document_ids_across(db, current_user, accessible_ids)
        query = db.query(Document).filter(Document.id.in_(readable_ids))
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
    return readable_documents_query(db, current_user, project_id).all()

@router.get("/search", response_model=List[DocumentOut])
def search_documents(
    query: str,
    project_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if project_id:
        if not user_has_project_access(db, current_user, project_id):
            raise HTTPException(status_code=403, detail="You do not have access to this project")
        readable_ids = readable_document_ids(db, current_user, project_id)
    else:
        accessible_ids = accessible_project_ids(db, current_user)
        if accessible_ids is None:
            accessible_ids = [row[0] for row in db.query(Project.id).all()]
        readable_ids = readable_document_ids_across(db, current_user, accessible_ids)
    return (
        db.query(Document)
        .filter(
            Document.id.in_(readable_ids),
            Document.title.ilike(f"%{query}%") | Document.notes.ilike(f"%{query}%"),
        )
        .all()
    )

@router.get("/{document_id}", response_model=DocumentOut)
def get_document_by_id(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    assert_document_readable(db, current_user, doc)
    return doc

def _classify_upload(path: "Path", filename: str, declared: DocumentType) -> Classification | None:
    """Identify and classify a stored upload, or give up quietly.

    Never allowed to fail the upload. The file is already saved and the
    document row is about to be written; a classifier that could not read a
    PDF is a missing second opinion, not a reason to reject work a person has
    successfully submitted.

    Takes the path rather than the stored URL since documents moved to private
    storage: the caller already holds an open `private_storage.local_path`, and
    re-deriving a location from a URL is what tied this to the public tree.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(1024 * 1024)
        detected = identify_format(head, path.suffix.lower())
        return classify_document(
            filename=filename, content=head, extension=path.suffix.lower(),
            text_sample=text_sample(path, detected),
            declared_type=declared.name,
        )
    except Exception:
        logger.exception("[FileIntelligence] classification failed for %s", path)
        return None


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
    # `document.upload` is the whole decision. The affiliation check that used
    # to sit here refused consultant-side engineers outright; in the new model
    # the reviewing engineers are the office's own staff, and an office that
    # does not want a particular role uploading project documents takes the
    # permission away from that role instead.
    require(db, current_user, "document.upload", proj_uuid)

    if not user_has_project_access(db, current_user, proj_uuid):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    task = db.query(Task).filter(Task.id == task_uuid, Task.project_id == proj_uuid).first() if task_uuid else None
    if task_uuid and not task:
        raise HTTPException(status_code=400, detail="taskId must belong to the selected project")
    # Attaching to a task you are not on is still refused — but the rule is now
    # "you do not manage this project", not "you are an Engineer". A project
    # manager or administrator files against any task; everyone else files
    # against their own work.
    if task and not has_permission(db, current_user, "task.edit", proj_uuid) and not any(
        assignee.id == current_user.id for assignee in task.assignees
    ):
        raise HTTPException(status_code=403, detail="You can only attach documents to a task assigned to you")
    storage_key, file_size = await private_storage.save(file, "documents")
    try:
        doc_type = DocumentType((document_type or "other").lower())
    except ValueError:
        private_storage.delete(storage_key)
        raise HTTPException(status_code=400, detail="Unsupported documentType")

    with private_storage.local_path(storage_key) as stored_path:
        classification = _classify_upload(stored_path, file.filename or title, doc_type)

    new_doc = Document(
        project_id=proj_uuid,
        task_id=task_uuid,
        uploaded_by_id=current_user.id,
        title=title,
        document_type=doc_type,
        storage_key=storage_key,
        # Retained as an audit trail of where the row came from. It is no longer
        # a reachable location: `/uploads` no longer serves this category.
        file_url=f"private://{storage_key}",
        file_size_bytes=file_size,
        mime_type=file.content_type,
        version=1,
        notes=notes,
        detected_format=classification.detected_format if classification else None,
        suggested_document_type=classification.document_type if classification else None,
        classification_json=classification.as_json() if classification else {},
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
    # The Document Consistency Agent subscribes to this and had nothing to
    # listen to: the event type was declared but never emitted anywhere, so the
    # agent could only ever be run by hand.
    #
    # Emitted after the file is stored and classified, so a subscriber that
    # reads `indexStatus` or the classification is not racing the upload that
    # produced them.
    from app.services.domain_event_dispatcher import emit_domain_event
    emit_domain_event(
        db, project_id=proj_uuid, event_type="DOCUMENT_UPLOADED",
        entity_type="DOCUMENT", entity_id=new_doc.id, actor_user_id=current_user.id,
        payload={
            "title": new_doc.title,
            "documentType": new_doc.document_type.value,
            "detectedFormat": new_doc.detected_format,
            "taskId": str(task_uuid) if task_uuid else None,
        },
        correlation_id=f"document:{new_doc.id}",
        idempotency_key=f"DOCUMENT_UPLOADED:{new_doc.id}",
    )
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
    # Your own upload, the project's manager, or anybody the office trusted
    # with the project's documents. `document.share_external` is deliberately
    # not the code here — that governs who may hand a file outside; deleting
    # one is project setup, which `project.edit` names.
    if not (
        current_user.id == doc.uploaded_by_id
        or (project and project.project_manager_id == current_user.id)
        or has_permission(db, current_user, "project.edit", doc.project_id)
    ):
        raise HTTPException(status_code=403, detail="You cannot delete this document")
    # Evidence attached to work that has been submitted stays put, whoever
    # uploaded it. Keyed on managing the project rather than on a role name, so
    # the protection follows authority instead of job title.
    if doc.task_id and not has_permission(db, current_user, "task.edit", doc.project_id):
        task = db.get(Task, doc.task_id)
        if not task or not any(assignee.id == current_user.id for assignee in task.assignees):
            raise HTTPException(status_code=403, detail="This document is outside your assigned work")
        if task.status in {TaskStatus.UNDER_REVIEW, TaskStatus.DONE}:
            raise HTTPException(status_code=403, detail="Submitted task evidence cannot be deleted")
    record_audit(db, actor_id=current_user.id, action="document_deleted", entity_type="document",
                 entity_id=doc.id, project_id=doc.project_id)
    # Documents uploaded since the move live in private storage; rows that
    # predate it still point into the old public tree. Delete whichever one
    # this row actually has, so retiring the public path does not start
    # leaving orphaned bytes behind.
    if doc.storage_key:
        private_storage.delete(doc.storage_key)
    else:
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
    # Downloading is reading. Same rule, same helper — a download endpoint that
    # checked less than the read endpoint would be the bypass, and this one
    # used to carry its own copy of the scoping.
    assert_document_readable(db, current_user, doc)
    # This used to return `{"url": doc.file_url}` — a public `/uploads/...`
    # location served by an unauthenticated static mount. The check above ran
    # and then handed back a URL that did not need it, so the whole document
    # scope was advisory to anyone who had once seen the response. The bytes
    # are now streamed through the same authorization that reached this line.
    if not doc.storage_key:
        raise HTTPException(
            status_code=409,
            detail="This document predates secure storage and has not been migrated yet",
        )
    if not private_storage.exists(doc.storage_key):
        raise HTTPException(status_code=404, detail="Stored file is unavailable")
    return stored_file_response(
        doc.storage_key,
        filename=doc.title or "document",
        media_type=doc.mime_type or "application/octet-stream",
    )
