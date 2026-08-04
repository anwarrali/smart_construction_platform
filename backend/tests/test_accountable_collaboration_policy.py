from datetime import datetime, time, timedelta, timezone

from app.services.collaboration_policy import (
    assert_human_authority,
    can_transition_owner_request,
    choose_discipline_assignee,
    reminder_is_due,
    schedules_overlap,
)


def test_discipline_routing_selects_only_active_exact_engineer():
    candidates = [
        {"id": "z", "role": "engineer", "discipline": "electrical", "active": True},
        {"id": "a", "role": "worker", "discipline": "electrical", "active": True},
        {"id": "b", "role": "engineer", "discipline": "electrical", "active": False},
        {"id": "c", "role": "engineer", "discipline": "mechanical", "active": True},
    ]
    assert choose_discipline_assignee("Electrical", candidates) == "z"
    assert choose_discipline_assignee("architectural", candidates) is None


def test_owner_request_cannot_bypass_design_governance():
    assert can_transition_owner_request("UNDER_REVIEW", "ACCEPTED")
    assert can_transition_owner_request("UNDER_REVIEW", "CONVERTED_TO_DESIGN_CHANGE")
    assert not can_transition_owner_request("SUBMITTED", "COMPLETED")
    assert not can_transition_owner_request("REJECTED", "ACCEPTED")


def test_ai_never_has_official_approval_authority():
    assert assert_human_authority("HUMAN")
    assert not assert_human_authority("AI")
    assert not assert_human_authority("LLM")


def test_site_visit_conflict_uses_half_open_intervals():
    start = datetime(2026, 8, 5, 10, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    assert schedules_overlap(start, end, start + timedelta(minutes=30), end + timedelta(minutes=30))
    assert not schedules_overlap(start, end, end, end + timedelta(hours=1))


def test_reminders_stop_after_response_limit_and_respect_quiet_hours():
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    assert reminder_is_due(now=now, waiting_since=now - timedelta(hours=7), last_sent_at=None,
                           first_minutes=360, repeat_minutes=360, sent_count=0, maximum=3)
    assert not reminder_is_due(now=now, waiting_since=now - timedelta(days=2), last_sent_at=now - timedelta(days=1),
                               first_minutes=60, repeat_minutes=60, sent_count=3, maximum=3)
    assert not reminder_is_due(now=now, waiting_since=now - timedelta(days=2), last_sent_at=None,
                               first_minutes=60, repeat_minutes=60, sent_count=0, maximum=3,
                               quiet_start=time(11), quiet_end=time(13))

