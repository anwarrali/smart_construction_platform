"""Document question answering.

Three endpoints, one authorization story: every one of them resolves what the
caller may read through `services/document_access.py` — the same rules the
documents API enforces — before touching an index or a vector.

That shared path is the point. Answering questions *out of* document text is a
read of that text, so a RAG route that checked only project access would hand
an Owner the contents of a draft they are forbidden to download, quoted back
with page numbers. Retrieval is scoped to the project **and** to the specific
document ids the caller may read; the store's `search` requires both, so an
unscoped query cannot be written.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.document import Document
from app.models.ingestion import IngestedFile
from app.models.user import User
from app.schemas.rag import (
    DocumentIndexStatus,
    IngestedFileIndexStatus,
    RagCitation,
    RagQueryRequest,
    RagQueryResponse,
    RagReindexRequest,
    RagReindexStatus,
)
from app.services import rag
from app.services.audit_service import record_audit
from app.services.document_access import (
    assert_document_readable,
    assert_ingested_file_readable,
    readable_document_ids,
    readable_ingested_file_ids,
)
from app.services.authorization import require
from app.services.rag import maintenance, text_source
from app.services.rag.answering import AnswerError, AnswerService
from app.services.rag.embeddings import EmbeddingError, EmbeddingService
from app.models.ifc import IFCModelVersion
from app.models.site_report import SiteReport
from app.services.knowledge_router import SourceAvailability, route_question

router = APIRouter(prefix="/rag", tags=["RAG"])


def _require_enabled() -> None:
    """Refuse cleanly when RAG is switched off.

    503 rather than 404: the feature exists, this deployment has not enabled
    it, and a client should be able to tell those apart. The rest of the
    application is entirely unaffected by the flag.
    """
    if not settings.RAG_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document question answering is not enabled on this server",
        )


def _get_readable_document(
    document_id: uuid.UUID, db: Session, current_user: User
) -> Document:
    """Fetch a document the caller is genuinely allowed to read, or raise."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    # Raises 403 with the reason (project, owner scope, or discipline).
    assert_document_readable(db, current_user, document)
    return document


