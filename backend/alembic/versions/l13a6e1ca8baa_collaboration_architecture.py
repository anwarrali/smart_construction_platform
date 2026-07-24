"""project assignments and contextual attachments

Revision ID: l13a6e1ca8baa
Revises: k12f5d0b97a99
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "l13a6e1ca8baa"
down_revision = "k12f5d0b97a99"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_members", sa.Column("assignment_title", sa.String(120), nullable=True))
    op.add_column("project_members", sa.Column("is_site_engineer", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("project_members", sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_project_members_assigned_by", "project_members", "users", ["assigned_by_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_project_members_is_site_engineer", "project_members", ["is_site_engineer"])

    op.add_column("notifications", sa.Column("related_entity_type", sa.String(50), nullable=True))
    op.add_column("notifications", sa.Column("related_entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_notifications_related_entity_type", "notifications", ["related_entity_type"])
    op.create_index("ix_notifications_related_entity_id", "notifications", ["related_entity_id"])

    op.create_table(
        "attachments",
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("file_url", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_attachments_project_id", "attachments", ["project_id"])
    op.create_index("ix_attachments_uploaded_by_id", "attachments", ["uploaded_by_id"])
    op.create_index("ix_attachments_entity_type", "attachments", ["entity_type"])
    op.create_index("ix_attachments_entity_id", "attachments", ["entity_id"])
    op.create_index("ix_attachments_context", "attachments", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("attachments")
    op.drop_index("ix_notifications_related_entity_id", table_name="notifications")
    op.drop_index("ix_notifications_related_entity_type", table_name="notifications")
    op.drop_column("notifications", "related_entity_id")
    op.drop_column("notifications", "related_entity_type")
    op.drop_index("ix_project_members_is_site_engineer", table_name="project_members")
    op.drop_constraint("fk_project_members_assigned_by", "project_members", type_="foreignkey")
    op.drop_column("project_members", "assigned_by_id")
    op.drop_column("project_members", "is_site_engineer")
    op.drop_column("project_members", "assignment_title")
