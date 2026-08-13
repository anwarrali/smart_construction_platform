"""The owner's "what changed since I was last here" boundary.

A fixed recent-period window answers a different question than the one the
owner is asking, so the boundary must come from that owner's previous visit.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.project_view_service import (
    FIRST_VISIT_FALLBACK_DAYS,
    record_visit,
    visit_boundary,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


class FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._result


class FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    def query(self, *_args):
        return FakeQuery(self.existing)

    def add(self, item):
        self.added.append(item)


def test_first_ever_visit_falls_back_to_the_recent_period():
    since, first = visit_boundary(None, now=NOW)
    assert first is True
    assert since == NOW - timedelta(days=FIRST_VISIT_FALLBACK_DAYS)


def test_a_single_recorded_visit_still_has_no_previous_boundary():
    state = SimpleNamespace(last_viewed_at=NOW - timedelta(hours=2), previous_viewed_at=None)
    since, first = visit_boundary(state, now=NOW)
    assert first is True
    assert since == NOW - timedelta(days=FIRST_VISIT_FALLBACK_DAYS)


def test_the_boundary_is_the_owners_own_previous_visit():
    previous = NOW - timedelta(days=31)
    state = SimpleNamespace(last_viewed_at=NOW - timedelta(days=1), previous_viewed_at=previous)
    since, first = visit_boundary(state, now=NOW)
    assert first is False
    assert since == previous, "a month-old absence must not be reported as a 7-day window"


def test_the_first_visit_is_recorded_without_a_previous_boundary():
    session = FakeSession(existing=None)
    state = record_visit(session, user_id=uuid4(), project_id=uuid4(), now=NOW)
    assert session.added == [state]
    assert state.last_viewed_at == NOW
    assert state.previous_viewed_at is None
    assert state.view_count == 1


def test_a_later_visit_moves_the_old_timestamp_into_the_boundary():
    earlier = NOW - timedelta(days=10)
    existing = SimpleNamespace(last_viewed_at=earlier, previous_viewed_at=None, view_count=1)
    session = FakeSession(existing=existing)
    state = record_visit(session, user_id=uuid4(), project_id=uuid4(), now=NOW)
    assert state is existing
    assert session.added == [], "an existing visit row is updated, not duplicated"
    assert state.previous_viewed_at == earlier
    assert state.last_viewed_at == NOW
    assert state.view_count == 2


def test_reloading_the_dashboard_does_not_collapse_the_window_to_nothing():
    """A refresh must still show what changed since the visit before it."""
    first_open = NOW - timedelta(days=5)
    existing = SimpleNamespace(last_viewed_at=first_open, previous_viewed_at=None, view_count=1)
    session = FakeSession(existing=existing)

    record_visit(session, user_id=uuid4(), project_id=uuid4(), now=NOW)
    since, first = visit_boundary(existing, now=NOW)
    assert first is False
    assert since == first_open

    # Immediately reloading moves the boundary to this session, not to "now-0".
    record_visit(session, user_id=uuid4(), project_id=uuid4(), now=NOW + timedelta(seconds=5))
    since_after_reload, _ = visit_boundary(existing, now=NOW + timedelta(seconds=5))
    assert since_after_reload == NOW
