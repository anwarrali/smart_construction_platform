"""Indexed text of a document, in retrievable pieces.

One row is one chunk: a passage of a document, small enough to be a useful
retrieval unit, tagged with the page it came from so an answer built on it can
cite that page honestly.

Two design points worth stating, because both are load-bearing:

**`page_number` is NOT NULL.** A chunk that cannot name its page cannot be
cited, and an uncitable chunk is useless in a system whose entire promise is
grounded answers. Chunking therefore never spans a page boundary — see
`services/rag/chunking.py`.

**`project_id` is denormalised.** It is derivable by joining `documents`, and
it is stored anyway so that every retrieval query filters on the project
column directly. A join that must be remembered is a join that will eventually
be forgotten, and forgetting this one leaks another project's document text.

The embedding lives in JSONB. That is a deliberate MVP trade documented in
`docs/RAG.md`: it keeps the stock `postgres:15` image, and it is replaced by
pgvector behind the `VectorStore` interface without touching anything else.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class DocumentChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        # Retrieval loads one document's chunks in order; re-indexing deletes
        # by document. Both are served by this.
        Index("ix_document_chunks_document_order", "document_id", "chunk_index"),
        # Project-wide retrieval filters on project first, then on the set of
        # documents the user may read.
        Index("ix_document_chunks_project", "project_id"),
        Index("ix_document_chunks_document_page", "document_id", "page_number"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Denormalised from `documents.project_id` — see the module docstring.
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: 1-based, matching what a reader sees in a PDF viewer.
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Position within the document, ascending across all pages.
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The embedding vector as a JSON array of floats. Never serialised into
    #: any API response — see `schemas/rag.py`, which has no field for it.
    embedding: Mapped[list] = mapped_column(JSONB, nullable=False)

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

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk doc={self.document_id} page={self.page_number} "
            f"index={self.chunk_index}>"
        )