def _get_readable_ingested_file(
    file_id: uuid.UUID, db: Session, current_user: User
) -> IngestedFile:
    """Fetch an ingested file the caller is genuinely allowed to read, or raise.

    Narrows through `assert_ingested_file_readable`, the same rule unified
    retrieval uses, rather than inventing a RAG-specific permission. Indexing
    and reading a file's text is a read of that file, and the answer must be
    the one the file library would give.

    404 rather than 403 for a file outside every project this person can
    reach: telling a stranger that an id exists is itself information.
    """
    file = db.query(IngestedFile).filter(IngestedFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    # The same narrowing retrieval applies, not a looser one. Before unified
    # retrieval this stopped at project access plus `document.view`, which
    # would have let an external participant index — and therefore read — a
    # file that was never shared with them.
    assert_ingested_file_readable(db, current_user, file)
    return file


def _ingested_file_status(db: Session, file: IngestedFile) -> IngestedFileIndexStatus:
    indexable = text_source.is_indexable(file)
    return IngestedFileIndexStatus(
        file_id=file.id,
        status=file.index_status or rag.STATUS_NOT_INDEXED,
        extraction=text_source.extraction_kind(file),
        indexable=indexable,
        not_indexable_reason=None if indexable else text_source.why_not_indexable(file),
        chunk_count=rag.ingested_file_chunk_count(db, file.id),
        indexed_at=file.indexed_at,
        error=file.index_error,
    )


@router.post(
    "/files/{file_id}/index",
    response_model=IngestedFileIndexStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def index_ingested_file(
    file_id: uuid.UUID,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue indexing for one file from the unified ingestion pipeline.

    202 and not 200, unlike the document endpoint: this returns as soon as the
    work is queued. Embedding a 300-page specification is not something to do
    inside a request handler, and the work runs on the same bounded pool IFC
    parsing and file processing already share — so one setting,
    `IFC_MAX_CONCURRENT_PROCESSING`, remains the ceiling over all heavy work.

    A file with no extractable text is refused here rather than queued, using
    the verdict the ingestion pipeline already recorded — so the file is never
    opened to answer a question that has already been answered.

    The permission is `document.view` and not `document.upload`: indexing a
    file the caller may already read exposes nothing new to them.
    """
    _require_enabled()
    file = _get_readable_ingested_file(file_id, db, current_user)

    if not text_source.is_indexable(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=text_source.why_not_indexable(file),
        )
    if file.index_status == rag.STATUS_INDEXING and not force:
        # Told before queuing rather than by the worker afterwards, where the
        # caller would never see it.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This file is already being indexed. If a previous run was "
                "interrupted, retry with force=true."
            ),
        )

    rag.submit_ingested_file_index(file.id, force=force)
    return _ingested_file_status(db, file)


@router.get("/files/{file_id}/status", response_model=IngestedFileIndexStatus)
def ingested_file_index_status(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether a file is indexed, why it cannot be, or why the last run failed."""
    _require_enabled()
    file = _get_readable_ingested_file(file_id, db, current_user)
    return _ingested_file_status(db, file)


@router.post(
    "/documents/{document_id}/index",
    response_model=DocumentIndexStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def index_document(
    document_id: uuid.UUID,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Index one PDF so it can be queried.

    Explicit by design: indexing is never triggered by upload, so nobody
    spends embedding credits on every drawing that lands in a project.

    `force=true` re-claims a document stuck in INDEXING after an interrupted
    run — the only case the concurrency guard cannot distinguish from a live
    one.
    """
    _require_enabled()
    document = _get_readable_document(document_id, db, current_user)

    try:
        result = rag.index_document(db, document, force=force)
    except rag.IndexingInProgress as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except rag.IndexingFailed as error:
        # The reason is already persisted to `index_error`, so the status
        # endpoint tells the same story as this response.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))

    return DocumentIndexStatus(
        document_id=result.document_id,
        status=result.status,
        page_count=result.page_count,
        chunk_count=result.chunk_count,
        indexed_at=result.indexed_at,
        error=None,
    )


@router.get("/documents/{document_id}/status", response_model=DocumentIndexStatus)
def document_index_status(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Whether a document is indexed, and why not if it is not."""
    _require_enabled()
    document = _get_readable_document(document_id, db, current_user)

    return DocumentIndexStatus(
        document_id=document.id,
        status=document.index_status or rag.STATUS_NOT_INDEXED,
        page_count=document.page_count,
        chunk_count=rag.chunk_count(db, document.id),
        indexed_at=document.indexed_at,
        error=document.index_error,
    )


@router.post("/query", response_model=RagQueryResponse)
def query_documents(
    payload: RagQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask a question about a project's indexed documents.

    Answers are grounded: the model is given only the retrieved passages and
    is required to say so when they do not contain the answer. Citations are
    constructed from the retrieved records, never from the model's prose, so a
    citation cannot point at a page that was not actually retrieved.
    """
    _require_enabled()

    if not user_has_project_access(db, current_user, payload.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")

    if payload.document_id:
        document = _get_readable_document(payload.document_id, db, current_user)
        if document.project_id != payload.project_id:
            # Refusing rather than silently trusting document_id: accepting a
            # document from another project here would let the project filter
            # be bypassed by naming a document directly.
            raise HTTPException(
                status_code=400, detail="documentId does not belong to the selected project"
            )
        if document.index_status != rag.STATUS_READY:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This document is not indexed yet",
            )
        allowed_ids = [document.id]
        # Naming a document is an instruction to look *there*, so no ingested
        # file is in scope — expressed as an explicit empty set, which the
        # store reads as "zero readable files", never as "all".
        allowed_file_ids: list = []
        # An explicitly named document is an explicit instruction. Routing is
        # for questions where nobody said where to look.
        routing = None
    else:
        routing = route_question(
            payload.query,
            availability=_availability(db, payload.project_id),
        )
        if not routing.needs_document_retrieval:
            # The question has a better home than the document vectors. Before
            # routing existed this searched anyway and returned whichever
            # passage happened to be nearest, which is how an unrelated
            # contract clause ended up answering a question about progress.
            return RagQueryResponse(
                answer=(
                    f"{routing.reason} Ask this through the project knowledge endpoint, "
                    "which reads that source directly."
                ),
                found=False, citations=[], chunks_used=0,
                route=routing.source.value, route_reason=routing.reason,
                route_matched=routing.matched,
            )
        # Every source in the project this user may read, resolved through the
        # same rules the documents and files APIs apply, then narrowed to those
        # actually indexed. Two independent resolutions, because the two
        # authorization rules are genuinely different — see
        # `services/document_access.py`.
        readable = readable_document_ids(db, current_user, payload.project_id)
        allowed_ids = [
            row[0]
            for row in db.query(Document.id)
            .filter(
                Document.id.in_(readable),
                Document.index_status == rag.STATUS_READY,
            )
            .all()
        ] if readable else []
        readable_files = readable_ingested_file_ids(db, current_user, payload.project_id)
        allowed_file_ids = [
            row[0]
            for row in db.query(IngestedFile.id)
            .filter(
                IngestedFile.id.in_(readable_files),
                IngestedFile.index_status == rag.STATUS_READY,
            )
            .all()
        ] if readable_files else []

    try:
        retrieved = rag.retrieve(
            db,
            project_id=payload.project_id,
            readable_document_ids=allowed_ids,
            readable_ingested_file_ids=allowed_file_ids,
            query=payload.query,
            embedding_service=EmbeddingService(),
        )
        answer = AnswerService().answer(payload.query, retrieved)
    except EmbeddingError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    except AnswerError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))

    return RagQueryResponse(
        answer=answer.answer,
        found=answer.found,
        citations=[
            RagCitation(
                source_type=citation.source_type,
                document_id=citation.document_id,
                ingested_file_id=citation.ingested_file_id,
                title=citation.title,
                page=citation.page,
                snippet=citation.snippet,
            )
            for citation in answer.citations
        ],
        chunks_used=answer.chunks_used,
        route=routing.source.value if routing else "DOCUMENTS",
        route_reason=routing.reason if routing else "A specific document was named by the caller.",
        route_matched=routing.matched if routing else None,
    )


# --- Project re-indexing ----------------------------------------------------


def _reindex_status(db: Session, project_id, job) -> RagReindexStatus:
    """One run, plus what the project's corpus is actually embedded with.

    The summary is included even when there is no job, so a client can answer
    "is a re-index worth starting" without starting one.
    """
    summary = maintenance.project_reembedding_summary(db, project_id)
    if job is None:
        return RagReindexStatus(project_id=project_id, embedding_summary=summary)
    return RagReindexStatus(
        job_id=job.id,
        project_id=project_id,
        status=job.status,
        scope=job.scope,
        attempt=job.attempt,
        total_sources=job.total_sources,
        processed_sources=job.processed_sources,
        succeeded_sources=job.succeeded_sources,
        failed_sources=job.failed_sources,
        skipped_sources=job.skipped_sources,
        chunk_count=job.chunk_count,
        embedding_model=job.embedding_model,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=job.duration_ms,
        # The code, never `failure_message` — that carries internal detail and
        # stays on the row for an operator.
        failure_code=job.failure_code,
        embedding_summary=summary,
    )


def _assert_may_reindex(db: Session, project_id, current_user: User) -> None:
    """Project access, then the permission that governs the write.

    `document.upload` rather than `document.view`: a re-index spends embedding
    credits on every eligible source in the project, which is a write-shaped
    action even though it changes no content. It is the same code the unified
    ingestion retry endpoint requires, for the same reason.

    Project access is checked *first*, so somebody with no business here gets
    the project answer rather than a permission answer that confirms the
    project exists.
    """
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    require(db, current_user, "document.upload", project_id)


@router.post(
    "/projects/{project_id}/reindex",
    response_model=RagReindexStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def reindex_project(
    project_id: uuid.UUID,
    payload: RagReindexRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a re-index of a project's indexed sources.

    202, and it returns as soon as the job row exists: embedding a project's
    whole corpus inside a request handler is exactly what the shared bounded
    pool is for. The client polls the companion GET.

    Two refusals are possible and both are safe to publish — a run is already
    active for this project, or the scope selected more sources than one run is
    allowed to touch. Neither leaks anything about the project's contents.
    """
    _require_enabled()
    _assert_may_reindex(db, project_id, current_user)

    scope = (payload.scope if payload else None) or maintenance.SCOPE_STALE
    try:
        job = maintenance.request_project_reindex(
            db, project_id=project_id, requested_by_id=current_user.id, scope=scope,
        )
    except maintenance.ReindexRefused as refusal:
        code = (
            status.HTTP_409_CONFLICT
            if refusal.code == maintenance.ERROR_ALREADY_RUNNING
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=code, detail={"code": refusal.code, "message": refusal.detail},
        )

    record_audit(
        db, actor_id=current_user.id, action="rag_project_reindex_requested",
        entity_type="project", entity_id=project_id, project_id=project_id,
        details={"scope": scope, "sources": job.total_sources},
    )
    db.commit()
    db.refresh(job)
    payload_out = _reindex_status(db, project_id, job)
    # Submitted after the commit: a pool worker opens its own session and would
    # not see a row this transaction has not committed yet.
    maintenance.submit_project_reindex(job.id)
    return payload_out


@router.get("/projects/{project_id}/reindex", response_model=RagReindexStatus)
def project_reindex_status(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The most recent run for this project, and the corpus's embedding state.

    Readable by anybody who may open the project's documents — knowing that a
    re-index is running discloses nothing about what is in them.
    """
    _require_enabled()
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")
    require(db, current_user, "document.view", project_id)
    return _reindex_status(db, project_id, maintenance.latest_job(db, project_id))


def _availability(db: Session, project_id) -> SourceAvailability:
    """What this project actually holds, so routing cannot pick an empty source."""
    return SourceAvailability(
        documents=True,
        ifc=db.query(IFCModelVersion.id).filter(
            IFCModelVersion.project_id == project_id,
            IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
        ).first() is not None,
        site_reports=db.query(SiteReport.id).filter(
            SiteReport.project_id == project_id
        ).first() is not None,
        structured=True,
    )
