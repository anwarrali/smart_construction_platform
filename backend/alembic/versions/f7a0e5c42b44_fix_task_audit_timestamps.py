"""add audit timestamp defaults

Revision ID: f7a0e5c42b44
Revises: e6f9d4b31a33
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a0e5c42b44"
down_revision = "e6f9d4b31a33"
branch_labels = None
depends_on = None

def upgrade() -> None:
    for table in ("task_comments", "task_reviews"):
        op.alter_column(table, "created_at", server_default=sa.text("now()"))
        op.alter_column(table, "updated_at", server_default=sa.text("now()"))

def downgrade() -> None:
    for table in ("task_comments", "task_reviews"):
        op.alter_column(table, "created_at", server_default=None)
        op.alter_column(table, "updated_at", server_default=None)
