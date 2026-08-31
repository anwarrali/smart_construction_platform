"""RBAC v2 expand: configurable roles, disciplines and external project parties

Expand step only. Everything added here is either a new table or a nullable
column, and nothing existing is dropped or narrowed, so this migration changes
no behaviour on its own: the legacy `user_role` enum columns keep working
exactly as before and remain the authority until the switch migration.

The one column that changes shape is `field_submissions.worker_id`, which is
*renamed* to `submitted_by_id`. A rename preserves every row and the foreign
key, so historical evidence stays attributable to the account that filed it —
which matters because those accounts are the worker accounts being retired.

Revision ID: c15a8d2e7f10
Revises: b14f7a2c9e63
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c15a8d2e7f10"
down_revision: Union[str, None] = "b14f7a2c9e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- the organization becomes a consulting office -----------------------
    op.add_column(
        "companies",
        sa.Column("kind", sa.String(length=30), nullable=False, server_default="OTHER"),
    )
    op.add_column(
        "companies",
        sa.Column("is_tenant", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "companies",
        sa.Column(
            "branding_json", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default="{}",
        ),
    )
    op.create_index("ix_companies_kind", "companies", ["kind"])
    op.create_index("ix_companies_is_tenant", "companies", ["is_tenant"])

    # --- roles --------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.Column("name_ar", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=10), nullable=False, server_default="BOTH"),
        sa.Column("is_internal_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("undeletable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("scope IN ('ORG','PROJECT','BOTH')", name="ck_roles_scope"),
    )
    op.create_index("ix_roles_organization_id", "roles", ["organization_id"])
    op.create_index("ix_roles_code", "roles", ["code"])
    op.create_index("ix_roles_is_internal_only", "roles", ["is_internal_only"])
    # Partial uniques: a global template is unique by code on its own, an
    # office's own role is unique by code within that office.
    op.create_index(
        "uq_roles_global_code", "roles", ["code"], unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_index(
        "uq_roles_org_code", "roles", ["organization_id", "code"], unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_code", sa.String(length=80), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_code", name="uq_role_permission"),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_code", "role_permissions", ["permission_code"])
    op.create_index("ix_role_permission_lookup", "role_permissions", ["role_id", "allowed"])

    # --- disciplines --------------------------------------------------------
    op.create_table(
        "disciplines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.Column("name_ar", sa.String(length=120), nullable=True),
        sa.Column(
            "ifc_disciplines", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default="[]",
        ),
        sa.Column("legacy_code", sa.String(length=40), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_disciplines_organization_id", "disciplines", ["organization_id"])
    op.create_index("ix_disciplines_code", "disciplines", ["code"])
    op.create_index("ix_disciplines_legacy_code", "disciplines", ["legacy_code"])
    op.create_index(
        "uq_disciplines_global_code", "disciplines", ["code"], unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_index(
        "uq_disciplines_org_code", "disciplines", ["organization_id", "code"], unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )

    op.create_table(
        "user_disciplines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discipline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discipline_id"], ["disciplines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "discipline_id", name="uq_user_discipline"),
    )
    op.create_index("ix_user_disciplines_user_id", "user_disciplines", ["user_id"])
    op.create_index("ix_user_disciplines_discipline_id", "user_disciplines", ["discipline_id"])

    # --- organization membership -------------------------------------------
    op.create_table(
        "organization_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("job_title", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_organization_membership"),
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index("ix_organization_memberships_organization_id", "organization_memberships", ["organization_id"])
    op.create_index("ix_organization_memberships_role_id", "organization_memberships", ["role_id"])
    op.create_index("ix_org_membership_lookup", "organization_memberships", ["user_id", "is_active"])

    # --- external parties on a project --------------------------------------
    op.create_table(
        "project_parties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("parent_party_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("contact_name", sa.String(length=150), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_party_id"], ["project_parties.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "display_name", "kind", name="uq_project_party_name"),
        sa.CheckConstraint(
            "kind IN ('CLIENT','MAIN_CONTRACTOR','SUBCONTRACTOR','CONSULTANT',"
            "'SUPPLIER','AUTHORITY','OTHER')",
            name="ck_project_party_kind",
        ),
    )
    op.create_index("ix_project_parties_project_id", "project_parties", ["project_id"])
    op.create_index("ix_project_parties_kind", "project_parties", ["kind"])
    op.create_index("ix_project_parties_parent_party_id", "project_parties", ["parent_party_id"])
    op.create_index("ix_project_party_project_kind", "project_parties", ["project_id", "kind"])

    op.create_table(
        "project_member_disciplines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discipline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_member_id"], ["project_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discipline_id"], ["disciplines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_member_id", "discipline_id", name="uq_project_member_discipline",
        ),
    )
    op.create_index(
        "ix_project_member_disciplines_member", "project_member_disciplines", ["project_member_id"],
    )
    op.create_index(
        "ix_project_member_disciplines_discipline", "project_member_disciplines", ["discipline_id"],
    )

    # --- explicit external document sharing ---------------------------------
    op.create_table(
        "document_party_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shared_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["party_id"], ["project_parties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "party_id", name="uq_document_party_share"),
    )
    op.create_index("ix_document_party_shares_document_id", "document_party_shares", ["document_id"])
    op.create_index("ix_document_party_shares_party_id", "document_party_shares", ["party_id"])
    op.create_index("ix_document_party_share_party", "document_party_shares", ["party_id", "document_id"])

    # --- columns on existing tables -----------------------------------------
    op.add_column("users", sa.Column("org_role_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_foreign_key(
        "fk_users_org_role_id", "users", "roles", ["org_role_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_users_org_role_id", "users", ["org_role_id"])
    op.create_index("ix_users_is_internal", "users", ["is_internal"])

    op.add_column(
        "project_members", sa.Column("project_role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "project_members", sa.Column("party_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_members_project_role_id", "project_members", "roles",
        ["project_role_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_project_members_party_id", "project_members", "project_parties",
        ["party_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_project_members_project_role_id", "project_members", ["project_role_id"])
    op.create_index("ix_project_members_party_id", "project_members", ["party_id"])

    op.add_column(
        "projects",
        sa.Column(
            "field_evidence_verification_required", sa.Boolean(),
            nullable=False, server_default=sa.true(),
        ),
    )

    op.add_column(
        "site_reports", sa.Column("discipline_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_site_reports_discipline_id", "site_reports", "disciplines",
        ["discipline_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_site_reports_discipline_id", "site_reports", ["discipline_id"])

    # --- field evidence author rename ---------------------------------------
    # A rename, not a new column: every existing row keeps its author, and the
    # foreign key (ON DELETE RESTRICT) travels with it.
    op.drop_index("ix_field_submissions_worker_created", table_name="field_submissions")
    op.alter_column("field_submissions", "worker_id", new_column_name="submitted_by_id")
    op.create_index(
        "ix_field_submissions_submitted_by_created",
        "field_submissions", ["submitted_by_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_field_submissions_submitted_by_created", table_name="field_submissions")
    op.alter_column("field_submissions", "submitted_by_id", new_column_name="worker_id")
    op.create_index(
        "ix_field_submissions_worker_created", "field_submissions", ["worker_id", "created_at"],
    )

    op.drop_index("ix_site_reports_discipline_id", table_name="site_reports")
    op.drop_constraint("fk_site_reports_discipline_id", "site_reports", type_="foreignkey")
    op.drop_column("site_reports", "discipline_id")

    op.drop_column("projects", "field_evidence_verification_required")

    op.drop_index("ix_project_members_party_id", table_name="project_members")
    op.drop_index("ix_project_members_project_role_id", table_name="project_members")
    op.drop_constraint("fk_project_members_party_id", "project_members", type_="foreignkey")
    op.drop_constraint("fk_project_members_project_role_id", "project_members", type_="foreignkey")
    op.drop_column("project_members", "party_id")
    op.drop_column("project_members", "project_role_id")

    op.drop_index("ix_users_is_internal", table_name="users")
    op.drop_index("ix_users_org_role_id", table_name="users")
    op.drop_constraint("fk_users_org_role_id", "users", type_="foreignkey")
    op.drop_column("users", "is_internal")
    op.drop_column("users", "org_role_id")

    op.drop_table("document_party_shares")
    op.drop_table("project_member_disciplines")
    op.drop_table("project_parties")
    op.drop_table("organization_memberships")
    op.drop_table("user_disciplines")
    op.drop_table("disciplines")
    op.drop_table("role_permissions")
    op.drop_table("roles")

    op.drop_index("ix_companies_is_tenant", table_name="companies")
    op.drop_index("ix_companies_kind", table_name="companies")
    op.drop_column("companies", "branding_json")
    op.drop_column("companies", "is_tenant")
    op.drop_column("companies", "kind")
