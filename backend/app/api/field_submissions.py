from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, is_worker, user_has_project_access
from app.db.database import get_db
from app.models.attachment import Attachment
from app.models.enums import (
    EvidencePhotoDirection,
    FieldSubmissionStatus,
    NotificationType,
)
from app.models.field_submission import (
    FieldSubmission,
    FieldSubmissionPhoto,
    PhotoCategory,
    PhotoCategoryAssignment,
)
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.field_submission import (
    FieldSubmissionOut,
    FieldSubmissionRejection,
    FieldSubmissionReview,
    FieldSubmissionPhotoOut,
    FieldSubmissionVerifyAndApply,
)
from app.services.audit_service import record_audit
from app.services.field_submission_authorization import (
    authorized_engineer_ids,
    can_engineer_review_field_submission,
    can_view_field_submission,
    can_worker_submit_evidence,
)
from app.services.file_storage import delete_upload, save_upload
from app.services.field_submission_policy import AUDIT_ACTIONS
from app.services.photo_archive_policy import category_belongs_to_project
from app.services.task_progress_service import update_task_progress


router = APIRouter(prefix="/field-submissions", tags=["Field Evidence"])


def _submission_or_404(db: Session, submission_id: uuid.UUID) -> FieldSubmission:
    submission = db.get(FieldSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Field submission not found")
    return submission


def _notify(
    db: Session, user_id: uuid.UUID, submission: FieldSubmission, title: str, message: str
) -> None:
    db.add(Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=NotificationType.TASK_UPDATED,
        project_id=submission.project_id,
        task_id=submission.task_id,
        related_entity_type="FIELD_SUBMISSION",
        related_entity_id=submission.id,
    ))


def _directions(raw: str | None, count: int) -> list[EvidencePhotoDirection | None]:
    if not raw:
        return [None] * count
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) != count:
            raise ValueError
        return [
            EvidencePhotoDirection(value) if value else None
            for value in values
        ]
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=422,
            detail="Photo directions must be a JSON list matching the uploaded photos",
        )


def _photo_categories(
    db: Session, raw: str | None, count: int, project_id: uuid.UUID
) -> list[list[PhotoCategory]]:
    if not raw:
        return [[] for _ in range(count)]
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) != count:
            raise ValueError
        parsed_ids = [
            [uuid.UUID(value) for value in item]
            for item in values
            if isinstance(item, list)
        ]
        if len(parsed_ids) != count or any(len(item) > 20 for item in parsed_ids):
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=422,
            detail="Photo categories must be a JSON list of category-id lists matching the uploaded photos",
        )
    all_ids = set(category_id for item in parsed_ids for category_id in item)
    categories = db.query(PhotoCategory).filter(PhotoCategory.id.in_(all_ids)).all() if all_ids else []
    by_id = {category.id: category for category in categories}
    if len(by_id) != len(all_ids) or any(
        not category.active
        or not category_belongs_to_project(
            category.project_id, project_id, category.is_system
        )
        for category in categories
    ):
        raise HTTPException(
            status_code=422,
            detail="Every photo category must be active and available to this project",
        )
    return [[by_id[category_id] for category_id in item] for item in parsed_ids]


async def _add_photo(
    db: Session,
    submission: FieldSubmission,
    worker: User,
    file: UploadFile,
    direction: EvidencePhotoDirection | None,
    categories: list[PhotoCategory] | None = None,
) -> tuple[FieldSubmissionPhoto, str]:
    file_url, file_size = await save_upload(file, "field-evidence")
    attachment = Attachment(
        original_filename=file.filename or "field-photo",
        storage_key=PurePosixPath(file_url.split("/uploads/", 1)[-1]).as_posix(),
        file_url=file_url,
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=file_size,
        uploaded_by_id=worker.id,
        project_id=submission.project_id,
        entity_type="FIELD_SUBMISSION",
        entity_id=submission.id,
    )
    db.add(attachment)
    db.flush()
    photo = FieldSubmissionPhoto(
        field_submission_id=submission.id,
        attachment_id=attachment.id,
        direction=direction,
    )
    db.add(photo)
    db.flush()
    for category in categories or []:
        db.add(PhotoCategoryAssignment(
            field_submission_photo_id=photo.id,
            category_id=category.id,
            assigned_by_id=worker.id,
            source="HUMAN",
        ))
    return photo, file_url


