"""persist revoked tokens

Revision ID: k12f5d0b97a99
Revises: j11e4c9a86f88
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "k12f5d0b97a99"
down_revision = "j11e4c9a86f88"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("revoked_tokens",
        sa.Column("token_hash",sa.String(128),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
        sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("token_hash"))
    op.create_index("ix_revoked_tokens_token_hash","revoked_tokens",["token_hash"],unique=True)
    op.create_index("ix_revoked_tokens_expires_at","revoked_tokens",["expires_at"])

def downgrade() -> None:
    op.drop_table("revoked_tokens")
