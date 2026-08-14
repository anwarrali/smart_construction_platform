"""Administrator-configurable permissions and consultant engineer scopes.

Additive only. No row is created here, so every role keeps exactly the
permissions it had before this migration ran; the tables only hold the
deviations an administrator later chooses to make.

Revision ID: ac30a8f5c921
Revises: ab29f7e4b810
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ac30a8f5c921"
down_revision = "ab29f7e4b810"
branch_labels = None
depends_on = None

USER_ROLE = postgresql.ENUM(name="user_role", create_type=False)


def upgrade() -> None:
    op.create_table(
        "role_permission_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role", USER_ROLE, nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("role", "permission_code", name="uq_role_permission_override"),
    )
    op.create_index("ix_role_permission_overrides_role", "role_permission_overrides", ["role"])
    op.create_index("ix_role_permission_overrides_permission_code", "role_permission_overrides", ["permission_code"])

    op.create_table(
        "user_permission_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "permission_code", "project_id", name="uq_user_permission_override"),
    )
    op.create_index("ix_user_permission_overrides_user_id", "user_permission_overrides", ["user_id"])
    op.create_index("ix_user_permission_overrides_project_id", "user_permission_overrides", ["project_id"])
    op.create_index("ix_user_permission_overrides_permission_code", "user_permission_overrides", ["permission_code"])
    op.create_index("ix_user_permission_lookup", "user_permission_overrides", ["user_id", "permission_code"])

    op.create_table(
        "consultant_engineer_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consultant_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engineer_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("project_id", "consultant_user_id", "engineer_user_id", name="uq_consultant_engineer_scope"),
    )
    op.create_index("ix_consultant_engineer_scopes_project_id", "consultant_engineer_scopes", ["project_id"])
    op.create_index("ix_consultant_engineer_scopes_consultant_user_id", "consultant_engineer_scopes", ["consultant_user_id"])
    op.create_index("ix_consultant_engineer_scopes_engineer_user_id", "consultant_engineer_scopes", ["engineer_user_id"])
    op.create_index("ix_consultant_scope_lookup", "consultant_engineer_scopes", ["project_id", "consultant_user_id"])


def downgrade() -> None:
    op.drop_table("consultant_engineer_scopes")
    op.drop_table("user_permission_overrides")
    op.drop_table("role_permission_overrides")