@router.post("", response_model=FieldSubmissionOut, status_code=201)
async def create_field_submission(
    project_id: str = Form(...),
    task_id: str = Form(...),
    description: str | None = Form(default=None),
    voice_metadata: str | None = Form(default=None),
    resubmission_of_id: str | None = Form(default=None),
    directions: str | None = Form(default=None),
    photo_category_ids: str | None = Form(default=None),
    files: List[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        project_uuid, task_uuid = uuid.UUID(project_id), uuid.UUID(task_id)
        resubmission_uuid = uuid.UUID(resubmission_of_id) if resubmission_of_id else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project, task, or resubmission id")
    task = db.get(Task, task_uuid)
    if not task or task.project_id != project_uuid:
        raise HTTPException(status_code=404, detail="Assigned task not found in this project")
    if not can_worker_submit_evidence(db, current_user, task):
        raise HTTPException(status_code=403, detail="You cannot submit field evidence for this task")
    uploads = files or []
    note = (description or "").strip() or None
    if not note and not uploads:
        raise HTTPException(status_code=422, detail="Add a note or at least one field photo")
    parsed_directions = _directions(directions, len(uploads))
    parsed_categories = _photo_categories(
        db, photo_category_ids, len(uploads), project_uuid
    )
    previous = None
    if resubmission_uuid:
        previous = db.get(FieldSubmission, resubmission_uuid)
        if (
            not previous
            or previous.worker_id != current_user.id
            or previous.task_id != task.id
            or previous.status != FieldSubmissionStatus.REJECTED
        ):
            raise HTTPException(status_code=400, detail="Corrected evidence must reference your rejected submission")

    submission = FieldSubmission(
        project_id=project_uuid,
        task_id=task_uuid,
        worker_id=current_user.id,
        description=note,
        voice_metadata=voice_metadata,
        status=FieldSubmissionStatus.SUBMITTED,
        resubmission_of_id=previous.id if previous else None,
    )
    db.add(submission)
    db.flush()
    stored_urls: list[str] = []
    try:
        for file, direction, categories in zip(
            uploads, parsed_directions, parsed_categories
        ):
            _, file_url = await _add_photo(
                db, submission, current_user, file, direction, categories
            )
            stored_urls.append(file_url)
        engineer_ids = authorized_engineer_ids(db, task)
        project = db.get(Project, project_uuid)
        if not engineer_ids and project and project.project_manager_id:
            engineer_ids.add(project.project_manager_id)
        for engineer_id in engineer_ids:
            _notify(
                db, engineer_id, submission, "Worker evidence submitted",
                f"{current_user.full_name} submitted field evidence for {task.task_code}.",
            )
        record_audit(
            db, actor_id=current_user.id, action=AUDIT_ACTIONS["SUBMITTED"],
            entity_type="field_submission", entity_id=submission.id, project_id=project_uuid,
            details={"task_id": task.id, "photo_count": len(uploads),
                     "resubmission_of_id": submission.resubmission_of_id},
        )
        db.commit()
    except Exception:
        db.rollback()
        for file_url in stored_urls:
            delete_upload(file_url)
        raise
    db.refresh(submission)
    return submission


@router.post("/{submission_id}/photos", response_model=FieldSubmissionPhotoOut, status_code=201)
async def add_field_submission_photo(
    submission_id: uuid.UUID,
    file: UploadFile = File(...),
    direction: EvidencePhotoDirection | None = Form(default=None),
    category_ids: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = _submission_or_404(db, submission_id)
    if (
        not is_worker(current_user)
        or submission.worker_id != current_user.id
        or submission.status != FieldSubmissionStatus.SUBMITTED
        or not can_worker_submit_evidence(db, current_user, submission.task)
    ):
        raise HTTPException(status_code=403, detail="You cannot add photos to this submission")
    file_url = None
    try:
        categories = _photo_categories(
            db, f"[{category_ids}]" if category_ids else None, 1, submission.project_id
        )[0]
        photo, file_url = await _add_photo(
            db, submission, current_user, file, direction, categories
        )
        db.commit()
        db.refresh(photo)
        return photo
    except Exception:
        db.rollback()
        if file_url:
            delete_upload(file_url)
        raise


@router.get("/mine", response_model=list[FieldSubmissionOut])
def list_my_field_submissions(
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_worker(current_user):
        raise HTTPException(status_code=403, detail="Worker access required")
    query = db.query(FieldSubmission).filter(FieldSubmission.worker_id == current_user.id)
    if project_id:
        query = query.filter(FieldSubmission.project_id == project_id)
    if task_id:
        query = query.filter(FieldSubmission.task_id == task_id)
    return query.order_by(FieldSubmission.created_at.desc()).all()


@router.get("/pending", response_model=list[FieldSubmissionOut])
def list_pending_field_submissions(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    values = db.query(FieldSubmission).filter(
        FieldSubmission.project_id == project_id,
        FieldSubmission.status == FieldSubmissionStatus.SUBMITTED,
    ).order_by(FieldSubmission.created_at.asc()).all()
    return [
        item for item in values
        if can_engineer_review_field_submission(db, current_user, item)
    ]


@router.get("/task/{task_id}", response_model=list[FieldSubmissionOut])
def list_task_field_submissions(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    values = db.query(FieldSubmission).filter(
        FieldSubmission.task_id == task_id
    ).order_by(FieldSubmission.created_at.desc()).all()
    return [item for item in values if can_view_field_submission(db, current_user, item)]


@router.get("/worker-dashboard")
def worker_dashboard(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_worker(current_user):
        raise HTTPException(status_code=403, detail="Worker access required")
    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.assignees.any(User.id == current_user.id),
    ).all()
    submissions = db.query(FieldSubmission).filter(
        FieldSubmission.project_id == project_id,
        FieldSubmission.worker_id == current_user.id,
    ).all()
    return {
        "assignedTasks": len(tasks),
        "submittedEvidence": len(submissions),
        "verifiedEvidence": sum(item.status == FieldSubmissionStatus.VERIFIED for item in submissions),
        "rejectedEvidence": sum(item.status == FieldSubmissionStatus.REJECTED for item in submissions),
        "recentActivity": [
            {
                "action": f"Evidence {item.status.value.lower()}",
                "timestamp": item.updated_at.isoformat(),
            }
            for item in sorted(submissions, key=lambda value: value.updated_at, reverse=True)[:3]
        ],
    }


@router.get("/{submission_id}", response_model=FieldSubmissionOut)
def get_field_submission(
    submission_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = _submission_or_404(db, submission_id)
    if not can_view_field_submission(db, current_user, submission):
        raise HTTPException(status_code=403, detail="You cannot view this field submission")
    return submission


@router.put("/{submission_id}/verify", response_model=FieldSubmissionOut)
def verify_field_submission(
    submission_id: uuid.UUID,
    data: FieldSubmissionReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.query(FieldSubmission).filter(
        FieldSubmission.id == submission_id
    ).with_for_update().first()
    if not submission:
        raise HTTPException(status_code=404, detail="Field submission not found")
    if not can_engineer_review_field_submission(db, current_user, submission):
        raise HTTPException(status_code=403, detail="You cannot verify this field submission")
    if submission.status != FieldSubmissionStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="This field submission has already been reviewed")
    submission.status = FieldSubmissionStatus.VERIFIED
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by_id = current_user.id
    submission.review_comment = (data.comment or "").strip() or None
    _notify(
        db, submission.worker_id, submission, "Field evidence verified",
        f"Your evidence for {submission.task.task_code} was verified.",
    )
    record_audit(
        db, actor_id=current_user.id, action=AUDIT_ACTIONS["VERIFIED"],
        entity_type="field_submission", entity_id=submission.id,
        project_id=submission.project_id, details={"task_id": submission.task_id},
    )
    db.commit()
    db.refresh(submission)
    return submission


@router.put("/{submission_id}/verify-and-apply", response_model=FieldSubmissionOut)
def verify_and_apply_field_submission(
    submission_id: uuid.UUID,
    data: FieldSubmissionVerifyAndApply,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.query(FieldSubmission).filter(
        FieldSubmission.id == submission_id
    ).with_for_update().first()
    if not submission:
        raise HTTPException(status_code=404, detail="Field submission not found")
    if not can_engineer_review_field_submission(db, current_user, submission):
        raise HTTPException(status_code=403, detail="You cannot review this field submission")
    if submission.status != FieldSubmissionStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="This field submission has already been reviewed")
    task = db.query(Task).filter(Task.id == submission.task_id).with_for_update().first()
    expected = data.expected_task_updated_at
    current_updated = task.updated_at
    if current_updated.tzinfo is None and expected.tzinfo is not None:
        current_updated = current_updated.replace(tzinfo=expected.tzinfo)
    if current_updated != expected:
        raise HTTPException(
            status_code=409,
            detail="Task changed after this comparison was shown. Refresh and confirm again.",
        )
    current_progress = float(task.progress_percentage or 0)
    if data.progress_percentage < current_progress and not data.correction_confirmed:
        raise HTTPException(
            status_code=409,
            detail="A progress decrease requires explicit correction confirmation",
        )
    update_task_progress(
        db=db,
        current_user=current_user,
        task_id=task.id,
        progress_percentage=data.progress_percentage,
        note=data.comment,
        source="worker_voice_evidence_review",
        audit_metadata={"field_submission_id": str(submission.id)},
        commit=False,
    )
    submission.status = FieldSubmissionStatus.VERIFIED
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by_id = current_user.id
    submission.review_comment = (data.comment or "").strip() or (
        f"Evidence verified and official progress updated to {data.progress_percentage:g}%."
    )
    _notify(
        db,
        submission.worker_id,
        submission,
        "Field evidence verified",
        f"Your evidence for {submission.task.task_code} was verified by the Engineer.",
    )
    record_audit(
        db,
        actor_id=current_user.id,
        action="field_submission_verified_and_update_applied",
        entity_type="field_submission",
        entity_id=submission.id,
        project_id=submission.project_id,
        details={
            "task_id": submission.task_id,
            "previous_progress": current_progress,
            "progress": data.progress_percentage,
        },
    )
    db.commit()
    db.refresh(submission)
    return submission


@router.put("/{submission_id}/reject", response_model=FieldSubmissionOut)
def reject_field_submission(
    submission_id: uuid.UUID,
    data: FieldSubmissionRejection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    submission = db.query(FieldSubmission).filter(
        FieldSubmission.id == submission_id
    ).with_for_update().first()
    if not submission:
        raise HTTPException(status_code=404, detail="Field submission not found")
    if not can_engineer_review_field_submission(db, current_user, submission):
        raise HTTPException(status_code=403, detail="You cannot reject this field submission")
    if submission.status != FieldSubmissionStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="This field submission has already been reviewed")
    reason = data.reason.strip()
    submission.status = FieldSubmissionStatus.REJECTED
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.reviewed_by_id = current_user.id
    submission.review_comment = reason
    _notify(
        db, submission.worker_id, submission, "Field evidence needs correction",
        f"Evidence for {submission.task.task_code} was rejected: {reason}",
    )
    record_audit(
        db, actor_id=current_user.id, action=AUDIT_ACTIONS["REJECTED"],
        entity_type="field_submission", entity_id=submission.id,
        project_id=submission.project_id,
        details={"task_id": submission.task_id, "reason": reason},
    )
    from app.services.ai_traceability_service import invalidate_insights_for_source
    invalidate_insights_for_source(db, project_id=submission.project_id, source_type="FIELD_SUBMISSION",
                                   source_id=submission.id, reason=reason, rejected=True)
    db.commit()
    db.refresh(submission)
    return submission
