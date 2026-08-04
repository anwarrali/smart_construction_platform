"""add deterministic voice action risk and evidence metadata

Revision ID: z27c0a5e2d46
Revises: y26b9f4d1c35
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "z27c0a5e2d46"
down_revision = "y26b9f4d1c35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "voice_action_drafts",
        sa.Column("risk_level", sa.String(20), server_default="LOW", nullable=False),
    )
    op.add_column(
        "voice_action_drafts",
        sa.Column(
            "required_evidence", postgresql.JSONB(), server_default="[]", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("voice_action_drafts", "required_evidence")
    op.drop_column("voice_action_drafts", "risk_level")
