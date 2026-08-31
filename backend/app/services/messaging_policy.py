"""Pure communication policies shared by authorization and regression tests."""
from __future__ import annotations


PROJECT_GROUPS = (
    "ALL_PROJECT_MEMBERS",
    "ALL_ENGINEERS",
    "CONTRACTOR_TEAM",
    "CONSULTANT_TEAM",
    "PROJECT_MANAGERS",
    "OWNERS",
)


def can_project_broadcast(role: str) -> bool:
    return role in {"admin", "project_manager"}


def can_create_group(role: str) -> bool:
    return role in {"admin", "project_manager"}


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
    return context_type is None or context_type.upper() in {
        "PROJECT", "TASK", "ISSUE", "DESIGN_CHANGE", "DOCUMENT", "ROOM", "FLOOR",
        "IFC_ELEMENT", "SITE_REPORT", "APPROVAL", "FIELD_SUBMISSION", "OWNER_REQUEST", "SITE_VISIT",
    }


def conversation_search_visible(
    *, conversation_project_id, requested_project_id, is_participant: bool,
    contextual_access: bool = False,
) -> bool:
    return (
        str(conversation_project_id) == str(requested_project_id)
        and (is_participant or contextual_access)
    )


# `resolve_group_records` lived here and was removed. It resolved a broadcast
# group from role names and the retired `engineer_affiliation` — "contractor
# team" meant `project_manager | worker | main_contractor` — while the shipped
# resolution in `messaging_authorization.resolve_group_recipients` reads the
# project membership (`party_id is not None`) and `has_permission`. Nothing but
# its own tests called this copy, and a reference implementation that disagrees
# with the real one is a trap, not documentation.
