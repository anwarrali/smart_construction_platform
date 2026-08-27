"""Wire shapes for routed project-knowledge answers.

A citation here can point at a document page, a project record or an IFC
finding, so it carries `source_type` rather than assuming a document. Every
citation is built from a record the server actually retrieved — never parsed
out of model prose — so what it points at can be opened and checked.
"""

from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.user import CamelModel


class KnowledgeQueryRequest(CamelModel):
    query: str = Field(min_length=3, max_length=2000)
    #: "en" or "ar". Structured answers are already phrased in both; this
    #: chooses which one is returned.
    language: Optional[str] = None


class KnowledgeCitation(CamelModel):
    #: DOCUMENT | PROJECT_RECORD | IFC_ELEMENT | IFC_COORDINATION_FINDING
    source_type: str
    source_id: str
    title: str
    snippet: str
    #: Documents only.
    page: Optional[int] = None
    #: The facts behind the citation, for sources that carry structured
    #: evidence — an interference finding's measured overlap, for instance.
    evidence: dict[str, Any] = {}


class KnowledgeQueryResponse(CamelModel):
    answer: str
    #: False when the routed source held no answer. Distinct from an error:
    #: the right place was consulted and had nothing.
    found: bool
    citations: list[KnowledgeCitation]
    #: Which source answered, why it was chosen, and the phrase that decided
    #: it — so a routing decision can be explained rather than guessed at.
    source: str
    route_reason: str
    route_matched: Optional[str] = None
    #: The `VoiceQueryTopic` used, when the source had one.
    topic: Optional[str] = None
    #: Structured facts behind a project-record answer, for a client that
    #: would rather render numbers than a sentence.
    data: dict[str, Any] = {}
