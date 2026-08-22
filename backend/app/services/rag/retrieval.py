"""Finding the passages that might answer a question.

The authorization decision does not live here — it arrives here already made,
as the `readable_document_ids` the caller resolved through
`services/document_access.py`. This module cannot widen it: it passes that set
to the store, which requires it.

That split is deliberate. Retrieval has no idea what an Owner or a consultant
engineer is, and permission logic has no idea what a vector is. Neither can
quietly erode the other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.store import ScoredChunk, VectorStore, get_vector_store


@dataclass(frozen=True)
class RetrievedChunk:
    """A scored chunk with the document metadata a citation needs."""

    chunk: ScoredChunk
    document_title: str


def retrieve(
    db: Session,
    *,
    project_id: uuid.UUID,
    readable_document_ids: Sequence[uuid.UUID],
    query: str,
    k: int | None = None,
    embedding_service: EmbeddingService | None = None,
    store: VectorStore | None = None,
) -> list[RetrievedChunk]:
    """Top-k passages for a question, within one project and an allowed set.

    `readable_document_ids` is required and is never defaulted to "all" — an
    empty list correctly retrieves nothing, which is the right answer for a
    user who may read no documents here.
    """
    embedding_service = embedding_service or EmbeddingService()
    store = store or get_vector_store()
    k = k or settings.RAG_TOP_K

    if not readable_document_ids or not query.strip():
        return []

    query_vector = embedding_service.embed_one(query)
    scored = store.search(
        db,
        project_id=project_id,
        document_ids=list(readable_document_ids),
        query_embedding=query_vector,
        k=k,
    )
    if not scored:
        return []

    # Titles in one query rather than one per chunk: top-k chunks routinely
    # come from the same document.
    document_ids = {chunk.document_id for chunk in scored}
    titles = dict(
        db.execute(
            select(Document.id, Document.title).where(Document.id.in_(document_ids))
        ).all()
    )
    return [
        RetrievedChunk(chunk=chunk, document_title=titles.get(chunk.document_id, "Untitled document"))
        for chunk in scored
    ]
