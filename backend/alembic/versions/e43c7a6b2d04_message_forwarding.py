"""message forwarding chain

Revision ID: e43c7a6b2d04
Revises: d32b6f5a1c93
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e43c7a6b2d04"
down_revision = "d32b6f5a1c93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("forwarded_from_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("messages", sa.Column("forward_origin_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_messages_forwarded_from_message", "messages", "messages",
        ["forwarded_from_message_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_messages_forward_origin_message", "messages", "messages",
        ["forward_origin_message_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_messages_forwarded_from_message_id", "messages", ["forwarded_from_message_id"])
    op.create_index("ix_messages_forward_origin_message_id", "messages", ["forward_origin_message_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_forward_origin_message_id", table_name="messages")
    op.drop_index("ix_messages_forwarded_from_message_id", table_name="messages")
    op.drop_constraint("fk_messages_forward_origin_message", "messages", type_="foreignkey")
    op.drop_constraint("fk_messages_forwarded_from_message", "messages", type_="foreignkey")
    op.drop_column("messages", "forward_origin_message_id")
    op.drop_column("messages", "forwarded_from_message_id")
