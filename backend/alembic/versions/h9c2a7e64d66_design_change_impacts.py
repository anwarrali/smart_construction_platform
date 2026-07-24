"""add design change impact fields

Revision ID: h9c2a7e64d66
Revises: g8b1f6d53c55
"""
from alembic import op
import sqlalchemy as sa

revision = "h9c2a7e64d66"
down_revision = "g8b1f6d53c55"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("design_changes", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("design_changes", sa.Column("related_drawings", sa.Text(), nullable=True))
    op.add_column("design_changes", sa.Column("expected_cost_impact", sa.Numeric(14,2), nullable=True))
    op.add_column("design_changes", sa.Column("expected_schedule_impact_days", sa.Integer(), nullable=True))
    op.add_column("design_changes", sa.Column("review_notes", sa.Text(), nullable=True))

def downgrade() -> None:
    for name in ("review_notes","expected_schedule_impact_days","expected_cost_impact","related_drawings","reason"):
        op.drop_column("design_changes", name)
