"""consultant engineer review gates and traceable submissions

Revision ID: s20b3f8d05c75
Revises: r19a2e7c94b64
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "s20b3f8d05c75"
down_revision = "r19a2e7c94b64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Consultant Engineers use the unified Engineer role. Their project role
    # remains CONSULTANT so a membership explicitly grants review authority.
    op.execute("UPDATE users SET role = 'ENGINEER' WHERE role = 'CONSULTANT'")

    op.add_column("tasks", sa.Column("review_required", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("tasks", sa.Column("review_due_date", sa.Date(), nullable=True))
    op.create_index("ix_tasks_review_required", "tasks", ["review_required"])
    op.create_index("ix_tasks_review_due_date", "tasks", ["review_due_date"])

    op.add_column("task_reviews", sa.Column("submission_number", sa.Integer(), server_default="1", nullable=False))
    op.add_column("task_reviews", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_reviews", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_reviews", sa.Column("required_corrections", sa.Text(), nullable=True))
    op.add_column("task_reviews", sa.Column("completion_note", sa.Text(), nullable=True))
    op.add_column("task_reviews", sa.Column("clarification_question", sa.Text(), nullable=True))
    op.add_column("task_reviews", sa.Column("clarification_response", sa.Text(), nullable=True))
    op.add_column("task_reviews", sa.Column("clarification_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_reviews", sa.Column("clarification_responded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task_reviews", sa.Column("evidence_snapshot", sa.Text(), nullable=True))
    op.add_column("task_reviews", sa.Column("resubmission_of_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_task_reviews_resubmission_of", "task_reviews", "task_reviews",
        ["resubmission_of_id"], ["id"], ondelete="SET NULL",
    )
    op.execute("""
        WITH numbered AS (
            SELECT id, row_number() OVER (PARTITION BY task_id ORDER BY created_at, id) AS n
            FROM task_reviews
        )
        UPDATE task_reviews tr SET
            submission_number = numbered.n,
            submitted_at = COALESCE(tr.submitted_at, tr.created_at),
            reviewed_at = CASE WHEN tr.reviewed_by_id IS NOT NULL THEN COALESCE(tr.reviewed_at, tr.updated_at) ELSE tr.reviewed_at END
        FROM numbered WHERE numbered.id = tr.id
    """)
    op.create_index(
        "uq_task_reviews_one_active_submission",
        "task_reviews",
        ["task_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'in_review', 'clarification_requested')"),
    )


def downgrade() -> None:
    op.drop_index("uq_task_reviews_one_active_submission", table_name="task_reviews")
    op.drop_constraint("fk_task_reviews_resubmission_of", "task_reviews", type_="foreignkey")
    for column in (
        "resubmission_of_id", "evidence_snapshot", "clarification_responded_at",
        "clarification_requested_at", "clarification_response", "clarification_question",
        "completion_note", "required_corrections", "reviewed_at", "submitted_at",
        "submission_number",
    ):
        op.drop_column("task_reviews", column)
    op.drop_index("ix_tasks_review_due_date", table_name="tasks")
    op.drop_index("ix_tasks_review_required", table_name="tasks")
    op.drop_column("tasks", "review_due_date")
    op.drop_column("tasks", "review_required")
