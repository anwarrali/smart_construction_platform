"""Unified file ingestion: ingested_files and ingestion_jobs

Two new tables and nothing else. No existing table is altered, no column is
dropped, and no data is moved — which is the whole safety argument for this
migration: rolling it back removes two empty-at-first tables and returns the
schema to exactly what it was.

## Why nothing is backfilled

There are three populations of existing files — `documents`, `attachments` and
`ifc_model_versions` — and a backfill would have to invent, for each row, a
detected format and a category that nothing ever looked at the bytes to
establish. A guessed classification is indistinguishable in the database from
one that was actually derived, and the whole point of this layer is that its
answers carry evidence.

IFC revisions are therefore registered as they are uploaded from now on, and
`services.ingestion.ifc_bridge.backfill_project` exists for an operator who
wants the historical ones — explicitly, per project, and repeatably. `documents`
and `attachments` keep their own identities and are not mirrored at all; they
are separate concerns, not older versions of this one.

## Rollback

`downgrade()` drops both tables. Any file uploaded through
`POST /projects/{id}/files` in the meantime loses its row while its stored
object remains in private storage under `ingest/`. That is deliberate: dropping
a table must never delete a customer's files. An operator rolling back should
either re-upload those files afterwards or leave the objects in place — they
are inert, and `ingest/` is the only prefix they occupy.

Revision ID: aa41c7d2e908
Revises: f59d2c8e4a13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "aa41c7d2e908"
down_revision = "f59d2c8e4a13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingested_files",
        # No server-side default: every other table in this schema lets the
        # ORM generate the UUID (`UUIDPrimaryKeyMixin`), and adding one here
        # would make this the only table needing pgcrypto.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("normalized_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("detected_format", sa.String(length=40), nullable=True),
        sa.Column("file_category", sa.String(length=30), nullable=False, server_default="OTHER"),
        sa.Column("document_kind", sa.String(length=40), nullable=True),
        sa.Column("classification_json", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="{}"),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="UPLOADED"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processor_name", sa.String(length=60), nullable=True),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="{}"),
        sa.Column("source_entity_type", sa.String(length=40), nullable=True),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        # RESTRICT, matching every other uploader column in the schema: a file
        # whose uploader has been deleted is evidence with no author, and the
        # platform would rather refuse the deletion than produce one.
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        # SET NULL, not CASCADE: removing a package must not silently destroy
        # members that have since been referenced elsewhere.
        sa.ForeignKeyConstraint(["parent_file_id"], ["ingested_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["ingested_files.id"], ondelete="SET NULL"),
        # The only uniqueness in this table. One row per stored object, so an
        # orphaned object or a double-registered one is impossible rather than
        # merely unlikely. Checksums are deliberately *not* unique — see the
        # model's `duplicate_of_id` docstring.
        sa.UniqueConstraint("storage_key", name="uq_ingested_files_storage_key"),
    )
    op.create_index("ix_ingested_files_project_id", "ingested_files", ["project_id"])
    op.create_index("ix_ingested_files_parent_file_id", "ingested_files", ["parent_file_id"])
    op.create_index("ix_ingested_files_detected_format", "ingested_files", ["detected_format"])
    op.create_index("ix_ingested_files_document_kind", "ingested_files", ["document_kind"])
    op.create_index("ix_ingested_files_status", "ingested_files", ["status"])
    op.create_index("ix_ingested_files_project_status", "ingested_files",
                    ["project_id", "status"])
    op.create_index("ix_ingested_files_project_category", "ingested_files",
                    ["project_id", "file_category"])
    op.create_index("ix_ingested_files_project_checksum", "ingested_files",
                    ["project_id", "checksum_sha256"])
    op.create_index("ix_ingested_files_source", "ingested_files",
                    ["source_entity_type", "source_entity_id"])

    op.create_table(
        "ingestion_jobs",
        # No server-side default: every other table in this schema lets the
        # ORM generate the UUID (`UUIDPrimaryKeyMixin`), and adding one here
        # would make this the only table needing pgcrypto.
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False, server_default="PROCESS"),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="QUEUED"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["file_id"], ["ingested_files.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("file_id", "job_type", "idempotency_key",
                            name="uq_ingestion_job_idempotency"),
    )
    op.create_index("ix_ingestion_jobs_file_id", "ingestion_jobs", ["file_id"])
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_file_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    for name in (
        "ix_ingested_files_source",
        "ix_ingested_files_project_checksum",
        "ix_ingested_files_project_category",
        "ix_ingested_files_project_status",
        "ix_ingested_files_status",
        "ix_ingested_files_document_kind",
        "ix_ingested_files_detected_format",
        "ix_ingested_files_parent_file_id",
        "ix_ingested_files_project_id",
    ):
        op.drop_index(name, table_name="ingested_files")
    op.drop_table("ingested_files")
