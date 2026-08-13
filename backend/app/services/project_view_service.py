"""Per-user project visit tracking behind the owner's "since your last visit" panel."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.project import ProjectViewState

# Only used the very first time a person opens a project, when there is no
# previous visit to compare against.
FIRST_VISIT_FALLBACK_DAYS = 7


def visit_boundary(state: ProjectViewState | None, *, now: datetime | None = None) -> tuple[datetime, bool]:
    """Return (since, is_first_visit) for the "what changed" window."""
    now = now or datetime.now(timezone.utc)
    if state and state.previous_viewed_at:
        return state.previous_viewed_at, False
    return now - timedelta(days=FIRST_VISIT_FALLBACK_DAYS), True


def record_visit(db: Session, *, user_id: uuid.UUID, project_id: uuid.UUID,
                 now: datetime | None = None) -> ProjectViewState:
    """Record that this user is looking at this project right now.

    The visit currently being served becomes `last_viewed_at`, and the one
    before it moves to `previous_viewed_at` — that is the boundary the next
    visit compares against, so a reload never wipes out the window.
    """
    now = now or datetime.now(timezone.utc)
    state = db.query(ProjectViewState).filter(
        ProjectViewState.user_id == user_id, ProjectViewState.project_id == project_id,
    ).first()
    if state:
        state.previous_viewed_at = state.last_viewed_at
        state.last_viewed_at = now
        state.view_count += 1
    else:
        state = ProjectViewState(user_id=user_id, project_id=project_id,
                                 last_viewed_at=now, previous_viewed_at=None, view_count=1)
        db.add(state)
    return state
