"""IFC intelligence persistence: immutable versions, extracted facts, links and reviewable proposals."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IFCModelGroup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_model_groups"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_ifc_group_project_name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    baseline_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    versions: Mapped[list["IFCModelVersion"]] = relationship(back_populates="model_group", cascade="all, delete-orphan", foreign_keys="IFCModelVersion.model_group_id")


class IFCModelVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_model_versions"
    __table_args__ = (
        UniqueConstraint("model_group_id", "version_number", name="uq_ifc_group_version_number"),
        UniqueConstraint("project_id", "file_hash", name="uq_ifc_project_file_hash"),
        Index("ix_ifc_version_project_status", "project_id", "processing_status"),
    )

    model_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    revision_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    version_type: Mapped[str] = mapped_column(String(50), nullable=False, default="DESIGN", server_default="DESIGN")
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    authoring_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    ifc_schema: Mapped[str | None] = mapped_column(String(40), nullable=True)
    authoring_application: Mapped[str | None] = mapped_column(String(250), nullable=True)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="SET NULL"), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(40), nullable=False, default="UPLOADED", server_default="UPLOADED", index=True)
    processing_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    parsing_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parsing_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_log_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    geometry_status: Mapped[str] = mapped_column(String(40), nullable=False, default="NOT_REQUESTED", server_default="NOT_REQUESTED")
    geometry_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    geometry_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry_stats_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    geometry_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(40), nullable=False, default="PENDING", server_default="PENDING")
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    asset_type_suggestion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    asset_type_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    asset_type_confirmed: Mapped[str | None] = mapped_column(String(80), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    model_group: Mapped[IFCModelGroup] = relationship(back_populates="versions", foreign_keys=[model_group_id])
    spatial_nodes: Mapped[list["IFCSpatialNode"]] = relationship(back_populates="version", cascade="all, delete-orphan")
    elements: Mapped[list["IFCElement"]] = relationship(back_populates="version", cascade="all, delete-orphan")


class IFCSpatialNode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_spatial_nodes"
    __table_args__ = (
        UniqueConstraint("version_id", "global_id", name="uq_ifc_spatial_version_global_id"),
        Index("ix_ifc_spatial_version_type", "version_id", "node_type"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    global_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    area: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    version: Mapped[IFCModelVersion] = relationship(back_populates="spatial_nodes")
    parent: Mapped["IFCSpatialNode | None"] = relationship(remote_side="IFCSpatialNode.id")


class IFCElement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_elements"
    __table_args__ = (
        UniqueConstraint("version_id", "global_id", name="uq_ifc_element_version_global_id"),
        Index("ix_ifc_element_version_class", "version_id", "entity_type"),
        Index("ix_ifc_element_version_discipline", "version_id", "discipline"),
        Index("ix_ifc_element_version_storey", "version_id", "storey_node_id"),
        Index("ix_ifc_element_version_space", "version_id", "space_node_id"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    global_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    predefined_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storey_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL"), nullable=True)
    space_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL"), nullable=True)
    zone_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL"), nullable=True)
    building_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_spatial_nodes.id", ondelete="SET NULL"), nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    system_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    type_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    material_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    properties_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    quantities_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    bounding_box_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geometry_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    geometry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    placement_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    version: Mapped[IFCModelVersion] = relationship(back_populates="elements")
    storey: Mapped[IFCSpatialNode | None] = relationship(foreign_keys=[storey_node_id])
    space: Mapped[IFCSpatialNode | None] = relationship(foreign_keys=[space_node_id])


class IFCEntityLink(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_entity_links"
    __table_args__ = (
        UniqueConstraint("version_id", "ifc_element_id", "spatial_node_id", "linked_entity_type", "linked_entity_id", "link_type", name="uq_ifc_entity_link"),
        Index("ix_ifc_link_project_target", "project_id", "linked_entity_type", "linked_entity_id"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    ifc_element_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_elements.id", ondelete="CASCADE"), nullable=True, index=True)
    spatial_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_spatial_nodes.id", ondelete="CASCADE"), nullable=True, index=True)
    linked_entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    linked_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    link_type: Mapped[str] = mapped_column(String(60), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="USER", server_default="USER")
    confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IFCComparison(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_comparisons"
    __table_args__ = (UniqueConstraint("base_version_id", "target_version_id", name="uq_ifc_comparison_pair"),)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    base_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False)
    target_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="QUEUED", server_default="QUEUED", index=True)
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IFCChangeRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_change_records"
    __table_args__ = (Index("ix_ifc_change_comparison_type", "comparison_id", "change_type"),)
    comparison_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_comparisons.id", ondelete="CASCADE"), nullable=False, index=True)
    base_element_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_elements.id", ondelete="SET NULL"), nullable=True)
    target_element_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_elements.id", ondelete="SET NULL"), nullable=True)
    change_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    match_method: Mapped[str] = mapped_column(String(40), nullable=False)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    property_changes_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    geometry_change_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    location_change_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW", server_default="LOW", index=True)
    discipline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    storey: Mapped[str | None] = mapped_column(String(250), nullable=True)
    space: Mapped[str | None] = mapped_column(String(250), nullable=True)


class IFCImpactSuggestion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_impact_suggestions"
    comparison_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_comparisons.id", ondelete="CASCADE"), nullable=False, index=True)
    change_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_change_records.id", ondelete="CASCADE"), nullable=True)
    impact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    affected_entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    affected_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", server_default="PENDING", index=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IFCCoordinationFinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_coordination_findings"
    __table_args__ = (Index("ix_ifc_finding_project_status", "project_id", "status"),)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False)
    comparison_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_comparisons.id", ondelete="SET NULL"), nullable=True)
    element_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_elements.id", ondelete="CASCADE"), nullable=False)
    element_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_elements.id", ondelete="CASCADE"), nullable=True)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    geometry_evidence_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    affected_disciplines_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    affected_tasks_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    suggested_recipients_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", server_default="PENDING", index=True)
    false_positive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IFCSuggestion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_suggestions"
    __table_args__ = (Index("ix_ifc_suggestion_project_status", "project_id", "status"),)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", server_default="PENDING", index=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    applied_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class AIInsight(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistent, reviewable structured project-intelligence result."""
    __tablename__ = "ai_insights"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_ai_insight_fingerprint"),
        Index("ix_ai_insight_project_status_severity", "project_id", "status", "severity"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    model_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    insight_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    potential_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    affected_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    related_task_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    related_issue_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    related_evidence_ids_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_engine: Mapped[str] = mapped_column(String(80), nullable=False, default="RULE_ENGINE", server_default="RULE_ENGINE")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NEW", server_default="NEW", index=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    applied_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class IFCProcessingJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ifc_processing_jobs"
    __table_args__ = (UniqueConstraint("version_id", "job_type", "idempotency_key", name="uq_ifc_job_idempotency"),)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ifc_model_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="QUEUED", server_default="QUEUED", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
