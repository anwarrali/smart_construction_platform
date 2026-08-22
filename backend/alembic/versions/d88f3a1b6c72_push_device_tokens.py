"""push notifications: per-device FCM registration tokens

Adds the `device_tokens` table, the `device_platform` enum, and
`notifications.read_at`.

One row per (user, device). The unique index on `token` is the load-bearing
constraint: an FCM registration token identifies exactly one app installation,
so allowing two rows for the same token would let a notification meant for one
account arrive on a device now signed in as somebody else.

Revision ID: d88f3a1b6c72
Revises: c87g2b4d0f69
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d88f3a1b6c72"
down_revision = "c87g2b4d0f69"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # No DDL for the new `NotificationChannel.PUSH` member, deliberately.
    # `NotificationChannel` is a Python-side enum only: no model column is
    # typed with it, so PostgreSQL has never had a `notification_channel`
    # type to alter. (Only `notification_type` and `notification_status` are
    # materialised.) An `ALTER TYPE` here fails with "type does not exist".
    #
    # If a column is ever typed with this enum, that migration will create the
    # type from the Python enum, PUSH included.

    device_platform = postgresql.ENUM(
        "ANDROID", "IOS", "WEB", name="device_platform", create_type=False
    )
    device_platform.create(bind, checkfirst=True)

    op.create_table(
        "device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(512), nullable=False),
        sa.Column("platform", device_platform, nullable=False),
        sa.Column("device_id", sa.String(200), nullable=True),
        sa.Column("device_name", sa.String(200), nullable=True),
        sa.Column("app_version", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("deactivated_reason", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])
    op.create_index("ix_device_tokens_user_active", "device_tokens", ["user_id", "is_active"])
    op.create_index("ix_device_tokens_token", "device_tokens", ["token"], unique=True)
    op.create_index("ix_device_tokens_device_id", "device_tokens", ["device_id"])

    # `is_read` alone cannot answer "how long did they sit on it", and
    # `updated_at` is touched by any write, so neither substitutes for this.
    # Existing rows keep NULL: back-dating a read time we never recorded would
    # be inventing history.
    op.add_column("notifications", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "read_at")
    op.drop_index("ix_device_tokens_device_id", table_name="device_tokens")
    op.drop_index("ix_device_tokens_token", table_name="device_tokens")
    op.drop_index("ix_device_tokens_user_active", table_name="device_tokens")
    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
    postgresql.ENUM(name="device_platform").drop(op.get_bind(), checkfirst=True)
