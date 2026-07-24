"""add audit logs

Revision ID: i10d3b8f75e77
Revises: h9c2a7e64d66
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "i10d3b8f75e77"
down_revision = "h9c2a7e64d66"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("audit_logs",
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(80), nullable=False), sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(80), nullable=False), sa.Column("details", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"],["users.id"],ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"],["projects.id"],ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    for column in ("actor_id","project_id","entity_type","entity_id","action"):
        op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])

def downgrade() -> None:
    op.drop_table("audit_logs")
