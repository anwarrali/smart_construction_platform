"""Indexing a document: PDF in, retrievable chunks out.

The state machine is the point of this module:

    NOT_INDEXED ─┐
    FAILED ──────┼──► INDEXING ──► READY
    READY ───────┘         │
                           └────► FAILED (+ index_error, chunks removed)

Three properties it guarantees, each of which is a way this could otherwise go
quietly wrong:

**A failed run never looks like a successful one.** On any error the chunks are
removed and the status becomes FAILED with a readable reason, committed as one
unit. Retrieval refuses anything that is not READY, so a half-written index is
unreachable by construction rather than by remembering to check.

**Two concurrent index requests cannot both run.** The move to INDEXING is a
conditional UPDATE whose row count is the lock. No lock table, no race.

**Re-indexing leaves no duplicates.** `add_chunks` replaces rather than
appends, so a corrected document stops answering from its outdated text.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_governance import AIProviderCall
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.rag import pdf_text
from app.services.rag.chunking import chunk_pages
from app.services.rag.embeddings import EmbeddingError, EmbeddingService
from app.services.rag.pdf_text import DocumentTextError
from app.services.rag.store import PreparedChunk, VectorStore, get_vector_store

logger = logging.getLogger("uvicorn.error").getChild("rag.ingestion")

STATUS_NOT_INDEXED = "NOT_INDEXED"
STATUS_INDEXING = "INDEXING"
STATUS_READY = "READY"
STATUS_FAILED = "FAILED"


class IndexingInProgress(Exception):
    """Another indexing run holds this document."""


class IndexingFailed(Exception):
    """Indexing failed. The message has already been persisted."""


@dataclass(frozen=True)
class IndexResult:
    document_id: uuid.UUID
    status: str
    page_count: int
    chunk_count: int
    indexed_at: datetime | None


def _claim(db: Session, document_id: uuid.UUID, *, force: bool) -> None:
    """Move the document to INDEXING, or refuse because a run is under way.

    The `rowcount` of this conditional UPDATE *is* the lock: two concurrent
    requests both attempt it, exactly one matches a row, and the loser is told
    to wait. Committed immediately so the claim is visible to other workers.

    `force` exists for the one case the guard cannot distinguish from a live
    run: a process that died mid-index leaves the row stuck in INDEXING
    forever, and without an override the document could never be re-indexed.
    """
    statement = update(Document).where(Document.id == document_id)
    if not force:
        statement = statement.where(Document.index_status != STATUS_INDEXING)

    result = db.execute(
        statement.values(
            index_status=STATUS_INDEXING,
            index_error=None,
            indexed_at=None,
        )
    )
    if not result.rowcount:
        db.rollback()
        raise IndexingInProgress(
            "This document is already being indexed. If a previous run was "
            "interrupted, retry with force=true."
        )
    db.commit()


def _fail(db: Session, document_id: uuid.UUID, reason: str) -> None:
    """Record the failure and leave nothing behind that looks indexed."""
    db.rollback()
    db.execute(delete_chunks_statement(document_id))
    db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(
            index_status=STATUS_FAILED,
            index_error=reason[:500],
            indexed_at=None,
            page_count=None,
        )
    )
    db.commit()


def delete_chunks_statement(document_id: uuid.UUID):
    from sqlalchemy import delete

    return delete(DocumentChunk).where(DocumentChunk.document_id == document_id)


def _record_provider_call(
    db: Session,
    *,
    project_id: uuid.UUID,
    reason: str,
    model: str,
    latency_ms: int,
    success: bool,
    tokens: int | None = None,
    error_code: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Log the OpenAI call to the existing governance table.

    Reused rather than reinvented: `AIProviderCall` already answers "what did
    we send to a provider, for which project, how long did it take and did it
    work" for the voice system, and RAG needs the same answers.
    """
    db.add(
        AIProviderCall(
            project_id=project_id,
            correlation_id=f"rag:{uuid.uuid4().hex[:16]}",
            reason=reason,
            provider="openai",
            model=model,
            latency_ms=latency_ms,
            success="success" if success else "failure",
            input_tokens=tokens,
            error_code=error_code,
            metadata_json=metadata or {},
        )
    )


def index_document(
    db: Session,
    document: Document,
    *,
    embedding_service: EmbeddingService | None = None,
    store: VectorStore | None = None,
    force: bool = False,
) -> IndexResult:
    """Index one document. Raises `IndexingFailed` with a persisted reason."""
    embedding_service = embedding_service or EmbeddingService()
    store = store or get_vector_store()

    document_id = document.id
    project_id = document.project_id
    file_url = document.file_url

    _claim(db, document_id, force=force)

    try:
        path = pdf_text.resolve_upload_path(file_url)
        pdf_text.assert_indexable(path)
        pages = pdf_text.extract_pages(path)
        chunks = chunk_pages(pages)
        if not chunks:
            raise DocumentTextError("No indexable text could be extracted from this document")
    except DocumentTextError as error:
        _fail(db, document_id, str(error))
        raise IndexingFailed(str(error)) from error

    started = time.monotonic()
    try:
        embedded = embedding_service.embed([chunk.content for chunk in chunks])
    except EmbeddingError as error:
        latency = int((time.monotonic() - started) * 1000)
        _fail(db, document_id, str(error))
        # Logged after the failure is committed, so the audit trail survives
        # even though the ingestion transaction was rolled back.
        _record_provider_call(
            db, project_id=project_id, reason="rag.embed",
            model=embedding_service.model, latency_ms=latency,
            success=False, error_code="embedding_error",
            metadata={"documentId": str(document_id), "chunks": len(chunks)},
        )
        db.commit()
        raise IndexingFailed(str(error)) from error

    latency = int((time.monotonic() - started) * 1000)

    if len(embedded.vectors) != len(chunks):
        message = "The embedding provider returned a different number of vectors than chunks"
        _fail(db, document_id, message)
        raise IndexingFailed(message)

    try:
        prepared = [
            PreparedChunk(
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, embedded.vectors)
        ]
        stored = store.add_chunks(
            db,
            document_id=document_id,
            project_id=project_id,
            chunks=prepared,
            embedding_model=embedded.model,
            embedding_dim=embedded.dimension,
        )
        indexed_at = datetime.now(timezone.utc)
        db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                index_status=STATUS_READY,
                indexed_at=indexed_at,
                index_error=None,
                page_count=len(pages),
            )
        )
        _record_provider_call(
            db, project_id=project_id, reason="rag.embed",
            model=embedded.model, latency_ms=latency, success=True,
            tokens=embedded.total_tokens,
            metadata={"documentId": str(document_id), "chunks": stored, "pages": len(pages)},
        )
        db.commit()
    except Exception as error:  # pragma: no cover - defensive
        _fail(db, document_id, f"Indexed text could not be stored: {error}")
        raise IndexingFailed(str(error)) from error

    logger.info(
        "indexed document %s: %s page(s), %s chunk(s)", document_id, len(pages), stored
    )
    return IndexResult(
        document_id=document_id,
        status=STATUS_READY,
        page_count=len(pages),
        chunk_count=stored,
        indexed_at=indexed_at,
    )


def chunk_count(db: Session, document_id: uuid.UUID) -> int:
    """How many chunks a document currently has.

    Counted rather than stored on `documents`: the chunks are the truth, and a
    denormalised counter is one more thing that can disagree with reality after
    a partial failure. The `(document_id, chunk_index)` index makes it cheap.
    """
    return int(
        db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
        ).scalar()
        or 0
    )
