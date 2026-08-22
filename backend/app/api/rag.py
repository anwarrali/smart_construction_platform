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
from app.models.user import User
from app.schemas.rag import (
    DocumentIndexStatus,
    RagCitation,
    RagQueryRequest,
    RagQueryResponse,
)
from app.services import rag
from app.services.document_access import assert_document_readable, readable_document_ids
from app.services.rag.answering import AnswerError, AnswerService
from app.services.rag.embeddings import EmbeddingError, EmbeddingService

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
    else:
        # Every document in the project this user may read — resolved from the
        # same rules the documents API applies, then narrowed to those that
        # are actually indexed.
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

    try:
        retrieved = rag.retrieve(
            db,
            project_id=payload.project_id,
            readable_document_ids=allowed_ids,
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
                document_id=citation.document_id,
                title=citation.title,
                page=citation.page,
                snippet=citation.snippet,
            )
            for citation in answer.citations
        ],
        chunks_used=answer.chunks_used,
    )
