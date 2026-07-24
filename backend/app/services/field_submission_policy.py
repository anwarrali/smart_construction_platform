"""Pure Worker evidence rules shared by authorization and tests."""
from __future__ import annotations


SUBMITTED = "SUBMITTED"
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
PHOTO_DIRECTIONS = {"FRONT", "BACK", "LEFT", "RIGHT", "TOP", "DETAIL", "OTHER"}
AUDIT_ACTIONS = {
    SUBMITTED: "worker_evidence_submitted",
    VERIFIED: "worker_evidence_verified",
    REJECTED: "worker_evidence_rejected",
}


def worker_assignment_allows_submission(
    *,
    role: str,
    active: bool,
    member_role: str | None,
    member_active: bool,
    member_project_id: str | None,
    task_project_id: str,
    assigned_to_task: bool,
) -> bool:
    return (
        role == "worker"
        and active
        and member_role == "worker"
        and member_active
        and member_project_id == task_project_id
        and assigned_to_task
    )


def engineer_assignment_allows_review(
    *,
    role: str,
    affiliation: str | None,
    active: bool,
    member_role: str | None,
    member_active: bool,
    member_project_id: str | None,
    submission_project_id: str,
    assigned_to_task: bool,
    reviewer_id: str,
    worker_id: str,
) -> bool:
    return (
        role == "engineer"
        and affiliation == "main_contractor"
        and active
        and member_role == "engineer"
        and member_active
        and member_project_id == submission_project_id
        and assigned_to_task
        and reviewer_id != worker_id
    )


def validate_photo_directions(
    directions: list[str | None], photo_count: int
) -> list[str | None]:
    if len(directions) != photo_count:
        raise ValueError("Direction count must match photo count")
    if any(value is not None and value not in PHOTO_DIRECTIONS for value in directions):
        raise ValueError("Unsupported photo direction")
    return directions


def can_review_submission(current_status: str) -> bool:
    return current_status == SUBMITTED


def valid_rejection_reason(reason: str | None) -> bool:
    return bool(reason and len(reason.strip()) >= 3)


def notification_recipients(
    event: str, engineer_ids: set[str], worker_id: str
) -> set[str]:
    return set(engineer_ids) if event == SUBMITTED else {worker_id}


def verification_preserves_official_task(
    task_status: str, progress: float, review_status: str | None
) -> tuple[str, float, str | None]:
    return task_status, progress, review_status
