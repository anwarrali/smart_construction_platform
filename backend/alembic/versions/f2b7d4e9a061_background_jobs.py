"""Durable background job queue

Adds `background_jobs`: one row per unit of heavy work (IFC parsing and
geometry, file ingestion, RAG indexing, automatic agent analysis), inserted in
the transaction that causes it and claimed by workers with
`FOR UPDATE SKIP LOCKED`. Replaces the in-memory thread pool, whose queued work
vanished on restart. Additive; no existing table changes.

Revision ID: f2b7d4e9a061
Revises: e1a9c3d5f720
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f2b7d4e9a061"
down_revision = "e1a9c3d5f720"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("queue", sa.String(length=60), nullable=False, server_default="default"),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED"),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_by", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_background_jobs_kind", "background_jobs", ["kind"])
    op.create_index("ix_background_jobs_project_id", "background_jobs", ["project_id"])
    op.create_index("ix_background_jobs_claim", "background_jobs", ["queue", "status", "run_after"])
    op.create_index(
        "ix_background_jobs_one_active_per_key", "background_jobs", ["queue", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING') AND dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_one_active_per_key", table_name="background_jobs")
    op.drop_index("ix_background_jobs_claim", table_name="background_jobs")
    op.drop_index("ix_background_jobs_project_id", table_name="background_jobs")
    op.drop_index("ix_background_jobs_kind", table_name="background_jobs")
    op.drop_table("background_jobs")
