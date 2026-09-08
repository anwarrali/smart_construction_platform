"""Long-lived, project-scoped credentials for MCP clients

One additive table. Nothing existing is altered, and no data moves.

## Why a table and not a longer-lived JWT

The MCP surface authenticates with the platform's own access token, which lives
for minutes. A desktop MCP client runs for weeks and has no browser to refresh
through, so the alternatives were to hand it a refresh token — the user's whole
account — or to sign an access token with a 90-day expiry. The second cannot be
promptly revoked: a JWT is valid because it is signed, so taking one back means
carrying it in `revoked_tokens` until it expires anyway.

A row is looked up on every call, so revoking is one UPDATE that takes effect
on the next request. `revoked_at` rather than a delete, so the audit rows that
reference the token still point at something.

## The two indexes

`ix_mcp_client_tokens_hash` is unique and is the lookup on every MCP request —
unique because two rows sharing a secret would make "which credential is this"
unanswerable. `ix_mcp_client_tokens_user` covers the listing, which is always
one person's tokens ordered by age.

Both foreign keys cascade: a deleted user or project must not leave a live
credential behind pointing at nothing.

## Rollback

`downgrade()` drops the table. Every row is a credential, not project content —
losing them logs MCP clients out and costs nobody any work. The MCP endpoint
falls back to session tokens, which is where it was before this migration.

Revision ID: e71d5a3c9b42
Revises: d74ab3c6f92a
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e71d5a3c9b42"
down_revision = "d74ab3c6f92a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_client_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("scopes", sa.String(length=200), nullable=False,
                  server_default="mcp:read"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_mcp_client_tokens_hash", "mcp_client_tokens",
                    ["token_hash"], unique=True)
    op.create_index("ix_mcp_client_tokens_user", "mcp_client_tokens",
                    ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mcp_client_tokens_user", table_name="mcp_client_tokens")
    op.drop_index("ix_mcp_client_tokens_hash", table_name="mcp_client_tokens")
    op.drop_table("mcp_client_tokens")
