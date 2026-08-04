"""add project-scoped IFC intelligence and versioning

Revision ID: b29e2c7d4f60
Revises: a28d1b6f3e57
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b29e2c7d4f60"
down_revision = "a28d1b6f3e57"
branch_labels = None
depends_on = None

U = postgresql.UUID(as_uuid=True)
J = postgresql.JSONB()


def base_columns():
    return [
        sa.Column("id", U, primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("ifc_model_groups", *base_columns(),
        sa.Column("project_id", U, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("discipline", sa.String(50)),
        sa.Column("description", sa.Text()), sa.Column("active_version_id", U), sa.Column("baseline_version_id", U),
        sa.Column("created_by_id", U, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "name", name="uq_ifc_group_project_name"))
    op.create_index("ix_ifc_model_groups_project_id", "ifc_model_groups", ["project_id"])

    op.create_table("ifc_model_versions", *base_columns(),
        sa.Column("model_group_id", U, sa.ForeignKey("ifc_model_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", U, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("revision_code", sa.String(80)),
        sa.Column("title", sa.String(250), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("discipline", sa.String(50)), sa.Column("authoring_source", sa.String(120)),
        sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("file_hash", sa.String(64), nullable=False), sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("ifc_schema", sa.String(40)), sa.Column("authoring_application", sa.String(250)),
        sa.Column("source_created_at", sa.DateTime(timezone=True)), sa.Column("uploaded_by_id", U, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("issue_date", sa.Date()), sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_baseline", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("parent_version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="SET NULL")),
        sa.Column("processing_status", sa.String(40), server_default="UPLOADED", nullable=False),
        sa.Column("processing_progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parsing_error_code", sa.String(80)), sa.Column("parsing_error_message", sa.Text()), sa.Column("support_log_id", sa.String(40)),
        sa.Column("entity_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("geometry_status", sa.String(40), server_default="NOT_REQUESTED", nullable=False),
        sa.Column("analysis_status", sa.String(40), server_default="PENDING", nullable=False),
        sa.Column("model_summary_json", J, server_default="{}", nullable=False),
        sa.Column("asset_type_suggestion", sa.String(80)), sa.Column("asset_type_confidence", sa.Float()), sa.Column("asset_type_confirmed", sa.String(80)),
        sa.Column("row_version", sa.Integer(), server_default="1", nullable=False), sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("model_group_id", "version_number", name="uq_ifc_group_version_number"),
        sa.UniqueConstraint("project_id", "file_hash", name="uq_ifc_project_file_hash"))
    op.create_index("ix_ifc_version_project_status", "ifc_model_versions", ["project_id", "processing_status"])
    op.create_index("ix_ifc_model_versions_model_group_id", "ifc_model_versions", ["model_group_id"])

    op.create_table("ifc_spatial_nodes", *base_columns(),
        sa.Column("version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("global_id", sa.String(64), nullable=False), sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("name", sa.String(300), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("parent_id", U, sa.ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL")),
        sa.Column("node_type", sa.String(40), nullable=False), sa.Column("elevation", sa.Float()), sa.Column("area", sa.Float()), sa.Column("volume", sa.Float()),
        sa.Column("metadata_json", J, server_default="{}", nullable=False),
        sa.UniqueConstraint("version_id", "global_id", name="uq_ifc_spatial_version_global_id"))
    op.create_index("ix_ifc_spatial_version_type", "ifc_spatial_nodes", ["version_id", "node_type"])

    op.create_table("ifc_elements", *base_columns(),
        sa.Column("version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("global_id", sa.String(64), nullable=False), sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("name", sa.String(300), nullable=False), sa.Column("description", sa.Text()), sa.Column("object_type", sa.String(200)),
        sa.Column("predefined_type", sa.String(100)), sa.Column("tag", sa.String(120)),
        sa.Column("storey_node_id", U, sa.ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL")),
        sa.Column("space_node_id", U, sa.ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL")),
        sa.Column("zone_node_id", U, sa.ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL")),
        sa.Column("building_node_id", U, sa.ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL")),
        sa.Column("discipline", sa.String(50)), sa.Column("system_name", sa.String(250)), sa.Column("type_name", sa.String(250)), sa.Column("material_summary", sa.Text()),
        sa.Column("properties_json", J, server_default="{}", nullable=False), sa.Column("quantities_json", J, server_default="{}", nullable=False),
        sa.Column("bounding_box_json", J), sa.Column("geometry_reference", sa.String(500)), sa.Column("geometry_hash", sa.String(64)),
        sa.Column("placement_hash", sa.String(64)), sa.Column("metadata_json", J, server_default="{}", nullable=False),
        sa.UniqueConstraint("version_id", "global_id", name="uq_ifc_element_version_global_id"))
    op.create_index("ix_ifc_element_version_class", "ifc_elements", ["version_id", "entity_type"])
    op.create_index("ix_ifc_element_version_discipline", "ifc_elements", ["version_id", "discipline"])
    op.create_index("ix_ifc_element_version_storey", "ifc_elements", ["version_id", "storey_node_id"])
    op.create_index("ix_ifc_element_version_space", "ifc_elements", ["version_id", "space_node_id"])

    op.create_table("ifc_entity_links", *base_columns(),
        sa.Column("project_id", U, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ifc_element_id", U, sa.ForeignKey("ifc_elements.id", ondelete="CASCADE")),
        sa.Column("spatial_node_id", U, sa.ForeignKey("ifc_spatial_nodes.id", ondelete="CASCADE")),
        sa.Column("linked_entity_type", sa.String(40), nullable=False), sa.Column("linked_entity_id", U, nullable=False),
        sa.Column("link_type", sa.String(60), nullable=False), sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("source", sa.String(30), server_default="USER", nullable=False), sa.Column("confirmed_by_id", U, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("version_id", "ifc_element_id", "spatial_node_id", "linked_entity_type", "linked_entity_id", "link_type", name="uq_ifc_entity_link"))
    op.create_index("ix_ifc_link_project_target", "ifc_entity_links", ["project_id", "linked_entity_type", "linked_entity_id"])

    op.create_table("ifc_comparisons", *base_columns(),
        sa.Column("project_id", U, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(40), server_default="QUEUED", nullable=False), sa.Column("summary_json", J, server_default="{}", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_id", U, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False), sa.Column("error", sa.Text()),
        sa.UniqueConstraint("base_version_id", "target_version_id", name="uq_ifc_comparison_pair"))

    op.create_table("ifc_change_records", *base_columns(),
        sa.Column("comparison_id", U, sa.ForeignKey("ifc_comparisons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_element_id", U, sa.ForeignKey("ifc_elements.id", ondelete="SET NULL")), sa.Column("target_element_id", U, sa.ForeignKey("ifc_elements.id", ondelete="SET NULL")),
        sa.Column("change_type", sa.String(40), nullable=False), sa.Column("match_method", sa.String(40), nullable=False), sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.Column("property_changes_json", J, server_default="{}", nullable=False), sa.Column("geometry_change_json", J, server_default="{}", nullable=False),
        sa.Column("location_change_json", J, server_default="{}", nullable=False), sa.Column("severity", sa.String(20), server_default="LOW", nullable=False),
        sa.Column("discipline", sa.String(50)), sa.Column("storey", sa.String(250)), sa.Column("space", sa.String(250)))
    op.create_index("ix_ifc_change_comparison_type", "ifc_change_records", ["comparison_id", "change_type"])

    op.create_table("ifc_impact_suggestions", *base_columns(),
        sa.Column("comparison_id", U, sa.ForeignKey("ifc_comparisons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_record_id", U, sa.ForeignKey("ifc_change_records.id", ondelete="CASCADE")), sa.Column("impact_type", sa.String(50), nullable=False),
        sa.Column("affected_entity_type", sa.String(40), nullable=False), sa.Column("affected_entity_id", U, nullable=False),
        sa.Column("severity", sa.String(20), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence_json", J, server_default="{}", nullable=False), sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), server_default="PENDING", nullable=False), sa.Column("reviewed_by_id", U, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)))

    op.create_table("ifc_coordination_findings", *base_columns(),
        sa.Column("project_id", U, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comparison_id", U, sa.ForeignKey("ifc_comparisons.id", ondelete="SET NULL")),
        sa.Column("element_a_id", U, sa.ForeignKey("ifc_elements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("element_b_id", U, sa.ForeignKey("ifc_elements.id", ondelete="CASCADE")), sa.Column("finding_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False), sa.Column("title", sa.String(300), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("geometry_evidence_json", J, server_default="{}", nullable=False), sa.Column("affected_disciplines_json", J, server_default="[]", nullable=False),
        sa.Column("affected_tasks_json", J, server_default="[]", nullable=False), sa.Column("suggested_recipients_json", J, server_default="[]", nullable=False),
        sa.Column("status", sa.String(30), server_default="PENDING", nullable=False), sa.Column("false_positive", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("reviewed_by_id", U, sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_ifc_finding_project_status", "ifc_coordination_findings", ["project_id", "status"])

    op.create_table("ifc_suggestions", *base_columns(),
        sa.Column("project_id", U, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggestion_type", sa.String(50), nullable=False), sa.Column("payload_json", J, server_default="{}", nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False), sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), server_default="PENDING", nullable=False), sa.Column("reviewed_by_id", U, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("applied_entity_type", sa.String(40)), sa.Column("applied_entity_id", U))
    op.create_index("ix_ifc_suggestion_project_status", "ifc_suggestions", ["project_id", "status"])

    op.create_table("ifc_processing_jobs", *base_columns(),
        sa.Column("version_id", U, sa.ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(40), nullable=False), sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), server_default="QUEUED", nullable=False), sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("duration_ms", sa.Integer()),
        sa.Column("failure_code", sa.String(80)), sa.Column("failure_message", sa.Text()),
        sa.UniqueConstraint("version_id", "job_type", "idempotency_key", name="uq_ifc_job_idempotency"))


def downgrade() -> None:
    for name in ["ifc_processing_jobs", "ifc_suggestions", "ifc_coordination_findings", "ifc_impact_suggestions", "ifc_change_records", "ifc_comparisons", "ifc_entity_links", "ifc_elements", "ifc_spatial_nodes", "ifc_model_versions", "ifc_model_groups"]:
        op.drop_table(name)
