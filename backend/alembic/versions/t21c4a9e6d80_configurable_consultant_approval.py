"""configurable project Consultant approval workflow

Revision ID: t21c4a9e6d80
Revises: s20b3f8d05c75
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "t21c4a9e6d80"
down_revision = "s20b3f8d05c75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    approval_mode = postgresql.ENUM(
        "CENTRALIZED_REVIEW",
        "DISCIPLINE_BASED_REVIEW",
        name="consultant_approval_mode",
    )
    approval_mode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "projects",
        sa.Column(
            "consultant_approval_mode",
            approval_mode,
            server_default="DISCIPLINE_BASED_REVIEW",
            nullable=False,
        ),
    )
    op.create_table(
        "project_consultant_reviewers",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discipline", sa.String(length=50), nullable=True),
        sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "user_id", "discipline",
            name="uq_project_consultant_reviewer_assignment",
        ),
    )
    op.create_index(
        "ix_project_consultant_reviewers_project_id",
        "project_consultant_reviewers",
        ["project_id"],
    )
    op.create_index(
        "ix_project_consultant_reviewers_user_id",
        "project_consultant_reviewers",
        ["user_id"],
    )
    op.create_index(
        "ix_project_consultant_reviewers_discipline",
        "project_consultant_reviewers",
        ["discipline"],
    )
    op.create_index(
        "uq_project_consultant_reviewers_one_central",
        "project_consultant_reviewers",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("discipline IS NULL"),
    )

    # Existing behavior was discipline-based for every active Consultant
    # membership. Seed explicit assignments so upgrades do not revoke authority.
    op.execute("""
        INSERT INTO project_consultant_reviewers
            (id, project_id, user_id, discipline, assigned_by_id, created_at, updated_at)
        SELECT
            pm.id,
            pm.project_id,
            pm.user_id,
            CASE
                WHEN lower(COALESCE(pm.project_discipline, ep.discipline::text)) IN
                    ('architect', 'architecture', 'architectural') THEN 'architectural'
                WHEN lower(COALESCE(pm.project_discipline, ep.discipline::text)) IN
                    ('structural', 'structure', 'civil') THEN 'civil'
                WHEN lower(COALESCE(pm.project_discipline, ep.discipline::text)) IN
                    ('plumbing', 'hvac', 'firefighting', 'mep_mechanical', 'mechanical') THEN 'mechanical'
                WHEN lower(COALESCE(pm.project_discipline, ep.discipline::text)) IN
                    ('mep_electrical', 'electrical') THEN 'electrical'
                ELSE lower(COALESCE(pm.project_discipline, ep.discipline::text))
            END,
            pm.assigned_by_id,
            pm.created_at,
            pm.updated_at
        FROM project_members pm
        JOIN users u ON u.id = pm.user_id
        LEFT JOIN engineer_profiles ep ON ep.user_id = u.id
        WHERE pm.is_active = true
          AND pm.role_on_project = 'CONSULTANT'
          AND u.role = 'ENGINEER'
          AND u.engineer_affiliation = 'external_consultant'
          AND COALESCE(pm.project_discipline, ep.discipline::text) IS NOT NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index(
        "uq_project_consultant_reviewers_one_central",
        table_name="project_consultant_reviewers",
    )
    op.drop_index("ix_project_consultant_reviewers_discipline", table_name="project_consultant_reviewers")
    op.drop_index("ix_project_consultant_reviewers_user_id", table_name="project_consultant_reviewers")
    op.drop_index("ix_project_consultant_reviewers_project_id", table_name="project_consultant_reviewers")
    op.drop_table("project_consultant_reviewers")
    op.drop_column("projects", "consultant_approval_mode")
    postgresql.ENUM(name="consultant_approval_mode").drop(op.get_bind(), checkfirst=True)
