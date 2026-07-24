"""workers and field evidence submissions

Revision ID: u22d5b0f7e91
Revises: t21c4a9e6d80
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "u22d5b0f7e91"
down_revision = "t21c4a9e6d80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'WORKER'")

    submission_status = postgresql.ENUM(
        "SUBMITTED", "VERIFIED", "REJECTED",
        name="field_submission_status", create_type=False,
    )
    photo_direction = postgresql.ENUM(
        "FRONT", "BACK", "LEFT", "RIGHT", "TOP", "DETAIL", "OTHER",
        name="evidence_photo_direction", create_type=False,
    )
    submission_status.create(op.get_bind(), checkfirst=True)
    photo_direction.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "field_submissions",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("voice_metadata", sa.Text(), nullable=True),
        sa.Column(
            "status", submission_status,
            server_default="SUBMITTED", nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("resubmission_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["resubmission_of_id"], ["field_submissions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "task_id", "worker_id", "status"):
        op.create_index(f"ix_field_submissions_{column}", "field_submissions", [column])

    op.create_table(
        "field_submission_photos",
        sa.Column("field_submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", photo_direction, nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("ai_metadata", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["field_submission_id"], ["field_submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attachment_id", name="uq_field_submission_photo_attachment"),
    )
    op.create_index(
        "ix_field_submission_photos_field_submission_id",
        "field_submission_photos", ["field_submission_id"],
    )
    op.create_index(
        "ix_field_submission_photos_attachment_id",
        "field_submission_photos", ["attachment_id"],
    )
    op.create_index(
        "ix_field_submission_photos_category",
        "field_submission_photos", ["category"],
    )


def downgrade() -> None:
    op.drop_index("ix_field_submission_photos_category", table_name="field_submission_photos")
    op.drop_index("ix_field_submission_photos_attachment_id", table_name="field_submission_photos")
    op.drop_index("ix_field_submission_photos_field_submission_id", table_name="field_submission_photos")
    op.drop_table("field_submission_photos")
    for column in ("status", "worker_id", "task_id", "project_id"):
        op.drop_index(f"ix_field_submissions_{column}", table_name="field_submissions")
    op.drop_table("field_submissions")
    postgresql.ENUM(name="evidence_photo_direction").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="field_submission_status").drop(op.get_bind(), checkfirst=True)
    # PostgreSQL enum values cannot be removed safely in-place. WORKER remains
    # available in user_role after downgrade, matching prior enum migrations.
