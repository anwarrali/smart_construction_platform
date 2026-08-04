"""Deterministic workflow policy. AI is never an approving actor."""

from datetime import datetime, time, timedelta


OWNER_REQUEST_TRANSITIONS = {
    "SUBMITTED": {"ASSIGNED", "UNDER_REVIEW", "NEEDS_CLARIFICATION", "REJECTED"},
    "ASSIGNED": {"UNDER_REVIEW", "NEEDS_CLARIFICATION", "ACCEPTED", "REJECTED"},
    "UNDER_REVIEW": {"NEEDS_CLARIFICATION", "ACCEPTED", "REJECTED", "CONVERTED_TO_DESIGN_CHANGE"},
    "NEEDS_CLARIFICATION": {"UNDER_REVIEW", "REJECTED"},
    "ACCEPTED": {"CONVERTED_TO_DESIGN_CHANGE", "COMPLETED"},
    "REJECTED": set(),
    "CONVERTED_TO_DESIGN_CHANGE": {"COMPLETED"},
    "COMPLETED": set(),
}


def can_transition_owner_request(current: str, target: str) -> bool:
    return target in OWNER_REQUEST_TRANSITIONS.get(current.upper(), set())


def choose_discipline_assignee(discipline: str | None, candidates: list[dict]):
    """Prefer an active exact project-discipline engineer; deterministic by id."""
    wanted = (discipline or "").strip().casefold()
    matches = [item for item in candidates if item.get("active", True) and item.get("role") == "engineer"
               and (item.get("discipline") or "").strip().casefold() == wanted]
    return sorted(matches, key=lambda item: str(item.get("id")))[0].get("id") if matches else None


def schedules_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def in_quiet_hours(at: datetime, start: time | None, end: time | None) -> bool:
    if start is None or end is None:
        return False
    local_time = at.timetz().replace(tzinfo=None)
    return start <= local_time < end if start < end else local_time >= start or local_time < end


def reminder_is_due(*, now: datetime, waiting_since: datetime, last_sent_at: datetime | None,
                    first_minutes: int, repeat_minutes: int, sent_count: int, maximum: int,
                    quiet_start: time | None = None, quiet_end: time | None = None) -> bool:
    if sent_count >= maximum or in_quiet_hours(now, quiet_start, quiet_end):
        return False
    threshold = waiting_since + timedelta(minutes=first_minutes) if not last_sent_at else last_sent_at + timedelta(minutes=repeat_minutes)
    return now >= threshold


def assert_human_authority(actor_type: str) -> bool:
    """Backend guard used by official-state workflows and voice execution."""
    return actor_type.upper() not in {"AI", "AI_ASSISTANT", "SYSTEM_AI", "LLM"}

