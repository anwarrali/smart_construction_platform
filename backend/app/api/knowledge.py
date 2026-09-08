"""One question, routed to whichever source actually holds the answer.

This is the entry point Phase 4 calls RAG 2.0, and it is mostly *not* new code.
Structured project questions go to `voice_query_service.answer_query`, which
already answers them for the voice assistant. Document questions go to
`rag.retrieve`, which already retrieves them. IFC questions go to
`ifc_knowledge`, which is the one source that had no query path. Routing is the
part that was missing, not the answering.

Reusing the voice answering path is deliberate beyond saving code: a typed
question and a spoken one now reach the same facts through the same function,
so the two interfaces cannot drift into disagreeing about the project.

Authorization is unchanged and is never widened here. Structured answers are
built from the caller's already-authorized task list, document retrieval is
scoped to the document ids they may read, and IFC needs the same `VIEW`
permission the IFC workspace requires.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, user_has_project_access
from app.db.database import get_db
from app.models.document import Document
from app.models.ifc import IFCModelVersion
from app.models.ingestion import IngestedFile
from app.models.site_report import SiteReport
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeCitation,
    KnowledgeQueryRequest,
    KnowledgeQueryResponse,
)
from app.schemas.voice_analysis import DetectedQuery
from app.services import rag
from app.services.document_access import (
    readable_document_ids, readable_ingested_file_ids,
)
from app.services.ifc_knowledge import answer_ifc_question
from app.services.ifc_policy import can_ifc
from app.services.knowledge_router import KnowledgeSource, SourceAvailability, route_question
from app.services.rag.answering import AnswerError, AnswerService
from app.services.rag.embeddings import EmbeddingError, EmbeddingService
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_query_service import answer_query

router = APIRouter(prefix="/projects/{project_id}/knowledge", tags=["Project Knowledge"])


def _availability(db: Session, project_id: uuid.UUID, user: User) -> SourceAvailability:
    """What this project holds *and* this caller may see.

    Availability is per-caller, not just per-project: routing a question to the
    model for someone who cannot open the model would produce a refusal where a
    document answer was available.
    """
    return SourceAvailability(
        documents=True,
        ifc=can_ifc(db, user, project_id, "VIEW") and db.query(IFCModelVersion.id).filter(
            IFCModelVersion.project_id == project_id,
            IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
        ).first() is not None,
        site_reports=db.query(SiteReport.id).filter(SiteReport.project_id == project_id).first() is not None,
        structured=True,
    )


@router.post("/query", response_model=KnowledgeQueryResponse)
def query_project_knowledge(
    project_id: uuid.UUID,
    payload: KnowledgeQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a project question from the source that holds the answer."""
    if not user_has_project_access(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this project")

    routing = route_question(payload.query, availability=_availability(db, project_id, current_user))
    handlers = {
        KnowledgeSource.PROJECT_STRUCTURED: _answer_structured,
        KnowledgeSource.SITE_REPORTS: _answer_structured,
        KnowledgeSource.IFC_MODEL: _answer_ifc,
        KnowledgeSource.DOCUMENTS: _answer_documents,
    }
    return handlers[routing.source](db, project_id, current_user, payload, routing)


def _response(routing, *, answer: str, found: bool, citations=None, **extra) -> KnowledgeQueryResponse:
    return KnowledgeQueryResponse(
        answer=answer, found=found, citations=citations or [],
        source=routing.source.value, route_reason=routing.reason,
        route_matched=routing.matched, topic=routing.topic.value if routing.topic else None,
        **extra,
    )


def _answer_structured(db, project_id, user, payload, routing) -> KnowledgeQueryResponse:
    """Delegate to the answering the voice assistant already uses.

    `authorized_voice_tasks` is the same scoping the voice pipeline applies, so
    a typed question can never see work a spoken one could not — and
    `answer_query` never widens the list it is handed.
    """
    tasks = authorized_voice_tasks(db, user, project_id)
    answer = answer_query(
        db, user=user, project_id=project_id,
        query=DetectedQuery(topic=routing.topic, confidence=routing.confidence),
        tasks=tasks, spoken=payload.query,
    ) if routing.topic else None

    if not answer or not answer.is_answered:
        return _response(
            routing, found=False,
            answer=(
                "That question routes to project records, but no answer could be "
                "built from the data available to you."
            ),
        )
    return _response(
        routing, answer=answer.text_for(payload.language), found=True,
        citations=[KnowledgeCitation(
            source_type="PROJECT_RECORD", source_id=str(project_id),
            title="Project records", snippet=answer.text_en[:400],
        )],
        data=answer.data,
    )


def _answer_ifc(db, project_id, user, payload, routing) -> KnowledgeQueryResponse:
    if not can_ifc(db, user, project_id, "VIEW"):
        raise HTTPException(status_code=403, detail="IFC view permission required")
    result = answer_ifc_question(db, project_id=project_id, question=payload.query)
    if not result.found:
        # "No conflicts" and "no model to look in" are different answers, and
        # the reason says which one this is.
        return _response(routing, answer=result.unavailable_reason or "No model facts matched.", found=False)
    return _response(
        routing,
        answer=" ".join(fact.statement for fact in result.facts[:5]),
        found=True,
        citations=[KnowledgeCitation(
            source_type=fact.source_type, source_id=fact.source_id,
            title=result.resolved_subject or "IFC model", snippet=fact.statement[:400],
            evidence=fact.evidence,
        ) for fact in result.facts],
    )


def _answer_documents(db, project_id, user, payload, routing) -> KnowledgeQueryResponse:
    """Both indexed sources, each scoped by its own authorization rule.

    `KnowledgeCitation` was already polymorphic — `source_type` plus
    `source_id` — so an ingested file needed no schema change here. Leaving
    this route documents-only would have meant the same question answered
    through `/knowledge/query` and `/rag/query` giving two different answers.
    """
    readable = readable_document_ids(db, user, project_id)
    allowed = [
        row[0] for row in db.query(Document.id).filter(
            Document.id.in_(readable), Document.index_status == rag.STATUS_READY,
        ).all()
    ] if readable else []
    readable_files = readable_ingested_file_ids(db, user, project_id)
    allowed_files = [
        row[0] for row in db.query(IngestedFile.id).filter(
            IngestedFile.id.in_(readable_files),
            IngestedFile.index_status == rag.STATUS_READY,
        ).all()
    ] if readable_files else []
    if not allowed and not allowed_files:
        return _response(
            routing, found=False,
            answer="No indexed documents are available to you in this project.",
        )
    try:
        retrieved = rag.retrieve(
            db, project_id=project_id, readable_document_ids=allowed,
            readable_ingested_file_ids=allowed_files,
            query=payload.query, embedding_service=EmbeddingService(),
        )
        answer = AnswerService().answer(payload.query, retrieved)
    except (EmbeddingError, AnswerError) as error:
        raise HTTPException(status_code=503, detail=str(error))
    return _response(
        routing, answer=answer.answer, found=answer.found,
        citations=[KnowledgeCitation(
            source_type=citation.source_type,
            source_id=str(citation.document_id or citation.ingested_file_id),
            title=citation.title, snippet=citation.snippet, page=citation.page,
        ) for citation in answer.citations],
    )
