"""complete voice command workflow

Revision ID: y26b9f4d1c35
Revises: x25a8e3c0b24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "y26b9f4d1c35"
down_revision = "x25a8e3c0b24"
branch_labels = None
depends_on = None


NEW_STATES = (
    "TRANSCRIBED",
    "NEEDS_CLARIFICATION",
    "READY_FOR_CONFIRMATION",
    "CONFIRMED",
    "EXECUTING",
    "EXECUTED",
    "PARTIALLY_EXECUTED",
    "CANCELLED",
)


def upgrade() -> None:
    bind = op.get_bind()
    for value in NEW_STATES:
        # PostgreSQL enum values must be committed before subsequent statements
        # may use them. The migration only extends the enum; no rows are rewritten.
        with op.get_context().autocommit_block():
            op.execute(
                sa.text(f"ALTER TYPE voice_analysis_status ADD VALUE IF NOT EXISTS '{value}'")
            )

    op.add_column("voice_analyses", sa.Column("role_at_recording_time", sa.String(40)))
    op.add_column("voice_analyses", sa.Column("idempotency_key", sa.String(100)))
    op.add_column(
        "voice_analyses",
        sa.Column("row_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("voice_analyses", sa.Column("normalized_transcript", sa.Text()))
    op.create_unique_constraint(
        "uq_voice_analysis_user_idempotency",
        "voice_analyses",
        ["user_id", "idempotency_key"],
    )

    op.create_table(
        "voice_action_drafts",
        sa.Column("voice_analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_action_id", sa.String(80), nullable=False),
        sa.Column("action_type", sa.String(60), nullable=False),
        sa.Column("target_entity_type", sa.String(40)),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("extracted_payload", postgresql.JSONB(), nullable=False),
        sa.Column("user_edited_payload", postgresql.JSONB()),
        sa.Column("target_snapshot", postgresql.JSONB()),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("missing_fields", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("selected_for_execution", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("execution_status", sa.String(30), server_default="DRAFT", nullable=False),
        sa.Column("execution_error", sa.Text()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["voice_analysis_id"], ["voice_analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "voice_analysis_id", "client_action_id",
            name="uq_voice_action_draft_client_id",
        ),
    )
    op.create_index("ix_voice_action_drafts_voice_analysis_id", "voice_action_drafts", ["voice_analysis_id"])
    op.create_index("ix_voice_action_drafts_action_type", "voice_action_drafts", ["action_type"])
    op.create_index("ix_voice_action_drafts_target_entity_id", "voice_action_drafts", ["target_entity_id"])
    op.create_index("ix_voice_action_drafts_execution_status", "voice_action_drafts", ["execution_status"])

    op.create_table(
        "voice_clarifications",
        sa.Column("voice_analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voice_action_draft_id", postgresql.UUID(as_uuid=True)),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("field_path", sa.String(300), nullable=False),
        sa.Column("question_ar", sa.Text(), nullable=False),
        sa.Column("question_en", sa.Text(), nullable=False),
        sa.Column("expected_answer_type", sa.String(40), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("answer_text", sa.Text()),
        sa.Column("answer_audio_attachment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("answer_source", sa.String(20)),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["voice_analysis_id"], ["voice_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_action_draft_id"], ["voice_action_drafts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["answer_audio_attachment_id"], ["attachments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("voice_analysis_id", "sequence", name="uq_voice_clarification_sequence"),
    )
    op.create_index("ix_voice_clarifications_voice_analysis_id", "voice_clarifications", ["voice_analysis_id"])
    op.create_index("ix_voice_clarifications_voice_action_draft_id", "voice_clarifications", ["voice_action_draft_id"])

    op.create_table(
        "voice_execution_logs",
        sa.Column("voice_analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voice_action_draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(40)),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("before_state", postgresql.JSONB()),
        sa.Column("after_state", postgresql.JSONB()),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["voice_analysis_id"], ["voice_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voice_action_draft_id"], ["voice_action_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_voice_execution_logs_voice_analysis_id", "voice_execution_logs", ["voice_analysis_id"])
    op.create_index("ix_voice_execution_logs_voice_action_draft_id", "voice_execution_logs", ["voice_action_draft_id"])


def downgrade() -> None:
    op.drop_index("ix_voice_execution_logs_voice_action_draft_id", table_name="voice_execution_logs")
    op.drop_index("ix_voice_execution_logs_voice_analysis_id", table_name="voice_execution_logs")
    op.drop_table("voice_execution_logs")
    op.drop_index("ix_voice_clarifications_voice_action_draft_id", table_name="voice_clarifications")
    op.drop_index("ix_voice_clarifications_voice_analysis_id", table_name="voice_clarifications")
    op.drop_table("voice_clarifications")
    op.drop_index("ix_voice_action_drafts_execution_status", table_name="voice_action_drafts")
    op.drop_index("ix_voice_action_drafts_target_entity_id", table_name="voice_action_drafts")
    op.drop_index("ix_voice_action_drafts_action_type", table_name="voice_action_drafts")
    op.drop_index("ix_voice_action_drafts_voice_analysis_id", table_name="voice_action_drafts")
    op.drop_table("voice_action_drafts")
    op.drop_constraint("uq_voice_analysis_user_idempotency", "voice_analyses", type_="unique")
    op.drop_column("voice_analyses", "normalized_transcript")
    op.drop_column("voice_analyses", "row_version")
    op.drop_column("voice_analyses", "idempotency_key")
    op.drop_column("voice_analyses", "role_at_recording_time")
    # PostgreSQL cannot safely remove enum values without rebuilding the type.
    # The values remain dormant after the dependent schema is removed.
