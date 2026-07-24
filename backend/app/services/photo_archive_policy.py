"""Pure policy helpers for category normalization and archive query boundaries."""
from __future__ import annotations

import re
from datetime import date


SYSTEM_PHOTO_CATEGORIES = (
    "FOUNDATIONS", "STRUCTURAL", "MASONRY", "ARCHITECTURAL", "ELECTRICAL",
    "MECHANICAL", "PLUMBING", "HVAC", "FINISHING", "DOORS", "WINDOWS",
    "SAFETY", "EXCAVATION", "CONCRETE", "REINFORCEMENT", "OTHER",
)


def category_code(name: str) -> str:
    value = re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")
    if not value:
        raise ValueError("Category name must contain letters or numbers")
    return value[:80]


def category_belongs_to_project(category_project_id, project_id, is_system: bool) -> bool:
    return (is_system and category_project_id is None) or (
        not is_system and str(category_project_id) == str(project_id)
    )


def normalized_page(page: int, page_size: int) -> tuple[int, int, int]:
    safe_page = max(page, 1)
    safe_size = min(max(page_size, 1), 100)
    return safe_page, safe_size, (safe_page - 1) * safe_size


def archive_scope(role: str, *, is_consultant: bool = False) -> str:
    if role == "worker":
        return "OWN"
    if role == "engineer" and not is_consultant:
        return "ASSIGNED_TASKS"
    if is_consultant or role == "consultant":
        return "VERIFIED_ONLY"
    return "PROJECT"


def category_management_allowed(role: str, *, is_assigned_pm: bool) -> bool:
    return role == "admin" or (role == "project_manager" and is_assigned_pm)


def human_tagging_allowed(
    role: str, *, owns_submission: bool, submission_pending: bool,
    assigned_contractor_engineer: bool,
) -> bool:
    if role == "worker":
        return owns_submission and submission_pending
    return role == "engineer" and assigned_contractor_engineer


def matches_archive_filters(record: dict, *, project_id, **filters) -> bool:
    """Reference filter semantics used by unit tests and non-SQL consumers."""
    if str(record["project_id"]) != str(project_id):
        return False
    exact_fields = ("task_id", "uploader_id", "worker_id", "engineer_id", "status", "direction")
    for field in exact_fields:
        expected = filters.get(field)
        if expected and str(record.get(field)) != str(expected):
            return False
    if filters.get("discipline") and (
        (record.get("discipline") or "").casefold() != str(filters["discipline"]).casefold()
    ):
        return False
    if filters.get("category") and str(filters["category"]).casefold() not in {
        str(value).casefold() for value in record.get("categories", ())
    }:
        return False
    created = record.get("created_date")
    if isinstance(created, str):
        created = date.fromisoformat(created)
    if filters.get("date_from") and created < filters["date_from"]:
        return False
    if filters.get("date_to") and created > filters["date_to"]:
        return False
    search = str(filters.get("search") or "").strip().casefold()
    if search and search not in " ".join(str(value) for value in (
        record.get("task_code", ""), record.get("task_title", ""),
        record.get("discipline", ""), " ".join(record.get("categories", ())),
        record.get("filename", ""),
    )).casefold():
        return False
    return True


def paginate_records(records: list, page: int, page_size: int) -> tuple[list, int]:
    safe_page, safe_size, offset = normalized_page(page, page_size)
    return records[offset:offset + safe_size], safe_page
