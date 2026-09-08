"""Where vectors live, and the interface that hides it.

`VectorStore` is the only thing the rest of the application knows about vector
storage. Nothing outside this module reads `DocumentChunk.embedding` or
computes a similarity. That is what made the move from JSONB to pgvector one
new class and one factory line, instead of a change to ingestion, retrieval,
answering and the API — the abstraction paid for itself exactly as intended,
and it is why the *next* storage change will be equally contained.

`PgVectorStore` is the implementation: embeddings in a `vector(N)` column,
cosine distance computed by PostgreSQL, ordering and the top-k limit done in
SQL, and an HNSW index behind it. It replaced `JsonbVectorStore`, which held
the same vectors as JSONB arrays and scored every candidate in numpy — an MVP
trade that avoided a database extension at the cost of a full scan per query.

The old implementation is gone rather than kept beside the new one: the column
is no longer JSONB, so it could not run, and a second `VectorStore` that cannot
work is worse than none.

**The security-critical part of this interface is that `search()` requires
`project_id` and an explicit set of readable ids for *each* source type.** All
three are mandatory parameters, so a query that is not scoped to a project and
to the sources the caller may read cannot be *expressed*, let alone executed.
An empty set means zero readable sources of that type; it never means "all".

A chunk's text comes from one of two places — a library `Document` or an
`IngestedFile` from the unified ingestion pipeline — and `ChunkSource` is how
callers name which. Writing, deleting and searching all handle both.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol, Sequence

from sqlalchemy import delete, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger("uvicorn.error").getChild("rag.store")


class VectorDimensionMismatch(ValueError):
    """A vector is not the width the `embedding` column accepts.

    Raised before the insert rather than letting PostgreSQL reject it, so the
    message names the configured dimension and the model that produced the
    offending vector instead of surfacing a driver error. Changing the
    embedding model to one of a different width is a schema change — see
    `RAG_EMBEDDING_DIMENSIONS`.
    """


@dataclass(frozen=True)
class ChunkSource:
    """Where a chunk's text came from: a library document, or an ingested file.

    A value object rather than two loose keyword arguments, because "exactly
    one of these" is then enforced once, at construction, instead of at every
    call site — and because a function taking `source` cannot be called with
    neither, which a pair of optional kwargs allows.

    It deliberately mirrors the database CHECK constraint on
    `document_chunks`. Two places state the same invariant, and that is the
    point: the constraint is the guarantee, this is the guard rail that stops
    application code discovering the guarantee the hard way.
    """

    document_id: uuid.UUID | None = None
    ingested_file_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if (self.document_id is None) == (self.ingested_file_id is None):
            raise ValueError(
                "a chunk source is exactly one of document_id or ingested_file_id"
            )

    @classmethod
    def from_document(cls, document_id: uuid.UUID) -> "ChunkSource":
        return cls(document_id=document_id)

    @classmethod
    def from_ingested_file(cls, ingested_file_id: uuid.UUID) -> "ChunkSource":
        return cls(ingested_file_id=ingested_file_id)

    @property
    def id(self) -> uuid.UUID:
        """The id of whichever source this is. Never None, by construction."""
        return self.document_id or self.ingested_file_id

    @property
    def column(self):
        """The `DocumentChunk` column this source is stored in."""
        return (
            DocumentChunk.document_id if self.document_id is not None
            else DocumentChunk.ingested_file_id
        )

    @property
    def kind(self) -> str:
        return "DOCUMENT" if self.document_id is not None else "INGESTED_FILE"


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
    """A retrieved chunk and how well it matched. Never carries the embedding.

    The source is a `ChunkSource`, not a bare id, so a result whose origin is
    unknown — or which claims two — cannot be constructed. A citation is only
    trustworthy if it can name exactly what it came from, and that guarantee is
    better placed in the type than in a convention.

    `document_id` and `ingested_file_id` remain readable as properties, so
    every existing consumer keeps working unchanged.
    """

    chunk_id: uuid.UUID
    source: ChunkSource
    page_number: int
    chunk_index: int
    content: str
    score: float

    @property
    def document_id(self) -> uuid.UUID | None:
        return self.source.document_id

    @property
    def ingested_file_id(self) -> uuid.UUID | None:
        return self.source.ingested_file_id


class VectorStore(Protocol):
    """The storage contract. Implementations differ; callers do not."""

    def add_chunks(
        self,
        db: Session,
        *,
        source: ChunkSource,
        project_id: uuid.UUID,
        chunks: Sequence[PreparedChunk],
        embedding_model: str,
        embedding_dim: int,
    ) -> int:
        """Store chunks for one source, replacing anything already stored."""

    def search(
        self,
        db: Session,
        *,
        project_id: uuid.UUID,
        readable_document_ids: Sequence[uuid.UUID],
        readable_ingested_file_ids: Sequence[uuid.UUID],
        query_embedding: Sequence[float],
        k: int,
    ) -> list[ScoredChunk]:
        """Top-k chunks within a project, across two explicitly scoped sets.

        Both id sets are **required**. Neither has a default, and neither may
        be omitted to mean "everything" — searching one source type only is
        expressed by passing `[]` for the other, which means *zero readable
        sources of that type*.
        """

    def delete_source(self, db: Session, *, source: ChunkSource) -> int:
        """Remove every chunk of one source. Returns how many were removed."""


#: The values pgvector accepts for `hnsw.iterative_scan`. Whitelisted rather
#: than interpolated, because the value reaches a `SET LOCAL` statement, which
#: takes no bind parameters — a configuration string is not user input, but a
#: setting that becomes SQL should still be unable to become *arbitrary* SQL.
_ITERATIVE_SCAN_MODES = frozenset({"strict_order", "relaxed_order", "off"})


def _apply_iterative_scan(db: Session) -> None:
    """Make HNSW keep scanning until it has k rows that pass the filter.

    Every query this store issues filters by project and by readable source
    ids. Plain HNSW fetches its candidate set first and filters afterwards, so
    a selective filter returns fewer than k rows — silently, and more often as
    the corpus grows. Iterative scan continues until k matches are found.

    `SET LOCAL`, so it lasts exactly this transaction: the setting must not
    leak onto the next request that borrows the same pooled connection.

    Left off — by configuring an empty string — on pgvector older than 0.8,
    which does not have the parameter. It is a recall improvement, not a
    correctness requirement: with it off, results are still correctly scoped
    and correctly ordered, just possibly fewer.
    """
    mode = (settings.RAG_HNSW_ITERATIVE_SCAN or "").strip().lower()
    if not mode:
        return
    if mode not in _ITERATIVE_SCAN_MODES:
        logger.warning(
            "ignoring RAG_HNSW_ITERATIVE_SCAN=%r; expected one of %s",
            mode, ", ".join(sorted(_ITERATIVE_SCAN_MODES)),
        )
        return
    db.execute(text(f"SET LOCAL hnsw.iterative_scan = {mode}"))


class PgVectorStore:
    """Vectors in a `vector(N)` column, similarity computed by PostgreSQL."""

    def add_chunks(
        self,
        db: Session,
        *,
        source: ChunkSource,
        project_id: uuid.UUID,
        chunks: Sequence[PreparedChunk],
        embedding_model: str,
        embedding_dim: int,
    ) -> int:
        # Checked here, once, rather than letting hundreds of inserts fail one
        # at a time deep in the driver. A mismatch means the embedding model
        # was changed to one of a different width, which needs a migration.
        expected = settings.RAG_EMBEDDING_DIMENSIONS
        if chunks and embedding_dim != expected:
            raise VectorDimensionMismatch(
                f"{embedding_model!r} produced {embedding_dim}-dimensional vectors, "
                f"but the embedding column holds {expected}. Changing the embedding "
                f"model to a different width requires a schema migration."
            )

        # Replace, never append. This delete is also the whole idempotency
        # story: re-indexing the same source twice cannot produce duplicates,
        # because the second run removes the first run's rows before writing
        # its own -- and it does so inside the caller's transaction, so a crash
        # between the delete and the insert rolls back to the previous state
        # rather than to an empty one.
        #
        # Leaving the old rows would be worse than duplication: they stay
        # retrievable, so a corrected file keeps answering from its outdated
        # text.
        self.delete_source(db, source=source)
        for chunk in chunks:
            db.add(
                DocumentChunk(
                    document_id=source.document_id,
                    ingested_file_id=source.ingested_file_id,
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
        readable_document_ids: Sequence[uuid.UUID],
        readable_ingested_file_ids: Sequence[uuid.UUID],
        query_embedding: Sequence[float],
        k: int,
    ) -> list[ScoredChunk]:
        """Top-k chunks within a project, across two explicitly scoped sets.

        ## The security invariant

        **An empty id set means zero readable sources of that type. It never
        means "all".** Both sets empty therefore returns nothing, and the
        function exits before a query is built -- so there is no code path in
        which this scans a project without an explicit, caller-resolved list of
        what may be read.

        That early return is not an optimisation. `column.in_([])` renders as a
        false-y expression in SQLAlchemy today, but combining two such
        expressions under `OR` and trusting the result is precisely the kind of
        detail that changes under a dialect or a version bump. The set that
        governs access is checked in Python, where it cannot be optimised away.

        Both parameters are keyword-only and required. A caller that has not
        been updated fails with a `TypeError` at the call site rather than
        silently searching one source type.

        ## Ordering

        `cosine_distance` is pgvector's `<=>`. Distance and similarity are
        opposites, so the score returned is `1 - distance`, which keeps the
        contract every caller was written against: higher is better, and an
        exact match scores 1.

        The `LIMIT` is in SQL, so the database returns k rows rather than the
        whole candidate set for Python to sort. That is the point of the move
        off JSONB.
        """
        documents = list(readable_document_ids)
        files = list(readable_ingested_file_ids)

        # Nothing readable, or nothing asked for. Neither is an error; both
        # correctly retrieve nothing.
        if k <= 0 or (not documents and not files):
            return []

        expected = settings.RAG_EMBEDDING_DIMENSIONS
        if len(query_embedding) != expected:
            # A question embedded by a different model than the corpus.
            # PostgreSQL would reject the comparison outright; refusing here
            # makes it an empty result rather than a 500 on a search endpoint.
            logger.warning(
                "refusing a %s-dimensional query against a %s-dimensional index",
                len(query_embedding), expected,
            )
            return []

        # One arm per non-empty set. An empty set contributes no arm at all,
        # so it can never widen the filter -- the difference between "these
        # documents" and "any document" is structural here.
        source_filters = []
        if documents:
            source_filters.append(DocumentChunk.document_id.in_(documents))
        if files:
            source_filters.append(DocumentChunk.ingested_file_id.in_(files))

        _apply_iterative_scan(db)

        distance = DocumentChunk.embedding.cosine_distance(list(query_embedding))
        rows = db.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.ingested_file_id,
                DocumentChunk.page_number,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                distance.label("distance"),
            )
            .where(
                # Both conditions, always. The project filter is the outer
                # boundary; the source filter is the per-source permission the
                # caller resolved. Neither is redundant: a document could be
                # moved between projects, and a readable-id list is only as
                # fresh as the request that built it. An id from another
                # project therefore matches the source arm and is still
                # excluded by the project arm.
                DocumentChunk.project_id == project_id,
                or_(*source_filters),
            )
            .order_by(distance)
            .limit(k)
        ).all()

        return [
            ScoredChunk(
                chunk_id=row.id,
                source=ChunkSource(
                    document_id=row.document_id,
                    ingested_file_id=row.ingested_file_id,
                ),
                page_number=row.page_number,
                chunk_index=row.chunk_index,
                content=row.content,
                # Cosine distance is in [0, 2]; similarity is 1 - distance.
                score=float(1.0 - row.distance),
            )
            for row in rows
        ]

    def delete_source(self, db: Session, *, source: ChunkSource) -> int:
        result = db.execute(delete(DocumentChunk).where(source.column == source.id))
        return int(result.rowcount or 0)


#: The store the application uses. This is the one line that changed when
#: vectors moved from JSONB to pgvector, which is what putting a
#: `VectorStore` in front of them was for.
_default_store: VectorStore = PgVectorStore()


def get_vector_store() -> VectorStore:
    return _default_store
