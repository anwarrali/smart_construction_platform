"""Add IFC version type and processing duration.

Revision ID: c30f4a6b8e71
Revises: b29e2c7d4f60
"""
from alembic import op
import sqlalchemy as sa

revision = "c30f4a6b8e71"
down_revision = "b29e2c7d4f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ifc_model_versions", sa.Column("version_type", sa.String(50), server_default="DESIGN", nullable=False))
    op.add_column("ifc_model_versions", sa.Column("processing_duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ifc_model_versions", "processing_duration_ms")
    op.drop_column("ifc_model_versions", "version_type")
