"""API contracts for the unified file ingestion pipeline.

One rule governs every field below: **the storage key never leaves the
server.** It is the address of a private object, and publishing it turns a
permission check into a guess about whether anyone will try the URL. Downloads
go through an endpoint that re-checks project access and streams the object;
the client never learns where it lives.

The second rule is the error split. `error` carries the publishable code and
the sentence a person can act on, from `services.ingestion.errors`. The
internal detail — the exception type, the library message — stays on the row.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class IngestedFileOut(CamelModel):
    # No `model_config` override: `CamelModel` already supplies the camelCase
    # alias generator and `from_attributes`, and no field here starts with
    # `model_`, so nothing needs relaxing.
    id: UUID
    project_id: UUID
    uploaded_by_id: UUID
    parent_file_id: UUID | None = None

    original_filename: str
    content_type: str | None = None
    detected_format: str | None = None
    file_category: str
    document_kind: str | None = None
    file_size_bytes: int

    status: str
    progress: int
    processor_name: str | None = None
    #: The publishable failure, or null. Composed by the endpoint from
    #: `error_code`; `error_message` has no field here and never will.
    error: dict | None = None

    #: What classification saw and why. Advisory throughout.
    classification_json: dict = {}
    #: Normalized extraction output. Shape depends on the processor and is
    #: documented by it; the envelope keys are always the same.
    metadata_json: dict = {}

    checksum_sha256: str | None = None
    duplicate_of_id: UUID | None = None
    source_entity_type: str | None = None
    source_entity_id: UUID | None = None

    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IngestedFilePage(CamelModel):
    """A page of files. Paginated from the start because a project's file list
    is unbounded — a design package alone contributes hundreds of rows."""

    items: list[IngestedFileOut]
    total: int
    limit: int
    offset: int


class UploadConstraints(CamelModel):
    """The rules the server will apply, so a client can check before uploading.

    Same purpose as `/ifc/upload-constraints`: without it, the only way to
    learn that a file is too large or of the wrong type is to transmit all of
    it and read the rejection. The server remains the authority and re-checks
    everything.
    """

    max_file_bytes: int
    max_file_mb: int
    accepted_extensions: list[str]
    max_package_entries: int
    max_package_total_bytes: int
    max_package_depth: int
    categories: list[str]


class IngestionRetryOut(CamelModel):
    file: IngestedFileOut
    queued: bool = Field(
        description="True when the file was handed to the background pool; "
                    "false when it was processed inline.",
    )
