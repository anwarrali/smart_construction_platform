"""Indexing a file: text in, retrievable chunks out.

Two kinds of thing can be indexed, and one state machine governs both:

  * a **`Document`** — the project library entry RAG was originally built on,
    always a PDF, its bytes reached through a public `/uploads/` URL;
  * an **`IngestedFile`** — the record the unified ingestion pipeline
    produces, whose text the pipeline has *already* extracted once and whose
    verdict is recorded in `metadata_json.extraction`.

They differ only in where the text comes from. `_Target` is the seam: it names
the row to drive, the project to scope to, and the `ChunkSource` to store
under. Everything after "here are the pages" — chunking, embedding, storing,
the status transitions, the failure handling — is shared, because two copies of
an indexing state machine is two places for a half-written index to hide.

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

**An unindexable file is not a failed one.** A scan, a drawing, a spreadsheet:
the ingestion pipeline already recorded that no text came out, so indexing
refuses *before claiming the row* and raises `NotIndexable`. The status stays
NOT_INDEXED and no error is written, because nothing was attempted and a
failure message would make an unindexable file look like a broken one.
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
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.ingestion import IngestedFile
from app.services import processing_pool
from app.services.rag import pdf_text, text_source
from app.services.rag.chunking import chunk_pages
from app.services.rag.embeddings import EmbeddingError, EmbeddingService
from app.services.rag.pdf_text import DocumentTextError, PageText
from app.services.rag.store import (
    ChunkSource, PreparedChunk, VectorStore, get_vector_store,
)

logger = logging.getLogger("uvicorn.error").getChild("rag.ingestion")

STATUS_NOT_INDEXED = "NOT_INDEXED"
STATUS_INDEXING = "INDEXING"
STATUS_READY = "READY"
STATUS_FAILED = "FAILED"


class IndexingInProgress(Exception):
    """Another indexing run holds this document."""


class IndexingFailed(Exception):
    """Indexing failed. The message has already been persisted."""


class NotIndexable(Exception):
    """There is no text in this file to index, and there never will be.

    Distinct from `IndexingFailed` on purpose. A failure is retryable and is
    recorded on the row; this is a permanent property of the file, already
    established by the ingestion pipeline, and it leaves no trace — see the
    module docstring.
    """


@dataclass(frozen=True)
class IndexResult:
    #: The id of whatever was indexed. Named `document_id` for the Document
    #: path's existing callers; `source` below says which kind it actually is.
    document_id: uuid.UUID
    status: str
    page_count: int
    chunk_count: int
    indexed_at: datetime | None
    #: "DOCUMENT" or "INGESTED_FILE". Additive: every existing caller ignores
    #: it and behaves exactly as before.
    source: str = "DOCUMENT"


@dataclass(frozen=True)
class _Target:
    """The row an indexing run drives, and where its chunks belong.

    The whole difference between indexing a `Document` and indexing an
    `IngestedFile` is captured here. Everything downstream is shared, which is
    what stops the two paths drifting into two subtly different definitions of
    "indexed".
    """

    model: type
    id: uuid.UUID
    project_id: uuid.UUID
    source: ChunkSource
    #: Whether the row has a `page_count` column to maintain. `documents` does;
    #: `ingested_files` does not, because the ingestion pipeline already
    #: records the page count in `metadata_json`.
    tracks_page_count: bool

    @classmethod
    def for_document(cls, document: Document) -> "_Target":
        return cls(
            model=Document, id=document.id, project_id=document.project_id,
            source=ChunkSource.from_document(document.id), tracks_page_count=True,
        )

    @classmethod
    def for_ingested_file(cls, file: IngestedFile) -> "_Target":
        return cls(
            model=IngestedFile, id=file.id, project_id=file.project_id,
            source=ChunkSource.from_ingested_file(file.id), tracks_page_count=False,
        )

    @property
    def label(self) -> str:
        return "document" if self.model is Document else "file"


def _claim(db: Session, target: _Target, *, force: bool) -> None:
    """Move the row to INDEXING, or refuse because a run is under way.

    The `rowcount` of this conditional UPDATE *is* the lock: two concurrent
    requests both attempt it, exactly one matches a row, and the loser is told
    to wait. Committed immediately so the claim is visible to other workers.

    `force` exists for the one case the guard cannot distinguish from a live
    run: a process that died mid-index leaves the row stuck in INDEXING
    forever, and without an override it could never be re-indexed.
    """
    model = target.model
    statement = update(model).where(model.id == target.id)
    if not force:
        statement = statement.where(model.index_status != STATUS_INDEXING)

    result = db.execute(
        statement.values(
            index_status=STATUS_INDEXING,
            index_error=None,
            indexed_at=None,
            # Stamped here and nowhere else. This is the only moment a run
            # begins, and the reaper's entire question — "how long has this
            # been INDEXING?" — is unanswerable without it.
            index_started_at=datetime.now(timezone.utc),
        )
    )
    if not result.rowcount:
        db.rollback()
        raise IndexingInProgress(
            f"This {target.label} is already being indexed. If a previous run "
            "was interrupted, retry with force=true."
        )
    db.commit()


def _fail(db: Session, target: _Target, reason: str) -> None:
    """Record the failure and leave nothing behind that looks indexed.

    The rollback first is what keeps this usable from inside a half-finished
    run: whatever the failed attempt wrote is discarded, and only then is the
    failure written and committed on its own. Without it a flush error would
    poison the session and the failure itself could not be recorded — leaving
    the row stuck in INDEXING, which is the one state nothing can recover from
    without `force`.
    """
    db.rollback()
    db.execute(delete_chunks_statement(target.source))
    values = {
        "index_status": STATUS_FAILED,
        "index_error": reason[:500],
        "indexed_at": None,
        # Cleared on the way out: a settled row has no run in flight, and a
        # lingering start time would make the reaper consider it again.
        "index_started_at": None,
    }
    if target.tracks_page_count:
        values["page_count"] = None
    db.execute(update(target.model).where(target.model.id == target.id).values(**values))
    db.commit()


def delete_chunks_statement(source: ChunkSource):
    from sqlalchemy import delete

    return delete(DocumentChunk).where(source.column == source.id)


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
    """Index one library document. Raises `IndexingFailed` with a persisted reason.

    Unchanged in behaviour: the same PDF path, the same errors, the same
    result. It now shares its state machine with `index_ingested_file`.
    """
    target = _Target.for_document(document)
    file_url = document.file_url

    def read_pages() -> list[PageText]:
        path = pdf_text.resolve_upload_path(file_url)
        pdf_text.assert_indexable(path)
        return pdf_text.extract_pages(path)

    return _run(
        db, target, read_pages,
        embedding_service=embedding_service, store=store, force=force,
    )


def index_ingested_file(
    db: Session,
    file: IngestedFile,
    *,
    embedding_service: EmbeddingService | None = None,
    store: VectorStore | None = None,
    force: bool = False,
) -> IndexResult:
    """Index one file from the unified ingestion pipeline.

    The gate is `metadata_json.extraction`, which the pipeline already
    recorded — so a scan, a drawing or a spreadsheet is refused without the
    file being opened at all. That refusal happens **before** the row is
    claimed, so an unindexable file is left exactly as it was rather than
    marked failed.

    Raises `NotIndexable` when there is no text to index, `IndexingInProgress`
    when a run already holds the row, and `IndexingFailed` when a run started
    and could not finish.
    """
    if not text_source.is_indexable(file):
        raise NotIndexable(text_source.why_not_indexable(file))

    target = _Target.for_ingested_file(file)
    file_id = file.id

    def read_pages() -> list[PageText]:
        # Re-fetched inside the run: the row was expired by the commit in
        # `_claim`, and touching a stale instance here would either reload it
        # implicitly or raise, depending on the session's state.
        current = db.get(IngestedFile, file_id)
        if current is None:
            raise DocumentTextError("The file no longer exists")
        return text_source.pages_for(db, current)

    return _run(
        db, target, read_pages,
        embedding_service=embedding_service, store=store, force=force,
    )


def _run(
    db: Session,
    target: _Target,
    read_pages,
    *,
    embedding_service: EmbeddingService | None,
    store: VectorStore | None,
    force: bool,
) -> IndexResult:
    """The indexing state machine, shared by both sources.

    `read_pages` is the only thing that varies, and it is called *after* the
    claim so that a slow extraction cannot be started twice concurrently.
    """
    embedding_service = embedding_service or EmbeddingService()
    store = store or get_vector_store()
    project_id = target.project_id

    _claim(db, target, force=force)

    try:
        pages = read_pages()
        chunks = chunk_pages(pages)
        if not chunks:
            raise DocumentTextError("No indexable text could be extracted from this file")
    except DocumentTextError as error:
        _fail(db, target, str(error))
        raise IndexingFailed(str(error)) from error

    started = time.monotonic()
    try:
        embedded = embedding_service.embed([chunk.content for chunk in chunks])
    except EmbeddingError as error:
        latency = int((time.monotonic() - started) * 1000)
        _fail(db, target, str(error))
        # Logged after the failure is committed, so the audit trail survives
        # even though the ingestion transaction was rolled back.
        _record_provider_call(
            db, project_id=project_id, reason="rag.embed",
            model=embedding_service.model, latency_ms=latency,
            success=False, error_code="embedding_error",
            metadata={"sourceId": str(target.id), "source": target.source.kind,
                      "chunks": len(chunks)},
        )
        db.commit()
        raise IndexingFailed(str(error)) from error

    latency = int((time.monotonic() - started) * 1000)

    if len(embedded.vectors) != len(chunks):
        message = "The embedding provider returned a different number of vectors than chunks"
        _fail(db, target, message)
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
            source=target.source,
            project_id=project_id,
            chunks=prepared,
            embedding_model=embedded.model,
            embedding_dim=embedded.dimension,
        )
        indexed_at = datetime.now(timezone.utc)
        values = {
            "index_status": STATUS_READY,
            "indexed_at": indexed_at,
            "index_error": None,
            "index_started_at": None,
        }
        if target.tracks_page_count:
            values["page_count"] = len(pages)
        db.execute(
            update(target.model).where(target.model.id == target.id).values(**values)
        )
        _record_provider_call(
            db, project_id=project_id, reason="rag.embed",
            model=embedded.model, latency_ms=latency, success=True,
            tokens=embedded.total_tokens,
            metadata={"sourceId": str(target.id), "source": target.source.kind,
                      "chunks": stored, "pages": len(pages)},
        )
        # One commit for the chunks, the status and the provider call
        # together. A crash before it leaves the row in INDEXING with no
        # chunks — recoverable with force — rather than READY with none.
        db.commit()
    except Exception as error:  # pragma: no cover - defensive
        _fail(db, target, f"Indexed text could not be stored: {error}")
        raise IndexingFailed(str(error)) from error

    logger.info(
        "indexed %s %s: %s page(s), %s chunk(s)",
        target.label, target.id, len(pages), stored,
    )
    return IndexResult(
        document_id=target.id,
        status=STATUS_READY,
        page_count=len(pages),
        chunk_count=stored,
        indexed_at=indexed_at,
        source=target.source.kind,
    )


def chunk_count(db: Session, document_id: uuid.UUID) -> int:
    """How many chunks a document currently has.

    Counted rather than stored on `documents`: the chunks are the truth, and a
    denormalised counter is one more thing that can disagree with reality after
    a partial failure. The `(document_id, chunk_index)` index makes it cheap.
    """
    return source_chunk_count(db, ChunkSource.from_document(document_id))


def ingested_file_chunk_count(db: Session, file_id: uuid.UUID) -> int:
    """How many chunks an ingested file currently has."""
    return source_chunk_count(db, ChunkSource.from_ingested_file(file_id))


def source_chunk_count(db: Session, source: ChunkSource) -> int:
    return int(
        db.execute(
            select(func.count(DocumentChunk.id)).where(source.column == source.id)
        ).scalar()
        or 0
    )


# --- Background indexing ----------------------------------------------------
#
# The Document path indexes synchronously inside `POST /rag/documents/{id}/index`
# and stays that way: changing it would change the contract of an endpoint that
# already returns a finished result, and nothing here needs that.
#
# The IngestedFile path does not, because it is reached from the unified
# ingestion pipeline where embedding a 300-page specification inside a request
# handler is exactly how a web server stops answering. It runs on
# `services/processing_pool.py` — the *same* bounded pool IFC parsing and file
# processing already share, so `IFC_MAX_CONCURRENT_PROCESSING` remains one
# ceiling over all heavy work rather than one of several.


def index_ingested_file_job(file_id: uuid.UUID, *, force: bool = False) -> None:
    """The background entry point: its own session, its own failure handling.

    A background job cannot borrow the request's session — the request has
    ended and the session with it. Every outcome is already persisted by the
    state machine before it reaches here, so this only has to make sure the
    session is closed and nothing escapes into a `Future` nobody reads.
    """
    db = SessionLocal()
    try:
        file = db.get(IngestedFile, file_id)
        if file is None:
            return
        index_ingested_file(db, file, force=force)
    except (NotIndexable, IndexingInProgress, IndexingFailed) as error:
        # All three are recorded outcomes, not surprises: NotIndexable leaves
        # the row untouched by design, and the other two have already written
        # their state. Logged at info because none of them is a defect.
        logger.info("indexing file %s did not complete: %s", file_id, error)
    except Exception:
        logger.exception("[RAG] background indexing failed for file %s", file_id)
        # The state machine records its own failures; anything reaching here
        # is a defect in this module, and the row may still read INDEXING.
        # Recovering it needs `force`, which is exactly what force is for.
    finally:
        db.close()


def submit_ingested_file_index(file_id: uuid.UUID, *, force: bool = False) -> None:
    """Hand indexing to the shared bounded pool."""
    processing_pool.submit(index_ingested_file_job, file_id, force=force)
