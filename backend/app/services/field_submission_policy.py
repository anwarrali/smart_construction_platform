"""Pure field-evidence rules, shared by authorization and tests.

These were written when field evidence was a worker's submission awaiting a
contractor engineer's check, and both halves of that sentence have changed.
Workers are no longer platform users, and the person recording what happened on
site is now normally a Site Engineer from the consulting office.

What has *not* changed is the shape of the workflow, and that is why these
functions survive rather than being deleted with the role: evidence is
submitted, and somebody other than the submitter confirms it. The rules below
just stopped naming who those people are — the caller resolves
`field_evidence.submit` and `field_evidence.verify` and passes the answer in.
"""
from __future__ import annotations


SUBMITTED = "SUBMITTED"
VERIFIED = "VERIFIED"
REJECTED = "REJECTED"
PHOTO_DIRECTIONS = {"FRONT", "BACK", "LEFT", "RIGHT", "TOP", "DETAIL", "OTHER"}
AUDIT_ACTIONS = {
    SUBMITTED: "field_evidence_submitted",
    VERIFIED: "field_evidence_verified",
    REJECTED: "field_evidence_rejected",
}


def evidence_submission_allowed(
    *,
    holds_permission: bool,
    active: bool,
    member_active: bool,
    member_project_id: str | None,
    task_project_id: str,
    assigned_to_task: bool,
    manages_work: bool = False,
) -> bool:
    """Whether this person may file evidence against this task.

    Membership of the task's own project is required in every case: holding
    `field_evidence.submit` says what somebody may do, never where.

    `manages_work` is the one widening. The retired rule demanded the submitter
    be assigned to the task, which was right for a worker recording their own
    output and wrong for a site engineer walking a whole floor — they are
    rarely an assignee of the tasks they observe. Somebody who may edit the
    project's work may therefore file against any of it; everyone else still
    files only against their own.
    """
    return (
        holds_permission
        and active
        and member_active
        and member_project_id == task_project_id
        and (assigned_to_task or manages_work)
    )


def evidence_review_allowed(
    *,
    holds_permission: bool,
    active: bool,
    member_active: bool,
    member_project_id: str | None,
    submission_project_id: str,
    assigned_to_task: bool,
    reviews_work: bool = False,
    reviewer_id: str,
    submitted_by_id: str,
) -> bool:
    """Whether this person may confirm or reject somebody else's evidence.

    `reviewer_id != submitted_by_id` is the rule worth keeping whatever else
    changes: evidence confirmed by the person who filed it is not evidence of
    anything. Every other condition is about reach — the right project, and
    either the specific task or authority over the project's work.
    """
    return (
        holds_permission
        and active
        and member_active
        and member_project_id == submission_project_id
        and (assigned_to_task or reviews_work)
        and reviewer_id != submitted_by_id
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
    event: str, reviewer_ids: set[str], submitted_by_id: str
) -> set[str]:
    return set(reviewer_ids) if event == SUBMITTED else {submitted_by_id}


def initial_status(verification_required: bool) -> str:
    """Where a new submission lands.

    A project can turn the second step off. The handshake exists because a
    worker's report of their own progress needed a qualified person to confirm
    it; when the qualified person is the one filing, an office may decide the
    report is the record and review happens at site-report level instead.
    Verification stays on by default, which is what every existing project has.
    """
    return SUBMITTED if verification_required else VERIFIED


def verification_preserves_official_task(
    task_status: str, progress: float, review_status: str | None
) -> tuple[str, float, str | None]:
    return task_status, progress, review_status
