from __future__ import annotations

import math
import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.deps import get_current_user, is_consultant_engineer, is_main_contractor_engineer, is_worker
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.enums import EvidencePhotoDirection, FieldSubmissionStatus, UserRole
from app.models.field_submission import (
    FieldSubmission,
    FieldSubmissionPhoto,
    PhotoCategory,
    PhotoCategoryAssignment,
)
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.field_submission import (
    EvidencePhotoArchiveItem,
    EvidencePhotoArchivePage,
    PhotoCategoryCreate,
    PhotoCategoryOut,
    PhotoCategoryReplace,
    PhotoCategoryUpdate,
)
from app.services.audit_service import record_audit
from app.services.field_submission_authorization import (
    can_categorize_field_photo,
    can_manage_project_photo_categories,
    can_view_project_photo_archive,
)
from app.services.photo_archive_policy import category_belongs_to_project, category_code, normalized_page


router = APIRouter(tags=["Evidence Photo Archive"])


def _project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _photo_query(db: Session):
    return db.query(FieldSubmissionPhoto).join(
        FieldSubmission, FieldSubmission.id == FieldSubmissionPhoto.field_submission_id
    ).join(Task, Task.id == FieldSubmission.task_id).join(
        Attachment, Attachment.id == FieldSubmissionPhoto.attachment_id
    )


def _scope_archive(query, current_user: User):
    if is_worker(current_user):
        return query.filter(FieldSubmission.worker_id == current_user.id)
    if is_main_contractor_engineer(current_user):
        return query.filter(Task.assignees.any(User.id == current_user.id))
    if is_consultant_engineer(current_user) or current_user.role == UserRole.CONSULTANT:
        return query.filter(FieldSubmission.status == FieldSubmissionStatus.VERIFIED)
    return query


def _archive_item(photo: FieldSubmissionPhoto) -> dict:
    submission = photo.submission
    attachment = photo.attachment
    return {
        "id": photo.id,
        "field_submission_id": submission.id,
        "project_id": submission.project_id,
        "task_id": submission.task_id,
        "task_code": submission.task.task_code,
        "task_title": submission.task.name,
        "discipline": submission.task.discipline,
        "worker_id": submission.worker_id,
        "worker_name": submission.worker.full_name,
        "uploader_id": attachment.uploaded_by_id,
        "uploader_name": attachment.uploaded_by.full_name,
        "submission_status": submission.status,
        "submission_created_at": submission.created_at,
        "reviewed_at": submission.reviewed_at,
        "reviewed_by_id": submission.reviewed_by_id,
        "reviewer_name": submission.reviewed_by.full_name if submission.reviewed_by else None,
        "direction": photo.direction,
        "categories": photo.categories,
        "attachment": attachment,
    }


