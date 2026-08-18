"""smart notifications: priority, deduplication key, localizable message, hot-path indexes

Revision ID: a65e9c8d4b27
Revises: f54d8b7c3e15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a65e9c8d4b27"
down_revision = "f54d8b7c3e15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("priority", sa.String(20), nullable=False, server_default="NORMAL"))
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(200), nullable=True))
    op.add_column("notifications", sa.Column("message_key", sa.String(80), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("message_params_json", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_notifications_priority", "notifications", ["priority"])
    # `list_notifications` (user + created_at DESC) and `unread-count`
    # (user + is_read) were both served only by the single-column user index;
    # `is_read` had no index at all.
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "is_read"])
    op.create_index("ix_notifications_user_dedupe", "notifications", ["user_id", "dedupe_key"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_dedupe", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_index("ix_notifications_priority", table_name="notifications")
    op.drop_column("notifications", "message_params_json")
    op.drop_column("notifications", "message_key")
    op.drop_column("notifications", "dedupe_key")
    op.drop_column("notifications", "priority")
