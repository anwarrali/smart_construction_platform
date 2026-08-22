"""RAG MVP: document_chunks table and document indexing state

Adds `document_chunks` (indexed, embedded passages of a PDF) and four columns
on `documents` that record whether — and how well — a document is indexed.

The embedding column is JSONB rather than a pgvector column. That is the
deliberate MVP trade recorded in docs/RAG.md: it keeps the stock `postgres:15`
image with no extension, and everything that reads a vector goes through the
`VectorStore` interface, so swapping in pgvector later is one new
implementation plus one migration and no application changes.

`page_number` is NOT NULL on purpose: a chunk that cannot name its page cannot
be cited, and an uncitable chunk has no place in a system whose whole promise
is grounded answers.

Revision ID: e91c4d7a3f26
Revises: d88f3a1b6c72
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e91c4d7a3f26"
down_revision = "d88f3a1b6c72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalised from documents.project_id so every retrieval query can
        # filter on the project directly. A join that must be remembered is a
        # join that will eventually be forgotten, and forgetting this one
        # leaks another project's document text.
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_document_order", "document_chunks", ["document_id", "chunk_index"])
    op.create_index("ix_document_chunks_document_page", "document_chunks", ["document_id", "page_number"])
    op.create_index("ix_document_chunks_project", "document_chunks", ["project_id"])

    # Existing documents are NOT_INDEXED, which is true: nothing has been
    # indexed yet, and indexing is explicit rather than automatic.
    op.add_column(
        "documents",
        sa.Column("index_status", sa.String(20), nullable=False, server_default="NOT_INDEXED"),
    )
    op.add_column("documents", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("index_error", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=True))
    op.create_index("ix_documents_index_status", "documents", ["index_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_index_status", table_name="documents")
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "index_error")
    op.drop_column("documents", "indexed_at")
    op.drop_column("documents", "index_status")

    op.drop_index("ix_document_chunks_project", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_page", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_order", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
