"""Where vectors live, and the interface that hides it.

`VectorStore` is the only thing the rest of the application knows about vector
storage. Nothing outside this module reads `DocumentChunk.embedding`, computes
a similarity, or names JSONB. That is what makes the pgvector migration later
a matter of writing one more class and changing one factory line — instead of
touching ingestion, retrieval, answering and the API.

`JsonbVectorStore` is the MVP implementation: embeddings as JSONB arrays,
cosine similarity in numpy, brute-force over the candidate set. Its limits are
real and documented in docs/RAG.md — it scans every candidate chunk, so cost
grows linearly with the corpus. For one indexed document (tens to hundreds of
chunks) that scan is sub-millisecond, and it needs no database extension.

**The security-critical part of this interface is that `search()` requires
`project_id` and an explicit set of readable document ids.** Both are
mandatory parameters, so a query that is not scoped to a project and to
documents the caller may read cannot be *expressed*, let alone executed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable, Protocol, Sequence

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk


@dataclass(frozen=True)
class PreparedChunk:
    """A chunk ready to be stored, with its vector already computed."""

    page_number: int
    chunk_index: int
    content: str
    token_count: int
    embedding: list[float]


@dataclass(frozen=True)
class ScoredChunk:
    """A retrieved chunk and how well it matched. Never carries the embedding."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    chunk_index: int
    content: str
    score: float


class VectorStore(Protocol):
    """The storage contract. Implementations differ; callers do not."""

    def add_chunks(
        self,
        db: Session,
        *,
        document_id: uuid.UUID,
        project_id: uuid.UUID,
        chunks: Sequence[PreparedChunk],
        embedding_model: str,
        embedding_dim: int,
    ) -> int:
        """Store chunks for a document, replacing anything already stored."""

    def search(
        self,
        db: Session,
        *,
        project_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        query_embedding: Sequence[float],
        k: int,
    ) -> list[ScoredChunk]:
        """Top-k chunks, restricted to a project and a set of documents."""

    def delete_document(self, db: Session, *, document_id: uuid.UUID) -> int:
        """Remove every chunk of a document. Returns how many were removed."""


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity of one vector against each row of a matrix.

    Normalising both sides rather than dividing by the product of norms keeps
    it stable for zero vectors, which would otherwise divide by zero and
    produce NaNs that sort unpredictably.
    """
    if matrix.size == 0:
        return np.empty(0, dtype=np.float32)

    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)

    row_norms = np.linalg.norm(matrix, axis=1)
    # A zero-length row scores 0 rather than NaN.
    safe_norms = np.where(row_norms == 0, 1.0, row_norms)
    scores = (matrix @ query) / (safe_norms * query_norm)
    return np.where(row_norms == 0, 0.0, scores).astype(np.float32)


class JsonbVectorStore:
    """Vectors in a JSONB column, similarity computed in Python."""

    def add_chunks(
        self,
        db: Session,
        *,
        document_id: uuid.UUID,
        project_id: uuid.UUID,
        chunks: Sequence[PreparedChunk],
        embedding_model: str,
        embedding_dim: int,
    ) -> int:
        # Replace, never append. Re-indexing a document must not leave the
        # previous run's chunks behind: they would still be retrievable, so a
        # corrected document would keep answering from its outdated text.
        self.delete_document(db, document_id=document_id)
        for chunk in chunks:
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    project_id=project_id,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding=list(chunk.embedding),
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                )
            )
        db.flush()
        return len(chunks)

    def search(
        self,
        db: Session,
        *,
        project_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        query_embedding: Sequence[float],
        k: int,
    ) -> list[ScoredChunk]:
        # An empty readable-document set means the user may read nothing here.
        # Returning early is not just an optimisation: without it the IN ()
        # clause would be dropped by some query builders and the filter would
        # silently widen to the whole project.
        if not document_ids or k <= 0:
            return []

        rows = db.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.page_number,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                DocumentChunk.embedding,
            ).where(
                # Both conditions, always. The project filter is the outer
                # boundary; the document filter is the per-document permission
                # the caller resolved. Neither is redundant: a document could
                # be moved between projects, and a readable-id list is only as
                # fresh as the request that built it.
                DocumentChunk.project_id == project_id,
                DocumentChunk.document_id.in_(list(document_ids)),
            )
        ).all()

        if not rows:
            return []

        # Vectors of the wrong length are from a superseded embedding model.
        # Comparing across incompatible spaces produces confident nonsense, so
        # they are skipped; re-indexing brings them back.
        dimension = len(query_embedding)
        usable = [row for row in rows if row.embedding and len(row.embedding) == dimension]
        if not usable:
            return []

        matrix = np.asarray([row.embedding for row in usable], dtype=np.float32)
        query = np.asarray(query_embedding, dtype=np.float32)
        scores = cosine_similarity(query, matrix)

        top = np.argsort(-scores)[:k]
        return [
            ScoredChunk(
                chunk_id=usable[i].id,
                document_id=usable[i].document_id,
                page_number=usable[i].page_number,
                chunk_index=usable[i].chunk_index,
                content=usable[i].content,
                score=float(scores[i]),
            )
            for i in top
        ]

    def delete_document(self, db: Session, *, document_id: uuid.UUID) -> int:
        result = db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        return int(result.rowcount or 0)


#: The store the application uses. Swapping in a `PgVectorStore` later means
#: changing this line and nothing else.
_default_store: VectorStore = JsonbVectorStore()


def get_vector_store() -> VectorStore:
    return _default_store
