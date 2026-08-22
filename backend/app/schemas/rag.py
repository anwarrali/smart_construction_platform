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


class RagQueryRequest(CamelModel):
    project_id: UUID
    query: str = Field(min_length=3, max_length=2000)
    #: Optional narrowing to one document. When omitted, retrieval spans every
    #: document in the project that this user is permitted to read.
    document_id: Optional[UUID] = None


class RagCitation(CamelModel):
    document_id: UUID
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
