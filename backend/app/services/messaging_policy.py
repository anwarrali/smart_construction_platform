"""Pure communication policies shared by authorization and regression tests."""
from __future__ import annotations


PROJECT_GROUPS = (
    "ALL_PROJECT_MEMBERS",
    "ALL_ENGINEERS",
    "CONTRACTOR_TEAM",
    "CONSULTANT_TEAM",
    "WORKERS",
    "PROJECT_MANAGERS",
    "OWNERS",
)


def can_project_broadcast(role: str) -> bool:
    return role in {"admin", "project_manager"}


def can_create_group(role: str) -> bool:
    return role in {"admin", "project_manager"}


def worker_can_message(*, target_is_project_manager: bool, target_is_assigned_engineer: bool) -> bool:
    return target_is_project_manager or target_is_assigned_engineer


def participants_belong_to_project(
    requested_ids: set[str], active_project_ids: set[str]
) -> bool:
    return requested_ids.issubset(active_project_ids)


def user_specific_unread(
    messages: list[dict], *, user_id: str, last_read_at
) -> int:
    return sum(
        1 for message in messages
        if str(message["sender_id"]) != str(user_id)
        and (last_read_at is None or message["created_at"] > last_read_at)
    )


def context_is_supported(context_type: str | None) -> bool:
    return context_type is None or context_type.upper() in {"TASK", "ISSUE"}


def conversation_search_visible(
    *, conversation_project_id, requested_project_id, is_participant: bool,
    contextual_access: bool = False,
) -> bool:
    return (
        str(conversation_project_id) == str(requested_project_id)
        and (is_participant or contextual_access)
    )


def resolve_group_records(group_code: str, members: list[dict]) -> set[str]:
    code = group_code.upper()
    if code == "ALL_PROJECT_MEMBERS":
        selected = members
    elif code == "CONTRACTOR_TEAM":
        selected = [
            item for item in members
            if item.get("role") in {"project_manager", "worker"}
            or item.get("affiliation") == "main_contractor"
        ]
    elif code == "CONSULTANT_TEAM":
        selected = [
            item for item in members
            if item.get("role") == "consultant"
            or item.get("affiliation") == "external_consultant"
        ]
    elif code == "ALL_ENGINEERS":
        selected = [item for item in members if item.get("role") == "engineer"]
    elif code.startswith("DISCIPLINE:"):
        discipline = code.split(":", 1)[1].casefold()
        selected = [
            item for item in members
            if str(item.get("discipline") or "").casefold() == discipline
        ]
    elif code == "WORKERS":
        selected = [item for item in members if item.get("role") == "worker"]
    else:
        selected = []
    return {str(item["id"]) for item in selected if item.get("active", True)}
