"""Add normalized milestones, task milestone links, and project messages.

Revision ID: r19a2e7c94b64
Revises: q18f1d6bea53
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "r19a2e7c94b64"
down_revision = "q18f1d6bea53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("milestone_code_counter", sa.Integer(), server_default="0", nullable=False))
    op.create_table(
        "milestones",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "milestone_code", name="uq_milestones_project_code"),
    )
    op.create_index("ix_milestones_project_id", "milestones", ["project_id"])
    op.create_index("ix_milestones_milestone_code", "milestones", ["milestone_code"])
    op.create_index("ix_milestones_planned_date", "milestones", ["planned_date"])
    op.add_column("tasks", sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_tasks_milestone_id", "tasks", "milestones", ["milestone_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_tasks_milestone_id", "tasks", ["milestone_id"])

    op.create_table(
        "messages",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receiver_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receiver_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("sender_id <> receiver_id", name="ck_messages_not_self"),
        sa.CheckConstraint("length(btrim(content)) > 0", name="ck_messages_content_not_blank"),
    )
    for column in ("project_id", "sender_id", "receiver_id", "is_read"):
        op.create_index(f"ix_messages_{column}", "messages", [column])
    op.create_index("ix_messages_conversation", "messages", ["project_id", "sender_id", "receiver_id", "created_at"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_index("ix_tasks_milestone_id", table_name="tasks")
    op.drop_constraint("fk_tasks_milestone_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "milestone_id")
    op.drop_table("milestones")
    op.drop_column("projects", "milestone_code_counter")
