"""durable AI voice analyses and confirmation provenance

Revision ID: x25a8e3c0b24
Revises: w24f7d2b9a13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "x25a8e3c0b24"
down_revision = "w24f7d2b9a13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    analysis_status = postgresql.ENUM(
        "UPLOADED", "TRANSCRIBING", "ANALYZING", "COMPLETED", "FAILED",
        name="voice_analysis_status", create_type=False,
    )
    confirmation_status = postgresql.ENUM(
        "PENDING", "PARTIALLY_CONFIRMED", "CONFIRMED",
        name="voice_confirmation_status", create_type=False,
    )
    analysis_status.create(op.get_bind(), checkfirst=True)
    confirmation_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "voice_analyses",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_submission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audio_attachment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("raw_transcript", sa.Text(), nullable=True),
        sa.Column("detected_language", sa.String(length=30), nullable=True),
        sa.Column("status", analysis_status, server_default="UPLOADED", nullable=False),
        sa.Column("structured_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmation_status", confirmation_status,
            server_default="PENDING", nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("retention_policy", sa.String(length=30), server_default="PRESERVE", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["audio_attachment_id"], ["attachments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["field_submission_id"], ["field_submissions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audio_attachment_id"),
    )
    op.create_index("ix_voice_analyses_project_id", "voice_analyses", ["project_id"])
    op.create_index("ix_voice_analyses_user_id", "voice_analyses", ["user_id"])
    op.create_index("ix_voice_analyses_task_id", "voice_analyses", ["task_id"])
    op.create_index("ix_voice_analyses_field_submission_id", "voice_analyses", ["field_submission_id"])
    op.create_index("ix_voice_analyses_status", "voice_analyses", ["status"])
    op.create_index("ix_voice_analyses_confirmation_status", "voice_analyses", ["confirmation_status"])
    op.create_index(
        "ix_voice_analyses_project_user_created",
        "voice_analyses", ["project_id", "user_id", "created_at"],
    )
    op.add_column(
        "site_reports",
        sa.Column("voice_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_site_reports_voice_analysis_id", "site_reports", "voice_analyses",
        ["voice_analysis_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_site_reports_voice_analysis_id", "site_reports", ["voice_analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_site_reports_voice_analysis_id", table_name="site_reports")
    op.drop_constraint("fk_site_reports_voice_analysis_id", "site_reports", type_="foreignkey")
    op.drop_column("site_reports", "voice_analysis_id")
    op.drop_index("ix_voice_analyses_project_user_created", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_confirmation_status", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_status", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_field_submission_id", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_task_id", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_user_id", table_name="voice_analyses")
    op.drop_index("ix_voice_analyses_project_id", table_name="voice_analyses")
    op.drop_table("voice_analyses")
    postgresql.ENUM(name="voice_confirmation_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="voice_analysis_status").drop(op.get_bind(), checkfirst=True)
