"""message entity sharing (forward/consult on project entities)

Revision ID: f54d8b7c3e15
Revises: e43c7a6b2d04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f54d8b7c3e15"
down_revision = "e43c7a6b2d04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("shared_entity_type", sa.String(40), nullable=True))
    op.add_column("messages", sa.Column("shared_entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_messages_shared_entity_type", "messages", ["shared_entity_type"])
    op.create_index("ix_messages_shared_entity_id", "messages", ["shared_entity_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_shared_entity_id", table_name="messages")
    op.drop_index("ix_messages_shared_entity_type", table_name="messages")
    op.drop_column("messages", "shared_entity_id")
    op.drop_column("messages", "shared_entity_type")
