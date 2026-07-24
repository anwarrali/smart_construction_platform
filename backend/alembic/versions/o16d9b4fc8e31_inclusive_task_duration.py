"""Enforce inclusive calendar-day task durations.

Revision ID: o16d9b4fc8e31
Revises: n15c8a3eb7d20
"""

from alembic import op


revision = "o16d9b4fc8e31"
down_revision = "n15c8a3eb7d20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tasks
        SET duration_days = CASE
            WHEN planned_start_date IS NOT NULL AND planned_end_date IS NOT NULL
                THEN (planned_end_date - planned_start_date) + 1
            ELSE NULL
        END,
        is_critical_path = FALSE,
        total_float_days = NULL
        """
    )
    op.create_check_constraint(
        "ck_tasks_duration_days_positive",
        "tasks",
        "duration_days IS NULL OR duration_days >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tasks_duration_days_positive", "tasks", type_="check")
    op.execute(
        """
        UPDATE tasks
        SET duration_days = CASE
            WHEN planned_start_date IS NOT NULL AND planned_end_date IS NOT NULL
                THEN GREATEST(1, planned_end_date - planned_start_date)
            ELSE NULL
        END,
        is_critical_path = FALSE,
        total_float_days = NULL
        """
    )
