"""add task voice evidence policy

Revision ID: a28d1b6f3e57
Revises: z27c0a5e2d46
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a28d1b6f3e57"
down_revision = "z27c0a5e2d46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "voice_evidence_requirements",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "voice_evidence_requirements")
