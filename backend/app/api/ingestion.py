"""The unified file endpoint: one way in, per project, for every file type.

Five routes and no more. The temptation with a "unified" layer is a generic
file endpoint that any subsystem can call with any parameters, which is exactly
the shape that ends up bypassing the checks the specific endpoints make. So:

  * this router is **project-scoped in its prefix**, which makes project
    isolation structural rather than remembered;
  * it reuses the platform's existing permission codes — `document.upload` and
    `document.view` — rather than inventing a parallel authorization
    vocabulary that an administrator would have to configure twice;
  * an IFC file uploaded here additionally requires the IFC upload verb, so
    this endpoint can never be the cheap way around `can_ifc`;
  * it does **not** replace `/documents/upload` or the IFC version endpoint.
    Those carry domain meaning — a library entry, a model revision — that this
    layer deliberately does not have.

Nothing here returns a storage key, and every 4xx says only what the caller
already knows or needs. See `schemas/ingestion.py`.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.downloads import stored_file_response
from app.core.config import settings
from app.core.deps import get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.ingestion import IngestedFile
from app.models.user import User
from app.schemas.ingestion import (
    IngestedFileOut, IngestedFilePage, IngestionRetryOut, UploadConstraints,
)
from app.services.audit_service import record_audit
from app.services.authorization import require
from app.services.ingestion import pipeline, state
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.errors import public_error
from app.services.ingestion.validation import INGEST_CATEGORY, accepted_extensions, size_limit_for
from app.services.ifc_policy import can_ifc
from app.services.private_storage import private_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/files", tags=["File Ingestion"])

#: Downloads are streamed as an opaque octet stream regardless of what the file
#: turned out to be. Serving a caller-influenced content type is how a stored
#: HTML or SVG file becomes stored XSS on the API's own origin.
DOWNLOAD_MEDIA_TYPE = "application/octet-stream"

MAX_PAGE_SIZE = 200


def _feature_enabled() -> None:
    if not settings.INGESTION_ENABLED:
        raise HTTPException(status_code=503, detail="File ingestion is not enabled")


def _project_access(db: Session, user: User, project_id: uuid.UUID) -> None:
    """Project isolation, checked before anything else and on every route.

    Deliberately first: a permission check that runs before project access has
    already told the caller whether the project exists.
    """
    if not user_has_project_access(db, user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")


def _file_or_404(db: Session, project_id: uuid.UUID, file_id: uuid.UUID) -> IngestedFile:
    """A file, scoped to the project in the URL.

    The `project_id` filter is not redundant with the access check above: it is
    what stops a file id from one project being read through another project's
    route by somebody who is a member of both.
    """
    item = (
        db.query(IngestedFile)
        .filter(IngestedFile.id == file_id, IngestedFile.project_id == project_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="File not found")
    return item


def _serialize(item: IngestedFile) -> IngestedFileOut:
    payload = IngestedFileOut.model_validate(item)
    payload.error = public_error(item.error_code)
    return payload


@router.get("/upload-constraints", response_model=UploadConstraints)
def upload_constraints(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_enabled()
    _project_access(db, current_user, project_id)
    require(db, current_user, "document.view", project_id)
    limit = size_limit_for(INGEST_CATEGORY)
    return UploadConstraints(
        max_file_bytes=limit,
        max_file_mb=limit // (1024 * 1024),
        accepted_extensions=accepted_extensions(),
        max_package_entries=settings.INGESTION_ZIP_MAX_ENTRIES,
        max_package_total_bytes=settings.INGESTION_ZIP_MAX_TOTAL_MB * 1024 * 1024,
        max_package_depth=settings.INGESTION_ZIP_MAX_DEPTH,
        categories=[category.value for category in FileCategory],
    )


@router.post("", response_model=IngestedFileOut, status_code=202)
async def ingest_file(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload one file into the pipeline.

    202 rather than 201: with background processing on, the response describes
    a file that has been accepted and stored, not one that has been processed.
    The client watches `status`.
    """
    _feature_enabled()
    _project_access(db, current_user, project_id)
    require(db, current_user, "document.upload", project_id)

    item = await pipeline.register_upload(
        db, project_id=project_id, uploader_id=current_user.id, upload=file,
    )

    # The IFC gate is applied *after* classification, because "is this an IFC"
    # is a question about the bytes and not about the filename. The object is
    # removed on refusal, so a caller without the IFC permission cannot use
    # this endpoint to park a model in storage.
    if item.file_category == FileCategory.IFC.value and not can_ifc(
        db, current_user, project_id, "UPLOAD"
    ):
        db.expunge(item)
        private_storage.delete(item.storage_key)
        db.rollback()
        raise HTTPException(
            status_code=403, detail="IFC upload permission required for model files",
        )

    pipeline.dispatch(db, item)
    record_audit(
        db, actor_id=current_user.id, action="file_ingested", entity_type="ingested_file",
        entity_id=item.id, project_id=project_id,
        details={"category": item.file_category, "size": item.file_size_bytes,
                 "filename": item.original_filename},
    )
    db.commit()
    db.refresh(item)
    if settings.INGESTION_BACKGROUND_PROCESSING_ENABLED:
        # Queued only after the commit: a background session opens its own
        # transaction and would not see a row this one has not committed.
        background_tasks.add_task(pipeline.submit, item.id)
    return _serialize(item)


