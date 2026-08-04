"""IFC geometry artifacts and persistent AI insights.

Revision ID: d31a7c9e4f82
Revises: c30f4a6b8e71
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d31a7c9e4f82"
down_revision = "c30f4a6b8e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ifc_model_versions", sa.Column("geometry_storage_key", sa.String(500), nullable=True))
    op.add_column("ifc_model_versions", sa.Column("geometry_error", sa.Text(), nullable=True))
    op.add_column("ifc_model_versions", sa.Column("geometry_stats_json", postgresql.JSONB(), server_default="{}", nullable=False))
    op.add_column("ifc_model_versions", sa.Column("geometry_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "ai_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False), sa.Column("insight_type", sa.String(80), nullable=False),
        sa.Column("category", sa.String(50), nullable=False), sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False), sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False), sa.Column("potential_impact", sa.Text(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("affected_json", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("related_task_ids_json", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("related_issue_ids_json", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("related_evidence_ids_json", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("source_engine", sa.String(80), server_default="RULE_ENGINE", nullable=False),
        sa.Column("status", sa.String(30), server_default="NEW", nullable=False), sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_entity_type", sa.String(40), nullable=True), sa.Column("applied_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_ai_insight_fingerprint"),
    )
    op.create_index("ix_ai_insights_project_id", "ai_insights", ["project_id"])
    op.create_index("ix_ai_insights_model_revision_id", "ai_insights", ["model_revision_id"])
    op.create_index("ix_ai_insights_insight_type", "ai_insights", ["insight_type"])
    op.create_index("ix_ai_insights_category", "ai_insights", ["category"])
    op.create_index("ix_ai_insights_status", "ai_insights", ["status"])
    op.create_index("ix_ai_insights_severity", "ai_insights", ["severity"])
    op.create_index("ix_ai_insight_project_status_severity", "ai_insights", ["project_id", "status", "severity"])


def downgrade() -> None:
    op.drop_table("ai_insights")
    op.drop_column("ifc_model_versions", "geometry_generated_at")
    op.drop_column("ifc_model_versions", "geometry_stats_json")
    op.drop_column("ifc_model_versions", "geometry_error")
    op.drop_column("ifc_model_versions", "geometry_storage_key")
