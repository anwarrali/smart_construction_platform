"""complete issue workflow fields

Revision ID: j11e4c9a86f88
Revises: i10d3b8f75e77
"""
from alembic import op
import sqlalchemy as sa

revision = "j11e4c9a86f88"
down_revision = "i10d3b8f75e77"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("issues", sa.Column("category", sa.String(80), nullable=True))
    op.add_column("issues", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("issues", sa.Column("affects_schedule", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("issues", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_issues_category", "issues", ["category"])

def downgrade() -> None:
    op.drop_index("ix_issues_category", table_name="issues")
    for name in ("resolved_at","affects_schedule","due_date","category"):
        op.drop_column("issues", name)
