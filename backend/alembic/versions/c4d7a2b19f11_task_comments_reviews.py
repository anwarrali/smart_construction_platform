"""persist task comments and review history

Revision ID: c4d7a2b19f11
Revises: 9c31f7292a10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c4d7a2b19f11"
down_revision = "9c31f7292a10"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("cost_validations", sa.Column("certified_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("cost_validations", sa.Column("planned_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("cost_validations", sa.Column("previously_paid", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("cost_validations", sa.Column("cost_variance_percentage", sa.Numeric(8, 2), nullable=True))
    op.add_column("tasks", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_tasks_sort_order", "tasks", ["sort_order"])
    op.create_table("task_comments",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_task_comments_task_id", "task_comments", ["task_id"])
    op.create_index("ix_task_comments_author_id", "task_comments", ["author_id"])
    op.create_table("task_reviews",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_task_reviews_task_id", "task_reviews", ["task_id"])
    op.create_index("ix_task_reviews_status", "task_reviews", ["status"])

def downgrade() -> None:
    op.drop_table("task_reviews")
    op.drop_table("task_comments")
    op.drop_index("ix_tasks_sort_order", table_name="tasks")
    op.drop_column("tasks", "sort_order")
    op.drop_column("cost_validations", "cost_variance_percentage")
    op.drop_column("cost_validations", "previously_paid")
    op.drop_column("cost_validations", "planned_amount")
    op.drop_column("cost_validations", "certified_amount")
