"""Pure domain rules for Consultant approval assignment and workflow gates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


CENTRALIZED_REVIEW = "CENTRALIZED_REVIEW"
DISCIPLINE_BASED_REVIEW = "DISCIPLINE_BASED_REVIEW"


@dataclass(frozen=True)
class ReviewerAssignment:
    project_id: str
    user_id: str
    discipline: str | None


def normalize_discipline(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower().replace(" ", "_")
    return {
        "architect": "architectural",
        "architecture": "architectural",
        "structural": "civil",
        "structure": "civil",
        "plumbing": "mechanical",
        "hvac": "mechanical",
        "firefighting": "mechanical",
        "mep_mechanical": "mechanical",
        "mep_electrical": "electrical",
    }.get(normalized, normalized)


def assignment_allows_review(
    mode: str,
    assignments: Iterable[ReviewerAssignment],
    *,
    project_id: str,
    user_id: str,
    task_discipline: str | None,
) -> bool:
    relevant = [
        item for item in assignments
        if item.project_id == project_id and item.user_id == user_id
    ]
    if mode == CENTRALIZED_REVIEW:
        return any(item.discipline is None for item in relevant)
    discipline = normalize_discipline(task_discipline)
    return bool(discipline and any(
        normalize_discipline(item.discipline) == discipline for item in relevant
    ))


def rejected_work_can_be_resubmitted(task_status: str, review_status: str | None) -> bool:
    return task_status == "rework_required" and review_status == "rejected"


def dependency_approval_is_satisfied(
    task_status: str, review_required: bool, review_status: str | None
) -> bool:
    return task_status == "done" and (not review_required or review_status == "approved")
