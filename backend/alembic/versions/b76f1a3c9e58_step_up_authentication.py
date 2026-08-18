"""step-up authentication: OTP challenges, step-up grants, rate limit counters

Revision ID: b76f1a3c9e58
Revises: a65e9c8d4b27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b76f1a3c9e58"
down_revision = "a65e9c8d4b27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_hits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_rate_limit_scope_key_created", "rate_limit_hits",
                    ["scope", "key", "created_at"])

    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(60), nullable=False),
        # HMAC-SHA256 digest of the code under the server secret — never the code.
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_reason", sa.String(40), nullable=True),
        sa.Column("delivery_channel", sa.String(20), nullable=False, server_default="EMAIL"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_otp_challenges_user_id", "otp_challenges", ["user_id"])
    op.create_index("ix_otp_challenges_user_purpose", "otp_challenges",
                    ["user_id", "purpose", "created_at"])

    op.create_table(
        "step_up_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(60), nullable=False),
        sa.Column("challenge_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("otp_challenges.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_step_up_grants_user_id", "step_up_grants", ["user_id"])
    op.create_index("ix_step_up_grants_user_purpose", "step_up_grants",
                    ["user_id", "purpose", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_step_up_grants_user_purpose", table_name="step_up_grants")
    op.drop_index("ix_step_up_grants_user_id", table_name="step_up_grants")
    op.drop_table("step_up_grants")
    op.drop_index("ix_otp_challenges_user_purpose", table_name="otp_challenges")
    op.drop_index("ix_otp_challenges_user_id", table_name="otp_challenges")
    op.drop_table("otp_challenges")
    op.drop_index("ix_rate_limit_scope_key_created", table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
