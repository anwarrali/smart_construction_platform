"""Add persistent project-scoped task codes.

Revision ID: p17e0c5ad9f42
Revises: o16d9b4fc8e31
"""

from alembic import op
import sqlalchemy as sa


revision = "p17e0c5ad9f42"
down_revision = "o16d9b4fc8e31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("task_code_counter", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("tasks", sa.Column("task_code", sa.String(length=30), nullable=True))

    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY project_id
                       ORDER BY created_at, id
                   ) AS sequence_number
            FROM tasks
        )
        UPDATE tasks AS task
        SET task_code = 'TSK-' || LPAD(ranked.sequence_number::text, 3, '0')
        FROM ranked
        WHERE task.id = ranked.id
        """
    )
    op.execute(
        """
        UPDATE projects AS project
        SET task_code_counter = counts.task_count
        FROM (
            SELECT project_id, COUNT(*)::integer AS task_count
            FROM tasks
            GROUP BY project_id
        ) AS counts
        WHERE project.id = counts.project_id
        """
    )

    op.alter_column("tasks", "task_code", nullable=False)
    op.create_index("ix_tasks_task_code", "tasks", ["task_code"], unique=False)
    op.create_unique_constraint("uq_tasks_project_task_code", "tasks", ["project_id", "task_code"])


def downgrade() -> None:
    op.drop_constraint("uq_tasks_project_task_code", "tasks", type_="unique")
    op.drop_index("ix_tasks_task_code", table_name="tasks")
    op.drop_column("tasks", "task_code")
    op.drop_column("projects", "task_code_counter")
