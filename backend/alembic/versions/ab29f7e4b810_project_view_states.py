"""Per-user project view state for a real "since your last visit" window

Revision ID: ab29f7e4b810
Revises: aa28d1e6f3a7
Create Date: 2026-08-13

The owner dashboard previously reported changes over a fixed 7-day period,
which is not the same question as "what changed since I was last here".
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "ab29f7e4b810"
down_revision = "aa28d1e6f3a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_view_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "project_id", name="uq_project_view_state_user_project"),
    )
    op.create_index("ix_project_view_states_user_id", "project_view_states", ["user_id"])
    op.create_index("ix_project_view_states_project_id", "project_view_states", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_view_states_project_id", table_name="project_view_states")
    op.drop_index("ix_project_view_states_user_id", table_name="project_view_states")
    op.drop_table("project_view_states")
