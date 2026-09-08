"""Project re-index jobs, and a timestamp that makes a stale run detectable

Two changes, both additive. No existing column is altered and no data is moved.

## `index_started_at`

`documents` and `ingested_files` each gain one nullable timestamp. It exists to
answer a question neither of the columns already there can:

  * `indexed_at` is written only on **success**, so it is NULL for exactly the
    rows the reaper cares about;
  * `updated_at` moves for **any** edit, so a document whose title was changed
    mid-index would look freshly started.

Without it, "has this been INDEXING for an hour, or for ten seconds?" is not
answerable, and a reaper would either miss genuinely stranded rows or seize
live ones. Set when a run claims the row; cleared when it settles.

Existing rows are left NULL. A row that is NOT_INDEXED, READY or FAILED has no
run to time, and a row already stuck in INDEXING from before this migration is
picked up by the reaper's NULL branch — see
`services/rag/maintenance.py`, which treats a NULL start on an INDEXING row as
"started before we were counting", i.e. definitely stale.

## `rag_index_jobs`

One row per project-wide re-index run. The partial unique index is the whole
duplicate-prevention story: two simultaneous requests cannot both create a
QUEUED/RUNNING row for the same project, because the second violates it. A
check-then-insert in application code would be a race, and losing that race
means a second full re-embedding pass over the same project.

`postgresql_where` needs the predicate to be immutable, which
`status IN (...)` is.

## Rollback

`downgrade()` drops the table and the two columns. The table is operational
history — which re-index ran, when, and how it went — not project content, so
losing it costs an audit trail rather than any user's work. Nothing else
references it.

Revision ID: d74ab3c6f92a
Revises: c63fa2b5e819
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d74ab3c6f92a"
down_revision = "c63fa2b5e819"
branch_labels = None
depends_on = None

ACTIVE_JOB_INDEX = "ix_rag_index_jobs_one_active_per_project"


def upgrade() -> None:
    for table in ("documents", "ingested_files"):
        op.add_column(
            table,
            sa.Column("index_started_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.create_table(
        "rag_index_jobs",
        # No server-side default on the id: every other table in this schema
        # lets the ORM generate the UUID (`UUIDPrimaryKeyMixin`).
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="STALE"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="QUEUED"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        # RESTRICT, matching every other actor column: a run with no requester
        # is a record nobody can account for.
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_rag_index_jobs_project_id", "rag_index_jobs", ["project_id"])
    op.create_index("ix_rag_index_jobs_status", "rag_index_jobs", ["status"])
    op.create_index("ix_rag_index_jobs_project_created", "rag_index_jobs",
                    ["project_id", "created_at"])
    # The duplicate-prevention guarantee. Partial, so a project may accumulate
    # any number of *settled* runs while holding at most one active.
    op.create_index(
        ACTIVE_JOB_INDEX, "rag_index_jobs", ["project_id"], unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index(ACTIVE_JOB_INDEX, table_name="rag_index_jobs")
    op.drop_index("ix_rag_index_jobs_project_created", table_name="rag_index_jobs")
    op.drop_index("ix_rag_index_jobs_status", table_name="rag_index_jobs")
    op.drop_index("ix_rag_index_jobs_project_id", table_name="rag_index_jobs")
    op.drop_table("rag_index_jobs")

    for table in ("documents", "ingested_files"):
        op.drop_column(table, "index_started_at")
