"""Replace the single task assignee with many-to-many task assignments.

Revision ID: q18f1d6bea53
Revises: p17e0c5ad9f42
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "q18f1d6bea53"
down_revision = "p17e0c5ad9f42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_assignees",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "user_id"),
        sa.UniqueConstraint("task_id", "user_id", name="uq_task_assignee_pair"),
    )
    op.create_index("ix_task_assignees_user_id", "task_assignees", ["user_id"], unique=False)
    op.execute(
        """
        INSERT INTO task_assignees (task_id, user_id, assigned_at)
        SELECT id, assignee_id, COALESCE(updated_at, created_at, now())
        FROM tasks
        WHERE assignee_id IS NOT NULL
        ON CONFLICT (task_id, user_id) DO NOTHING
        """
    )
    op.drop_index("ix_tasks_assignee_id", table_name="tasks")
    op.drop_constraint("tasks_assignee_id_fkey", "tasks", type_="foreignkey")
    op.drop_column("tasks", "assignee_id")


def downgrade() -> None:
    op.add_column("tasks", sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "tasks_assignee_id_fkey", "tasks", "users", ["assignee_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"], unique=False)
    op.execute(
        """
        UPDATE tasks AS task
        SET assignee_id = selected.user_id
        FROM (
            SELECT DISTINCT ON (task_id) task_id, user_id
            FROM task_assignees
            ORDER BY task_id, assigned_at, user_id
        ) AS selected
        WHERE task.id = selected.task_id
        """
    )
    op.drop_index("ix_task_assignees_user_id", table_name="task_assignees")
    op.drop_table("task_assignees")
