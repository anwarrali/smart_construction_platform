"""Finding the passages that might answer a question, across both sources.

The authorization decision does not live here — it arrives here already made,
as the two readable-id sets the caller resolved through
`services/document_access.py`. This module cannot widen them: it passes both to
the store, which requires both.

That split is deliberate. Retrieval has no idea what an Owner or a consultant
engineer is, and permission logic has no idea what a vector is. Neither can
quietly erode the other.

## Two sources, one result list

A passage may come from a library `Document` or from an `IngestedFile`. Both
appear in the same ranked list, scored the same way, and each carries enough
to build a citation that names exactly what it came from.

## What a title is, and what it is not

A citation shows a title, and for an ingested file that is `original_filename`
— the name the uploader gave it. It is deliberately *not* the storage key,
which is an address in private object storage and appears in no response
anywhere in this application. The `select` below names the two columns it
wants for that reason: a `select(IngestedFile)` would load the key into memory
one refactor away from being serialised.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.ingestion import IngestedFile
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.store import ScoredChunk, VectorStore, get_vector_store

#: Shown when a source row has vanished between indexing and retrieval. Rare,
#: and better than a citation with a blank title.
UNKNOWN_DOCUMENT_TITLE = "Untitled document"
UNKNOWN_FILE_TITLE = "Untitled file"


@dataclass(frozen=True)
class RetrievedChunk:
    """A scored chunk with the metadata a citation needs.

    `source_title` rather than `document_title`: the field would be a lie for
    half the results now, and a name that is true only sometimes is how a
    consumer ends up displaying a filename under a heading that says
    "document".
    """

    chunk: ScoredChunk
    source_title: str

    @property
    def source_type(self) -> str:
        """"DOCUMENT" or "INGESTED_FILE" — from the chunk's own source."""
        return self.chunk.source.kind


def _titles(
    db: Session,
    *,
    document_ids: set[uuid.UUID],
    file_ids: set[uuid.UUID],
) -> tuple[dict, dict]:
    """Titles for the sources actually retrieved, in at most two queries.

    Top-k chunks routinely come from the same handful of sources, so this is
    one query per source type rather than one per chunk — and none at all for
    a type that contributed nothing.
    """
    documents = dict(
        db.execute(
            select(Document.id, Document.title).where(Document.id.in_(document_ids))
        ).all()
    ) if document_ids else {}
    files = dict(
        db.execute(
            select(IngestedFile.id, IngestedFile.original_filename)
            .where(IngestedFile.id.in_(file_ids))
        ).all()
    ) if file_ids else {}
    return documents, files


def retrieve(
    db: Session,
    *,
    project_id: uuid.UUID,
    readable_document_ids: Sequence[uuid.UUID],
    readable_ingested_file_ids: Sequence[uuid.UUID],
    query: str,
    k: int | None = None,
    embedding_service: EmbeddingService | None = None,
    store: VectorStore | None = None,
) -> list[RetrievedChunk]:
    """Top-k passages for a question, within one project and two allowed sets.

    Both id sets are **required and never defaulted to "all"**. An empty set
    correctly retrieves nothing of that type, which is the right answer for a
    user who may read no sources of it here. Passing `[]` for both retrieves
    nothing at all — and, importantly, does so without reaching the database.

    `readable_ingested_file_ids` has no default value on purpose. A default of
    `()` would let a caller that predates unified retrieval keep compiling
    while silently searching documents only; a `TypeError` at the call site is
    the louder and safer failure.
    """
    embedding_service = embedding_service or EmbeddingService()
    store = store or get_vector_store()
    k = k or settings.RAG_TOP_K

    documents = list(readable_document_ids)
    files = list(readable_ingested_file_ids)
    if (not documents and not files) or not query.strip():
        # No readable source of either type, or nothing to ask. Returning here
        # also avoids paying for an embedding call that could not be used.
        return []

    query_vector = embedding_service.embed_one(query)
    scored = store.search(
        db,
        project_id=project_id,
        readable_document_ids=documents,
        readable_ingested_file_ids=files,
        query_embedding=query_vector,
        k=k,
    )
    if not scored:
        return []

    document_titles, file_titles = _titles(
        db,
        document_ids={c.document_id for c in scored if c.document_id},
        file_ids={c.ingested_file_id for c in scored if c.ingested_file_id},
    )

    retrieved: list[RetrievedChunk] = []
    for chunk in scored:
        if chunk.document_id is not None:
            title = document_titles.get(chunk.document_id, UNKNOWN_DOCUMENT_TITLE)
        else:
            title = file_titles.get(chunk.ingested_file_id, UNKNOWN_FILE_TITLE)
        retrieved.append(RetrievedChunk(chunk=chunk, source_title=title))
    return retrieved
