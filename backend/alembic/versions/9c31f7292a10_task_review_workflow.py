"""task review workflow

Revision ID: 9c31f7292a10
Revises: 8bb2a0d86e6d
Create Date: 2026-07-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9c31f7292a10"
down_revision: Union[str, None] = "8bb2a0d86e6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'REWORK_REQUIRED'")
    op.add_column("tasks", sa.Column("submitted_for_review_at", sa.Date(), nullable=True))
    op.add_column("tasks", sa.Column("reviewed_at", sa.Date(), nullable=True))
    op.add_column("tasks", sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tasks", sa.Column("consultant_comments", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("review_status", sa.String(length=30), nullable=True))
    op.create_foreign_key(
        "fk_tasks_reviewed_by_id_users",
        "tasks",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_reviewed_by_id_users", "tasks", type_="foreignkey")
    op.drop_column("tasks", "review_status")
    op.drop_column("tasks", "rejection_reason")
    op.drop_column("tasks", "consultant_comments")
    op.drop_column("tasks", "reviewed_by_id")
    op.drop_column("tasks", "reviewed_at")
    op.drop_column("tasks", "submitted_for_review_at")
