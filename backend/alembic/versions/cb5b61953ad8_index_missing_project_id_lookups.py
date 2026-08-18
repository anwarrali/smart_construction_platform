"""Index the project_id columns three hot query paths actually filter on.

A schema audit found four tables whose `project_id` foreign key had no
supporting index: `notifications`, `ifc_comparisons`, `ai_insight_sources`,
and `reminder_events`. Only the first three are ever filtered by
`project_id` in application code today — confirmed by grep, not guessed:

  * `notifications.project_id` — `list_notifications`, the unread-count
    endpoint, the dashboard summary, and the duplicate-notification check
    that runs on every notification write (`notification_service.py`).
  * `ifc_comparisons.project_id` — the comparison list/detail endpoints and
    the AI insight engine's revision-drift check.
  * `ai_insight_sources.project_id` — the insight-sources endpoint and the
    traceability service.

`reminder_events.project_id` is deliberately left alone: nothing in the
codebase queries it directly (every read goes through the existing
`(target_type, target_id, created_at)` index instead), so an index there
would be speculative rather than a fix for an observed gap.

Revision ID: cb5b61953ad8
Revises: cff92f4479c8
"""

from alembic import op

revision = "cb5b61953ad8"
down_revision = "cff92f4479c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_notifications_project_id", "notifications", ["project_id"])
    op.create_index("ix_ifc_comparisons_project_id", "ifc_comparisons", ["project_id"])
    op.create_index("ix_ai_insight_sources_project_id", "ai_insight_sources", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_insight_sources_project_id", table_name="ai_insight_sources")
    op.drop_index("ix_ifc_comparisons_project_id", table_name="ifc_comparisons")
    op.drop_index("ix_notifications_project_id", table_name="notifications")
