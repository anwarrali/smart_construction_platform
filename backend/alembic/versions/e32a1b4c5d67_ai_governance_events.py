"""AI action versions, domain events, and provider metrics.

Revision ID: e32a1b4c5d67
Revises: d31a7c9e4f82
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e32a1b4c5d67"
down_revision = "d31a7c9e4f82"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_action_versions",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voice_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reverted_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("intent", sa.String(80), nullable=False),
        sa.Column("original_input", sa.Text(), nullable=True),
        sa.Column("ai_interpretation", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("final_command", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("approval_info", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result", sa.String(30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(160), nullable=False),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("undo_policy", sa.String(40), server_default="MANUAL_REVIEW", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["voice_analysis_id"], ["voice_analyses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_action_id"], ["ai_action_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reverted_action_id"], ["ai_action_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_user_id", "request_id", name="uq_ai_action_actor_request"),
    )
    op.create_index("ix_ai_action_project_created", "ai_action_versions", ["project_id", "created_at"])
    op.create_index("ix_ai_action_entity_created", "ai_action_versions", ["entity_type", "entity_id", "created_at"])
    op.create_index("ix_ai_action_versions_actor_user_id", "ai_action_versions", ["actor_user_id"])
    op.create_index("ix_ai_action_versions_voice_analysis_id", "ai_action_versions", ["voice_analysis_id"])
    op.create_index("ix_ai_action_versions_reverted_action_id", "ai_action_versions", ["reverted_action_id"])
    op.create_index("ix_ai_action_versions_source", "ai_action_versions", ["source"])
    op.create_index("ix_ai_action_versions_intent", "ai_action_versions", ["intent"])
    op.create_index("ix_ai_action_versions_entity_type", "ai_action_versions", ["entity_type"])
    op.create_index("ix_ai_action_versions_entity_id", "ai_action_versions", ["entity_id"])
    op.create_index("ix_ai_action_versions_result", "ai_action_versions", ["result"])
    op.create_index("ix_ai_action_versions_correlation_id", "ai_action_versions", ["correlation_id"])

    op.create_table(
        "domain_events",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(30), server_default="PENDING", nullable=False),
        sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_domain_event_project_idempotency"),
    )
    op.create_index("ix_domain_event_status_created", "domain_events", ["status", "created_at"])
    op.create_index("ix_domain_events_project_id", "domain_events", ["project_id"])
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])
    op.create_index("ix_domain_events_entity_id", "domain_events", ["entity_id"])
    op.create_index("ix_domain_events_correlation_id", "domain_events", ["correlation_id"])

    op.create_table(
        "ai_provider_calls",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("voice_analysis_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["voice_analysis_id"], ["voice_analyses.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_provider_project_created", "ai_provider_calls", ["project_id", "created_at"])
    op.create_index("ix_ai_provider_calls_project_id", "ai_provider_calls", ["project_id"])
    op.create_index("ix_ai_provider_calls_voice_analysis_id", "ai_provider_calls", ["voice_analysis_id"])
    op.create_index("ix_ai_provider_calls_correlation_id", "ai_provider_calls", ["correlation_id"])
    op.create_index("ix_ai_provider_calls_reason", "ai_provider_calls", ["reason"])
    op.create_index("ix_ai_provider_calls_success", "ai_provider_calls", ["success"])


def downgrade():
    op.drop_table("ai_provider_calls")
    op.drop_table("domain_events")
    op.drop_table("ai_action_versions")