@router.get("", response_model=IngestedFilePage)
def list_files(
    project_id: uuid.UUID,
    category: str | None = None,
    status: str | None = None,
    parent_id: uuid.UUID | None = None,
    #: Absent means "top-level files only" is *not* implied — a project's file
    #: list shows everything by default, because a drawing that arrived inside
    #: a package is still a drawing somebody is looking for. `rootOnly` asks
    #: for the package view instead.
    root_only: bool = False,
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_enabled()
    _project_access(db, current_user, project_id)
    require(db, current_user, "document.view", project_id)

    query = db.query(IngestedFile).filter(IngestedFile.project_id == project_id)
    if category:
        query = query.filter(IngestedFile.file_category == category.strip().upper())
    if status:
        query = query.filter(IngestedFile.status == status.strip().upper())
    if parent_id:
        query = query.filter(IngestedFile.parent_file_id == parent_id)
    elif root_only:
        query = query.filter(IngestedFile.parent_file_id.is_(None))

    total = query.count()
    rows = (
        query.order_by(IngestedFile.created_at.desc())
        .offset(offset).limit(limit).all()
    )
    return IngestedFilePage(
        items=[_serialize(row) for row in rows], total=total, limit=limit, offset=offset,
    )


@router.get("/{file_id}", response_model=IngestedFileOut)
def get_file(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _feature_enabled()
    _project_access(db, current_user, project_id)
    require(db, current_user, "document.view", project_id)
    return _serialize(_file_or_404(db, project_id, file_id))


@router.get("/{file_id}/download")
def download_file(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream the stored object back.

    Downloading is reading, so it checks what reading checks and nothing less —
    the mistake the IFC and document download endpoints were both corrected for.
    An IFC file additionally requires the IFC download verb: the unified
    endpoint must not be a way around a permission the IFC workspace enforces.
    """
    _feature_enabled()
    _project_access(db, current_user, project_id)
    require(db, current_user, "document.view", project_id)
    item = _file_or_404(db, project_id, file_id)

    if item.file_category == FileCategory.IFC.value and not can_ifc(
        db, current_user, project_id, "DOWNLOAD"
    ):
        raise HTTPException(status_code=403, detail="IFC download permission required")

    if not private_storage.exists(item.storage_key):
        raise HTTPException(status_code=404, detail="Stored file is unavailable")

    record_audit(
        db, actor_id=current_user.id, action="file_downloaded", entity_type="ingested_file",
        entity_id=item.id, project_id=project_id,
    )
    db.commit()
    return stored_file_response(
        item.storage_key, filename=item.original_filename, media_type=DOWNLOAD_MEDIA_TYPE,
    )


@router.post("/{file_id}/retry", response_model=IngestionRetryOut, status_code=202)
def retry_file(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run processing on a file that failed or was only partly processed.

    `document.upload` rather than `document.view`: retrying consumes processing
    capacity on a shared bounded pool, which is a write-shaped action even
    though it changes no content.
    """
    _feature_enabled()
    _project_access(db, current_user, project_id)
    require(db, current_user, "document.upload", project_id)
    item = _file_or_404(db, project_id, file_id)

    if item.status not in state.SETTLED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="This file is still being processed; wait for it to settle before retrying",
        )

    pipeline.dispatch(db, item)
    record_audit(
        db, actor_id=current_user.id, action="file_reprocessed", entity_type="ingested_file",
        entity_id=item.id, project_id=project_id,
    )
    db.commit()
    db.refresh(item)
    queued = settings.INGESTION_BACKGROUND_PROCESSING_ENABLED
    if queued:
        background_tasks.add_task(pipeline.submit, item.id)
    return IngestionRetryOut(file=_serialize(item), queued=queued)
