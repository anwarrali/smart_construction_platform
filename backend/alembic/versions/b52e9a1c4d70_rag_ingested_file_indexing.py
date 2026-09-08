"""RAG on ingested files: indexing lifecycle, and a second chunk source

Two changes, both additive in the sense that matters — no existing row is
altered and no existing behaviour changes.

**`ingested_files` gains the three indexing columns `documents` already has.**
Same names, same types, same four values. Every existing row starts at
NOT_INDEXED, which is the truth: nothing has been indexed.

**`document_chunks` gains a second source.** `document_id` becomes nullable and
`ingested_file_id` is added, with a CHECK requiring exactly one of them. Every
existing chunk keeps its `document_id` and satisfies the constraint unchanged,
which is why the constraint can be added without validating an exception list.

## Ordering

The nullability change happens *before* the CHECK is added. Reversing that
order would briefly have a NOT NULL column and a constraint permitting NULL —
harmless here, but the reverse in `downgrade` genuinely matters: the constraint
must be dropped before `document_id` can be made NOT NULL again, or Postgres
evaluates a constraint against a column it is mid-way through rewriting.

## Why nothing is backfilled

Indexing costs embedding credits, and the existing Document path deliberately
never indexes on upload for exactly that reason (see `api/rag.py`). Backfilling
would spend money on every file already in the system without anybody asking.
Files are indexed on request, one at a time, as they always have been.

## Rollback

`downgrade()` deletes chunks that came from an ingested file before restoring
`document_id` to NOT NULL — those rows have no `document_id` and could not
satisfy it. That is a real data loss and it is the correct one: the rows are
derived data (embeddings of text still held in private storage), they are
regenerable by re-indexing, and the alternative — refusing to downgrade — would
strand an operator who needs to roll back. The `ingested_files` columns are
dropped after, so nothing is left claiming to be indexed.

Revision ID: b52e9a1c4d70
Revises: aa41c7d2e908
"""

from alembic import op
import sqlalchemy as sa

revision = "b52e9a1c4d70"
down_revision = "aa41c7d2e908"
branch_labels = None
depends_on = None

ONE_SOURCE_CONSTRAINT = "ck_document_chunks_exactly_one_source"


def upgrade() -> None:
    # --- ingested_files: the indexing lifecycle -----------------------------
    op.add_column(
        "ingested_files",
        sa.Column("index_status", sa.String(length=20), nullable=False,
                  server_default="NOT_INDEXED"),
    )
    op.add_column(
        "ingested_files",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingested_files",
        sa.Column("index_error", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_ingested_files_index_status", "ingested_files", ["index_status"])

    # --- document_chunks: a second source -----------------------------------
    op.add_column(
        "document_chunks",
        sa.Column("ingested_file_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_chunks_ingested_file_id", "document_chunks", "ingested_files",
        ["ingested_file_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_document_chunks_ingested_file_id", "document_chunks",
                    ["ingested_file_id"])
    op.create_index("ix_document_chunks_ingested_file_order", "document_chunks",
                    ["ingested_file_id", "chunk_index"])

    op.alter_column("document_chunks", "document_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=True)
    # Added last, and satisfied by every existing row: they all have a
    # document_id and no ingested_file_id, which is exactly one source.
    op.create_check_constraint(
        ONE_SOURCE_CONSTRAINT, "document_chunks",
        "num_nonnulls(document_id, ingested_file_id) = 1",
    )


def downgrade() -> None:
    op.drop_constraint(ONE_SOURCE_CONSTRAINT, "document_chunks", type_="check")
    # Regenerable derived data, deleted so `document_id` can be NOT NULL again.
    # See the module docstring for why this is the right trade.
    op.execute("DELETE FROM document_chunks WHERE document_id IS NULL")
    op.alter_column("document_chunks", "document_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=False)

    op.drop_index("ix_document_chunks_ingested_file_order", table_name="document_chunks")
    op.drop_index("ix_document_chunks_ingested_file_id", table_name="document_chunks")
    op.drop_constraint("fk_document_chunks_ingested_file_id", "document_chunks",
                       type_="foreignkey")
    op.drop_column("document_chunks", "ingested_file_id")

    op.drop_index("ix_ingested_files_index_status", table_name="ingested_files")
    op.drop_column("ingested_files", "index_error")
    op.drop_column("ingested_files", "indexed_at")
    op.drop_column("ingested_files", "index_status")
