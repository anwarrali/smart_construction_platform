"""Wire shapes for RAG.

There is deliberately **no embedding field anywhere in this module**. Vectors
are internal to the store; exposing them would leak the document corpus in a
form that is trivially reconstructable and useful to nobody using the API. The
absence is structural — a response model with no such field cannot leak one by
accident, however the service layer changes.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class DocumentIndexStatus(CamelModel):
    document_id: UUID
    #: NOT_INDEXED | INDEXING | READY | FAILED
    status: str
    page_count: Optional[int] = None
    chunk_count: int = 0
    indexed_at: Optional[datetime] = None
    #: Why the last attempt failed, in words the user can act on.
    error: Optional[str] = None


class IngestedFileIndexStatus(CamelModel):
    """Indexing state of one file from the unified ingestion pipeline.

    A separate model from `DocumentIndexStatus` rather than a widened one:
    they name different things (`fileId` versus `documentId`) and this one
    carries two fields the document path has no notion of — what the ingestion
    pipeline extracted, and whether that makes the file indexable at all.
    Folding them together would give every existing client optional fields
    that never apply to it.
    """

    file_id: UUID
    #: NOT_INDEXED | INDEXING | READY | FAILED — the same four values, from the
    #: same state machine, as a document's.
    status: str
    #: What the ingestion pipeline obtained: TEXT, METADATA, PACKAGE, NONE, or
    #: null when processing has not settled yet.
    extraction: Optional[str] = None
    #: False for a scan, a drawing, a spreadsheet. Answered from the record
    #: above, so a client can hide the "index" action without a round trip
    #: that opens the file.
    indexable: bool = False
    #: Why not, when `indexable` is false. Null when it is true.
    not_indexable_reason: Optional[str] = None
    chunk_count: int = 0
    indexed_at: Optional[datetime] = None
    #: Why the last attempt failed, in words the user can act on.
    error: Optional[str] = None


class RagReindexRequest(CamelModel):
    """Which sources a project re-index should touch.

    Defaults to `STALE` deliberately: that is the model-change case, it is the
    cheapest, and it means the obvious call — post with no body — never spends
    embedding credits re-doing work that is already current.
    """

    #: STALE | FAILED | ALL. See `services/rag/maintenance.eligible_sources`.
    scope: str = Field(default="STALE", pattern="^(STALE|FAILED|ALL)$")


class RagReindexStatus(CamelModel):
    """One project re-index run, enough to know what is happening.

    Counts are written as the run progresses rather than at the end, so an
    interrupted run still reports how far it got.
    """

    job_id: Optional[UUID] = None
    project_id: UUID
    #: QUEUED | RUNNING | COMPLETED | PARTIAL | FAILED, or null when this
    #: project has never been re-indexed.
    status: Optional[str] = None
    scope: Optional[str] = None
    attempt: int = 0

    total_sources: int = 0
    processed_sources: int = 0
    succeeded_sources: int = 0
    failed_sources: int = 0
    #: Not attempted — already indexing elsewhere, or no longer indexable.
    #: Not a failure.
    skipped_sources: int = 0
    chunk_count: int = 0

    #: The model this run wrote with.
    embedding_model: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    #: A safe machine-readable code. The internal detail stays on the row.
    failure_code: Optional[str] = None

    #: What the project's corpus is currently embedded with, and how much of it
    #: disagrees with the configured model. Present so a client can decide
    #: whether a re-index is worth starting without starting one.
    embedding_summary: dict = {}


class RagQueryRequest(CamelModel):
    project_id: UUID
    query: str = Field(min_length=3, max_length=2000)
    #: Optional narrowing to one document. When omitted, retrieval spans every
    #: document in the project that this user is permitted to read.
    document_id: Optional[UUID] = None


class RagCitation(CamelModel):
    """A passage the answer was built from, naming exactly where it came from.

    Backwards compatible for the case that already existed: a citation from a
    library document still carries `documentId` populated exactly as before,
    and every field a client already read is unchanged. `sourceType` and
    `ingestedFileId` are additive.

    `documentId` became optional because a citation from an ingested file
    genuinely has none. A client can branch on `sourceType` rather than
    null-checking two fields — which is why `sourceType` is required and not
    inferred from which id happens to be set.
    """

    #: "DOCUMENT" or "INGESTED_FILE". Always present.
    source_type: str
    #: Set when `sourceType` is "DOCUMENT". Null otherwise.
    document_id: Optional[UUID] = None
    #: Set when `sourceType` is "INGESTED_FILE". Null otherwise.
    ingested_file_id: Optional[UUID] = None
    #: A document's title, or a file's original filename. Never a storage key.
    title: str
    page: int
    snippet: str


class RagQueryResponse(CamelModel):
    answer: str
    #: False when the retrieved passages did not support an answer. The client
    #: can present that differently from a real answer rather than having to
    #: pattern-match on the wording.
    found: bool
    citations: list[RagCitation]
    chunks_used: int
    #: Which source the question was routed to. "DOCUMENTS" means retrieval
    #: ran; anything else means it deliberately did not, because the project
    #: holds a better answer elsewhere. Additive: clients that ignore these
    #: three fields behave exactly as before.
    route: str = "DOCUMENTS"
    route_reason: Optional[str] = None
    #: The phrase that decided the route, so the decision can be explained.
    route_matched: Optional[str] = None
