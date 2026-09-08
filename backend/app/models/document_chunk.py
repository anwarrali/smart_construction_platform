"""Indexed text of a file, in retrievable pieces.

One row is one chunk: a passage small enough to be a useful retrieval unit,
tagged with the page it came from so an answer built on it can cite that page
honestly.

## Two sources, exactly one per chunk

A chunk's text comes from either a `Document` — the project library entry the
RAG layer was originally built on — or an `IngestedFile`, the record the
unified ingestion pipeline produces. Both columns are nullable and a CHECK
constraint requires exactly one of them, so "a chunk with no source" and "a
chunk claiming two sources" are both unrepresentable rather than merely
discouraged.

The alternative — a `source_type`/`source_id` pair — was rejected: a polymorphic
id carries no foreign key, so nothing would stop a chunk pointing at a file that
had been deleted, and the cascade that keeps indexed text from outliving its
source would have to be re-implemented in application code.

`document_id` is **not** deprecated. Every existing chunk uses it, retrieval
still resolves citations through it, and the Document path continues to work
untouched. This is a compatibility phase, not a migration.

## Three design points that are load-bearing

**`page_number` is NOT NULL.** A chunk that cannot name its page cannot be
cited, and an uncitable chunk is useless in a system whose entire promise is
grounded answers. Chunking therefore never spans a page boundary — see
`services/rag/chunking.py`. A format with no pages of its own (a Word document,
a text file) is chunked as a single page 1, which is truthful: that is where a
reader would find it.

**`project_id` is denormalised.** It is derivable by joining either parent, and
it is stored anyway so that every retrieval query filters on the project column
directly. A join that must be remembered is a join that will eventually be
forgotten, and forgetting this one leaks another project's document text.

The embedding is a pgvector `vector(N)`. It was JSONB during the MVP, scanned
and scored in Python; it is now a native type ordered by PostgreSQL, and the
change was contained to this column and `services/rag/store.py` exactly as
`docs/RAG.md` predicted.

**The dimension is part of the schema.** `vector(1536)` rejects a vector of any
other width, which turns "somebody changed the embedding model" from a silent
degradation — vectors from two incompatible spaces compared against each other,
producing confident nonsense — into a write that fails immediately. The old
JSONB column could hold anything and relied on a length check at read time to
skip mismatches. See `RAG_EMBEDDING_DIMENSIONS`.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin

#: The invariant that makes a chunk's provenance answerable. Written with
#: `num_nonnulls` rather than a spelled-out OR of two AND clauses because the
#: intent — *exactly one source* — is then readable at a glance, and stays
#: readable if a third source is ever added.
ONE_SOURCE_CONSTRAINT = "ck_document_chunks_exactly_one_source"


class DocumentChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(document_id, ingested_file_id) = 1",
            name=ONE_SOURCE_CONSTRAINT,
        ),
        # Retrieval loads one document's chunks in order; re-indexing deletes
        # by document. Both are served by this.
        Index("ix_document_chunks_document_order", "document_id", "chunk_index"),
        # The same two access patterns for the ingestion-pipeline source.
        Index("ix_document_chunks_ingested_file_order", "ingested_file_id", "chunk_index"),
        # Project-wide retrieval filters on project first, then on the set of
        # sources the user may read.
        Index("ix_document_chunks_project", "project_id"),
        Index("ix_document_chunks_document_page", "document_id", "page_number"),
        # Approximate-nearest-neighbour over cosine distance. HNSW rather than
        # IVFFlat: it needs no training pass, so it is correct on an empty
        # table and stays correct as the corpus grows, which matters for a
        # project that indexes a handful of documents at a time.
        #
        # `postgresql_ops` names the operator class, without which the index is
        # built for L2 distance and the `<=>` (cosine) queries silently do not
        # use it. The index is an optimisation, so that failure would be
        # invisible — a full scan returning the right answers slowly.
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    #: The library document this text came from, or NULL when it came from an
    #: ingested file. Exactly one of the two is set — see the class docstring.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    #: The unified-pipeline file this text came from, or NULL when it came from
    #: a library document.
    ingested_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingested_files.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    #: Denormalised from the parent's `project_id` — see the module docstring.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: 1-based, matching what a reader sees in a PDF viewer.
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Position within the source, ascending across all pages.
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The embedding, as a native pgvector value. Never serialised into any API
    #: response — see `schemas/rag.py`, which has no field for it.
    #:
    #: Read and written only by `services/rag/store.py`. Nothing else in the
    #: application touches this column, which is what made the move off JSONB a
    #: one-module change.
    embedding: Mapped[list] = mapped_column(
        Vector(settings.RAG_EMBEDDING_DIMENSIONS), nullable=False
    )

    #: Which model produced the vector, and how long it is. Stored so that a
    #: model change is *detected* rather than silently comparing vectors from
    #: two incompatible spaces, which would degrade retrieval quietly instead
    #: of failing.
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")
    ingested_file: Mapped["IngestedFile"] = relationship(back_populates="chunks")

    @property
    def source_id(self) -> uuid.UUID:
        """Whichever parent this chunk actually has.

        The CHECK constraint guarantees one of them is set, so this cannot
        return None for a row that came out of the database.
        """
        return self.document_id or self.ingested_file_id

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk source={self.source_id} page={self.page_number} "
            f"index={self.chunk_index}>"
        )
