"""A stable message key for AI insights.

`insight_type` identifies the specific finding and is part of the fingerprint,
so it varies with the subject (DISCIPLINE_ELECTRICAL_NOT_IN_IFC,
DISCIPLINE_PLUMBING_NOT_IN_IFC, ...). The message key names the *family* of
statement instead, which is what a translation catalogue can key on, with the
varying part supplied as a parameter.

Revision ID: ae32c1d7e043
Revises: ad31b9c6d032
"""

import sqlalchemy as sa
from alembic import op

revision = "ae32c1d7e043"
down_revision = "ad31b9c6d032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_insights", sa.Column("message_key", sa.String(length=80), nullable=True))
    # Existing rows keep their stored English sentence as the fallback.


def downgrade() -> None:
    op.drop_column("ai_insights", "message_key")
