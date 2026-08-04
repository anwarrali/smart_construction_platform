"""API contracts for the project-scoped IFC intelligence workspace."""
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.user import CamelModel


class IFCCamelModel(CamelModel):
    model_config = ConfigDict(protected_namespaces=())


class IFCModelCreate(IFCCamelModel):
    name: str = Field(min_length=2, max_length=200)
    discipline: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=4000)


class IFCModelUpdate(IFCCamelModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    discipline: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=4000)


class IFCModelOut(IFCCamelModel):
    id: UUID
    project_id: UUID
    name: str
    discipline: str | None = None
    description: str | None = None
    active_version_id: UUID | None = None
    baseline_version_id: UUID | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IFCVersionOut(IFCCamelModel):
    id: UUID
    model_group_id: UUID
    project_id: UUID
    version_number: int
    revision_code: str | None = None
    version_type: str
    title: str
    description: str | None = None
    discipline: str | None = None
    authoring_source: str | None = None
    original_filename: str
    file_hash: str
    file_size: int
    ifc_schema: str | None = None
    authoring_application: str | None = None
    uploaded_by_id: UUID
    issue_date: date | None = None
    is_active: bool
    is_baseline: bool
    parent_version_id: UUID | None = None
    processing_status: str
    processing_progress: int
    parsing_error_code: str | None = None
    parsing_error_message: str | None = None
    support_log_id: str | None = None
    entity_count: int
    geometry_status: str
    geometry_error: str | None = None
    geometry_stats_json: dict[str, Any] = Field(default_factory=dict)
    geometry_generated_at: datetime | None = None
    analysis_status: str
    processing_duration_ms: int | None = None
    model_summary_json: dict[str, Any]
    asset_type_suggestion: str | None = None
    asset_type_confidence: float | None = None
    asset_type_confirmed: str | None = None
    row_version: int
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IFCVersionPatch(IFCCamelModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=4000)
    revision_code: str | None = Field(default=None, max_length=80)
    version_type: str | None = Field(default=None, max_length=50)
    issue_date: date | None = None
    asset_type_confirmed: str | None = Field(default=None, max_length=80)
    row_version: int = Field(ge=1)


class IFCSpatialNodeOut(IFCCamelModel):
    id: UUID
    version_id: UUID
    global_id: str
    entity_type: str
    name: str
    description: str | None = None
    parent_id: UUID | None = None
    node_type: str
    elevation: float | None = None
    area: float | None = None
    volume: float | None = None
    metadata_json: dict[str, Any]


class IFCElementOut(IFCCamelModel):
    id: UUID
    version_id: UUID
    global_id: str
    entity_type: str
    name: str
    description: str | None = None
    object_type: str | None = None
    predefined_type: str | None = None
    tag: str | None = None
    storey_node_id: UUID | None = None
    space_node_id: UUID | None = None
    zone_node_id: UUID | None = None
    building_node_id: UUID | None = None
    discipline: str | None = None
    system_name: str | None = None
    type_name: str | None = None
    material_summary: str | None = None
    properties_json: dict[str, Any]
    quantities_json: dict[str, Any]
    bounding_box_json: dict[str, Any] | None = None
    geometry_reference: str | None = None
    geometry_hash: str | None = None
    placement_hash: str | None = None
    metadata_json: dict[str, Any]


class IFCComparisonCreate(IFCCamelModel):
    base_version_id: UUID
    target_version_id: UUID

    @model_validator(mode="after")
    def distinct_versions(self):
        if self.base_version_id == self.target_version_id:
            raise ValueError("Comparison versions must be different")
        return self


class IFCComparisonOut(IFCCamelModel):
    id: UUID
    project_id: UUID
    base_version_id: UUID
    target_version_id: UUID
    status: str
    summary_json: dict[str, Any]
    created_by_id: UUID
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class IFCReviewRequest(IFCCamelModel):
    status: str = ""
    note: str | None = Field(default=None, max_length=4000)
    edited_payload: dict[str, Any] | None = None


class IFCBulkReview(IFCCamelModel):
    suggestion_ids: list[UUID] = Field(min_length=1, max_length=100)
    status: str
    note: str | None = Field(default=None, max_length=4000)


class IFCLinkCreate(IFCCamelModel):
    version_id: UUID
    ifc_element_id: UUID | None = None
    spatial_node_id: UUID | None = None
    linked_entity_type: str
    linked_entity_id: UUID
    link_type: str = Field(default="RELATED", max_length=60)

    @model_validator(mode="after")
    def one_ifc_source(self):
        if bool(self.ifc_element_id) == bool(self.spatial_node_id):
            raise ValueError("Provide exactly one IFC element or spatial node")
        return self


class IFCLinkOut(IFCCamelModel):
    id: UUID
    project_id: UUID
    version_id: UUID
    ifc_element_id: UUID | None = None
    spatial_node_id: UUID | None = None
    linked_entity_type: str
    linked_entity_id: UUID
    link_type: str
    confidence: float
    source: str
    confirmed_by_id: UUID | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class IFCPaged(IFCCamelModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
