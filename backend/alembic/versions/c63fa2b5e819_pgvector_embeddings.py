"""Move embeddings from JSONB to pgvector, with an HNSW cosine index

The MVP stored each embedding as a JSONB array and scored every candidate in
Python with numpy. That was a deliberate trade — it needed no database
extension — and `docs/RAG.md` §10 described exactly this migration as the way
out of it. The trade has been paid: similarity is now computed by PostgreSQL,
ordered in SQL, and served by an index.

## Prerequisite

The database image must ship the `vector` extension. `docker-compose.yml` was
moved from `postgres:15` to `pgvector/pgvector:pg15` — the same PostgreSQL
major version with the extension compiled in, so an existing data volume is
picked up unchanged. `CREATE EXTENSION` below needs superuser, which the
compose user has; a managed deployment may need the extension allow-listed by
the provider first.

## The column swap

`embedding` is replaced rather than duplicated:

    add `embedding_vector vector(1536)`  →  backfill  →  drop `embedding`
                                                      →  rename into place

Keeping the name means the ORM attribute, and therefore every line of
`services/rag/store.py`, is unchanged by the type change.

## Rows that cannot be converted

A `vector(1536)` holds exactly 1536 numbers. A chunk whose JSONB array is any
other length has no representation in the new column, and this migration
**deletes it** rather than admitting a NULL.

That is not data loss in any meaningful sense. Retrieval already refused those
rows — `JsonbVectorStore.search` skipped any vector whose length differed from
the query's, precisely because comparing across two embedding spaces produces
confident nonsense. They were unreachable text taking up space, and they are
regenerable by re-indexing the document or file they came from. Admitting them
as NULL would instead have cost the NOT NULL invariant permanently, and every
future reader would have to handle a case that should not exist.

The count is raised as a notice so an operator sees it happen.

## Rollback

`downgrade()` rebuilds the JSONB column from the vectors, which round-trips
exactly: `vector::text` is a JSON array of the same numbers. No chunk is lost
going back. The extension is left installed — dropping it would fail if
anything else had come to depend on it, and an unused extension costs nothing.

Revision ID: c63fa2b5e819
Revises: b52e9a1c4d70
"""

from alembic import op
import sqlalchemy as sa

revision = "c63fa2b5e819"
down_revision = "b52e9a1c4d70"
branch_labels = None
depends_on = None

#: The width of the column. A literal, not `settings.RAG_EMBEDDING_DIMENSIONS`:
#: a migration is a historical record of what was done to a database, and one
#: that reads runtime configuration produces a different schema depending on
#: the environment it happens to run in. Changing the dimension is a new
#: migration, not a different environment.
DIMENSIONS = 1536

HNSW_INDEX = "ix_document_chunks_embedding_hnsw"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        f"ALTER TABLE document_chunks ADD COLUMN embedding_vector vector({DIMENSIONS})"
    )

    # `::text::vector` is the documented conversion: a JSONB array renders as
    # `[1, 2, 3]`, which is pgvector's own input format.
    op.execute(
        f"""
        UPDATE document_chunks
           SET embedding_vector = embedding::text::vector
         WHERE jsonb_array_length(embedding) = {DIMENSIONS}
        """
    )

    # Reported before the delete so the number is visible in the migration log
    # rather than inferred from a row count afterwards.
    op.execute(
        f"""
        DO $$
        DECLARE stale integer;
        BEGIN
            SELECT count(*) INTO stale
              FROM document_chunks WHERE embedding_vector IS NULL;
            IF stale > 0 THEN
                RAISE NOTICE
                    'Deleting % chunk(s) whose embedding is not {DIMENSIONS} '
                    'dimensions. These were already unretrievable; re-index '
                    'their document or file to restore them.', stale;
            END IF;
        END $$;
        """
    )
    op.execute("DELETE FROM document_chunks WHERE embedding_vector IS NULL")

    op.drop_column("document_chunks", "embedding")
    op.alter_column("document_chunks", "embedding_vector", new_column_name="embedding")
    op.alter_column("document_chunks", "embedding", nullable=False)

    # Cosine, matching the `<=>` operator the store uses. An index built with
    # the default (L2) operator class would simply never be chosen, and the
    # only symptom would be slowness.
    op.execute(
        f"CREATE INDEX {HNSW_INDEX} ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {HNSW_INDEX}")

    op.add_column(
        "document_chunks",
        sa.Column("embedding_jsonb", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    # Round-trips exactly: a vector renders as `[1,2,3]`, which is valid JSON.
    op.execute("UPDATE document_chunks SET embedding_jsonb = embedding::text::jsonb")

    op.drop_column("document_chunks", "embedding")
    op.alter_column("document_chunks", "embedding_jsonb", new_column_name="embedding")
    op.alter_column("document_chunks", "embedding", nullable=False)

    # The extension stays. Dropping it would fail if anything else had started
    # using it, and an installed extension nothing references costs nothing.