@router.get(
    "/projects/{project_id}/photo-categories",
    response_model=list[PhotoCategoryOut],
)
def list_photo_categories(
    project_id: uuid.UUID,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _project_or_404(db, project_id)
    if not can_view_project_photo_archive(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You cannot access this project's evidence categories")
    query = db.query(PhotoCategory).filter(or_(
        PhotoCategory.project_id.is_(None),
        PhotoCategory.project_id == project_id,
    ))
    if not include_inactive:
        query = query.filter(PhotoCategory.active == True)
    return query.order_by(PhotoCategory.is_system.desc(), PhotoCategory.name.asc()).all()


@router.post(
    "/projects/{project_id}/photo-categories",
    response_model=PhotoCategoryOut,
    status_code=201,
)
def create_photo_category(
    project_id: uuid.UUID,
    data: PhotoCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _project_or_404(db, project_id)
    if not can_manage_project_photo_categories(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Only the Project Manager or Admin can manage categories")
    try:
        code = category_code(data.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    existing = db.query(PhotoCategory.id).filter(
        or_(
            PhotoCategory.project_id == project_id,
            PhotoCategory.project_id.is_(None),
        ),
        PhotoCategory.code == code,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A project category with this name already exists")
    category = PhotoCategory(
        name=data.name.strip(), code=code, project_id=project_id,
        is_system=False, active=True, created_by_id=current_user.id,
    )
    db.add(category)
    db.flush()
    record_audit(
        db, actor_id=current_user.id, action="photo_category_created",
        entity_type="photo_category", entity_id=category.id, project_id=project_id,
        details={"name": category.name, "code": category.code},
    )
    db.commit()
    db.refresh(category)
    return category


@router.patch(
    "/projects/{project_id}/photo-categories/{category_id}",
    response_model=PhotoCategoryOut,
)
def update_photo_category(
    project_id: uuid.UUID,
    category_id: uuid.UUID,
    data: PhotoCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage_project_photo_categories(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Only the Project Manager or Admin can manage categories")
    category = db.get(PhotoCategory, category_id)
    if not category or category.project_id != project_id:
        raise HTTPException(status_code=404, detail="Project category not found")
    if category.is_system:
        raise HTTPException(status_code=403, detail="System categories cannot be modified")
    previous_name = category.name
    if data.name is not None:
        try:
            next_code = category_code(data.name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        duplicate = db.query(PhotoCategory.id).filter(
            PhotoCategory.id != category.id,
            PhotoCategory.code == next_code,
            or_(
                PhotoCategory.project_id == project_id,
                PhotoCategory.project_id.is_(None),
            ),
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A category with this name already exists")
        category.name = data.name.strip()
        category.code = next_code
    if data.active is not None:
        category.active = data.active
    action = "photo_category_deactivated" if data.active is False else "photo_category_updated"
    record_audit(
        db, actor_id=current_user.id, action=action,
        entity_type="photo_category", entity_id=category.id, project_id=project_id,
        details={"previous_name": previous_name, "name": category.name, "active": category.active},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A project category with this name already exists")
    db.refresh(category)
    return category


@router.delete(
    "/projects/{project_id}/photo-categories/{category_id}",
    response_model=PhotoCategoryOut,
)
def deactivate_photo_category(
    project_id: uuid.UUID,
    category_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_photo_category(
        project_id, category_id, PhotoCategoryUpdate(active=False), db, current_user
    )


@router.put(
    "/field-submissions/photos/{photo_id}/categories",
    response_model=list[PhotoCategoryOut],
)
def replace_photo_categories(
    photo_id: uuid.UUID,
    data: PhotoCategoryReplace,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = db.query(FieldSubmissionPhoto).options(
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.task),
        selectinload(FieldSubmissionPhoto.category_assignments),
    ).filter(FieldSubmissionPhoto.id == photo_id).with_for_update().first()
    if not photo:
        raise HTTPException(status_code=404, detail="Evidence photo not found")
    if not can_categorize_field_photo(db, current_user, photo.submission):
        raise HTTPException(status_code=403, detail="You cannot categorize this evidence photo")
    category_ids = list(dict.fromkeys(data.category_ids))
    categories = db.query(PhotoCategory).filter(PhotoCategory.id.in_(category_ids)).all() if category_ids else []
    if len(categories) != len(category_ids) or any(
        not category.active
        or not category_belongs_to_project(
            category.project_id, photo.submission.project_id, category.is_system
        )
        for category in categories
    ):
        raise HTTPException(status_code=422, detail="Every category must be active and available to this project")
    photo.category_assignments.clear()
    db.flush()
    photo.category_assignments.extend([
        PhotoCategoryAssignment(
            category=category, assigned_by_id=current_user.id, source="HUMAN"
        )
        for category in categories
    ])
    record_audit(
        db, actor_id=current_user.id, action="evidence_photo_categories_updated",
        entity_type="field_submission_photo", entity_id=photo.id,
        project_id=photo.submission.project_id,
        details={"category_ids": category_ids},
    )
    db.commit()
    return categories


@router.get(
    "/projects/{project_id}/evidence-photos",
    response_model=EvidencePhotoArchivePage,
)
def list_evidence_photos(
    project_id: uuid.UUID,
    category: str | None = None,
    discipline: str | None = None,
    task_id: uuid.UUID | None = None,
    uploader_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    engineer_id: uuid.UUID | None = None,
    status: FieldSubmissionStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    direction: EvidencePhotoDirection | None = None,
    search: str | None = Query(default=None, max_length=120),
    page: int = 1,
    page_size: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _project_or_404(db, project_id)
    if not can_view_project_photo_archive(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You cannot access this project's evidence archive")
    query = _scope_archive(
        _photo_query(db).filter(FieldSubmission.project_id == project_id),
        current_user,
    )
    if category:
        category_term = category.strip()
        query = query.filter(FieldSubmissionPhoto.category_assignments.any(
            PhotoCategoryAssignment.category.has(or_(
                PhotoCategory.id == (
                    uuid.UUID(category_term) if _is_uuid(category_term) else uuid.UUID(int=0)
                ),
                PhotoCategory.code.ilike(category_term),
                PhotoCategory.name.ilike(category_term),
            ))
        ))
    if discipline:
        query = query.filter(Task.discipline.ilike(discipline.strip()))
    if task_id:
        query = query.filter(FieldSubmission.task_id == task_id)
    if uploader_id:
        query = query.filter(Attachment.uploaded_by_id == uploader_id)
    if worker_id:
        query = query.filter(FieldSubmission.worker_id == worker_id)
    if engineer_id:
        query = query.filter(FieldSubmission.reviewed_by_id == engineer_id)
    if status:
        query = query.filter(FieldSubmission.status == status)
    if date_from:
        query = query.filter(
            FieldSubmissionPhoto.created_at >= datetime.combine(date_from, time.min)
        )
    if date_to:
        query = query.filter(
            FieldSubmissionPhoto.created_at <= datetime.combine(date_to, time.max)
        )
    if direction:
        query = query.filter(FieldSubmissionPhoto.direction == direction)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            Task.name.ilike(term),
            Task.task_code.ilike(term),
            Task.discipline.ilike(term),
            Attachment.original_filename.ilike(term),
            FieldSubmission.description.ilike(term),
            FieldSubmissionPhoto.category_assignments.any(
                PhotoCategoryAssignment.category.has(or_(
                    PhotoCategory.name.ilike(term), PhotoCategory.code.ilike(term)
                ))
            ),
        ))
    safe_page, safe_size, offset = normalized_page(page, page_size)
    total = query.count()
    items = query.options(
        joinedload(FieldSubmissionPhoto.attachment).joinedload(Attachment.uploaded_by),
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.task),
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.worker),
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.reviewed_by),
        selectinload(FieldSubmissionPhoto.category_assignments).joinedload(
            PhotoCategoryAssignment.category
        ),
    ).order_by(FieldSubmissionPhoto.created_at.desc(), FieldSubmissionPhoto.id).offset(
        offset
    ).limit(safe_size).all()
    return {
        "items": [_archive_item(photo) for photo in items],
        "page": safe_page,
        "page_size": safe_size,
        "total": total,
        "total_pages": math.ceil(total / safe_size) if total else 0,
    }


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


@router.get(
    "/projects/{project_id}/evidence-photos/{photo_id}",
    response_model=EvidencePhotoArchiveItem,
)
def get_evidence_photo(
    project_id: uuid.UUID,
    photo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_view_project_photo_archive(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You cannot access this project's evidence archive")
    photo = _scope_archive(
        _photo_query(db).filter(
            FieldSubmission.project_id == project_id,
            FieldSubmissionPhoto.id == photo_id,
        ),
        current_user,
    ).options(
        joinedload(FieldSubmissionPhoto.attachment).joinedload(Attachment.uploaded_by),
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.task),
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.worker),
        joinedload(FieldSubmissionPhoto.submission).joinedload(FieldSubmission.reviewed_by),
        selectinload(FieldSubmissionPhoto.category_assignments).joinedload(
            PhotoCategoryAssignment.category
        ),
    ).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Evidence photo not found")
    return _archive_item(photo)
