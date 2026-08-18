"""add rejection reason to site reports

Revision ID: d32b6f5a1c93
Revises: cb5b61953ad8
"""
from alembic import op
import sqlalchemy as sa

revision = "d32b6f5a1c93"
down_revision = "cb5b61953ad8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_reports", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_reports", "rejection_reason")
