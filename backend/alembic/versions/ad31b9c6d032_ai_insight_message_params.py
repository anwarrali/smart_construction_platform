"""Structured parameters so AI insights can be rendered in any language.

The English sentences already stored stay exactly where they are and remain the
fallback, so existing rows keep their meaning and nothing is rewritten. New rows
additionally carry the facts the sentence was built from, letting the client
compose the same statement in the reader's language.

Revision ID: ad31b9c6d032
Revises: ac30a8f5c921
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ad31b9c6d032"
down_revision = "ac30a8f5c921"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_insights",
        sa.Column("message_params_json", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("ai_insights", "message_params_json")
