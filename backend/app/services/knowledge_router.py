"""Deciding *where* a question should be answered from, before answering it.

`POST /rag/query` embeds every question and searches the document vectors,
whatever the question was. Ask it "what is the project progress?" and it
searches contract PDFs, because searching is the only thing it can do. The
nearest passage is returned regardless of whether it has anything to do with
progress, and the answering layer is left to notice.

That is the wrong shape for a platform that already holds the answer to most
project questions as structured data. Progress is a number in the tasks table.
The latest site report is a row. What conflicts with a beam is a coordination
finding with measured evidence. None of those are improved by being turned into
a similarity search over PDFs, and injecting unrelated passages into the prompt
makes a grounded answer *less* likely, not more.

So routing happens first, and it is deterministic. The platform's own rule
holds here: AI decides intent, the backend decides authorization and
execution — and picking a data source is closer to execution than to intent.
Deterministic routing is also inspectable: every decision carries the phrase
that produced it.

The topic taxonomy is **not** reinvented. `VoiceQueryTopic` already enumerates
the questions the backend can answer from project data, and
`voice_query_service.answer_query` already answers them. This module maps a
question onto that taxonomy where one fits, so a typed question and a spoken
one reach the same answer through the same code.

Two behaviours matter more than accuracy:

  * **When unsure, documents.** A question this module cannot place is left to
    document retrieval, which is where it went before. Routing may only take
    work *away* from the vector store when it is confident something better
    exists, never on a guess.

  * **A source is never invented.** Routing to IFC on a project with no model
    would be worse than not routing at all, so availability is checked before
    a source is chosen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.schemas.voice_analysis import VoiceQueryTopic


class KnowledgeSource(str, Enum):
    """Where an answer can come from."""

    #: Counted, summed or looked up from tasks/issues/milestones.
    PROJECT_STRUCTURED = "PROJECT_STRUCTURED"
    #: The filed site-report record, not a summary of the project.
    SITE_REPORTS = "SITE_REPORTS"
    #: Elements, spatial structure and coordination findings from IFC.
    IFC_MODEL = "IFC_MODEL"
    #: Indexed document passages, retrieved by similarity.
    DOCUMENTS = "DOCUMENTS"


def _normalise(value: str | None) -> str:
    return " ".join(re.findall(r"[\w]+", str(value or "").casefold(), flags=re.UNICODE))


_ARABIC = re.compile(r"[؀-ۿ]")


def _phrase(text: str, phrase: str) -> bool:
    """Whole-phrase match, tolerating Arabic's attached definite article.

    Arabic writes "the conflict" as one token, `التعارض`, so a plain word
    boundary around `تعارض` never matches the form people actually type. An
    optional `ال` prefix is allowed on Arabic phrases; English is unaffected.
    """
    normalised = _normalise(phrase)
    if not normalised:
        return False
    prefix = "(?:ال)?" if _ARABIC.search(normalised) else ""
    return bool(re.search(rf"(?<!\w){prefix}{re.escape(normalised)}(?!\w)", text))


#: Question wording → the source that holds the answer, and the existing
#: `VoiceQueryTopic` to hand it to when one applies. English and Arabic, because
#: the platform is used in both and a router that only understood one would
#: silently send every Arabic question to the vector store.
#:
#: Ordered most specific first: "site report" must beat "report", and a
#: question about a clash must reach the model rather than the drawings.
ROUTES: list[tuple[KnowledgeSource, VoiceQueryTopic | None, tuple[str, ...]]] = [
    (KnowledgeSource.IFC_MODEL, None, (
        "clash", "clashes", "conflict with", "conflicts with", "interference",
        "intersect", "intersects",
        # Both forms: a question asks "does the duct *pass* through", a
        # statement says "the duct *passes* through".
        "pass through", "passes through", "run through", "runs through",
        "ifc", "bim model", "model element", "coordination finding",
        "تعارض", "تصادم", "تداخل", "يمر خلال", "عنصر في النموذج", "النموذج ثلاثي الأبعاد",
    )),
    (KnowledgeSource.SITE_REPORTS, VoiceQueryTopic.LATEST_SITE_REPORT, (
        "latest site report", "last site report", "site report", "daily report",
        "آخر تقرير موقع", "تقرير الموقع", "التقرير اليومي", "آخر تقرير",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.PROJECT_PROGRESS, (
        "project progress", "overall progress", "how far along", "percent complete",
        "percentage complete", "completion percentage",
        "تقدم المشروع", "نسبة الإنجاز", "نسبة الانجاز", "وين وصلنا",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.OPEN_ISSUES, (
        "open issues", "outstanding issues", "current issues", "any issues",
        "المشاكل المفتوحة", "المشاكل الحالية", "المشاكل",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.BLOCKED_TASKS, (
        "blocked tasks", "what is blocked", "which tasks are blocked",
        "المهام المتوقفة", "المهام المعلقة",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.REMAINING_TASKS, (
        "remaining tasks", "tasks left", "what is left", "outstanding tasks",
        "المهام المتبقية", "شو باقي",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.IN_PROGRESS_TASKS, (
        "in progress tasks", "tasks in progress", "ongoing tasks",
        "المهام الجارية", "المهام قيد التنفيذ",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.COMPLETED_TASKS, (
        "completed tasks", "finished tasks", "done tasks",
        "المهام المنجزة", "المهام المكتملة",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.NOT_STARTED_TASKS, (
        "not started", "tasks not started", "unstarted tasks",
        "المهام غير المبدوءة", "لم تبدأ",
    )),
    (KnowledgeSource.PROJECT_STRUCTURED, VoiceQueryTopic.NEXT_TASK, (
        "next task", "what should i do next", "what is next",
        "المهمة التالية", "شو بعدين",
    )),
    (KnowledgeSource.DOCUMENTS, None, (
        "specification", "spec says", "the contract says", "clause", "according to the contract",
        "bill of quantities", "boq", "drawing says", "method statement", "datasheet",
        "المواصفات", "العقد", "بند", "جدول الكميات", "كراسة الشروط",
    )),
]

#: Wording that asks about something *inside* a document even when the question
#: also mentions a structured subject. "What does the specification say about
#: the concrete grade for this task" is a document question, not a task lookup.
#: Every phrase here must be about *text* — what something says, states or is
#: written in. Generic question openers were tried and removed: "does the" made
#: "does the duct pass through the beam" a document question, which is exactly
#: the kind of confident wrong turn routing must not take.
DOCUMENT_INTENT = (
    "say about", "says about", "stated in", "written in", "as written",
    "according to", "clause", "section",
    "ماذا تقول", "شو بتقول", "منصوص", "مكتوب في",
)


@dataclass(frozen=True)
class RoutingDecision:
    """Which source should answer, and the wording that decided it."""

    source: KnowledgeSource
    #: The existing voice topic to delegate to, when the source has one.
    topic: VoiceQueryTopic | None
    confidence: float
    #: The phrase that matched, so a decision can be explained and audited.
    matched: str | None
    reason: str
    #: Sources considered and rejected because the project does not have them.
    unavailable: list[str] = field(default_factory=list)

    @property
    def needs_document_retrieval(self) -> bool:
        return self.source is KnowledgeSource.DOCUMENTS

    def as_json(self) -> dict:
        return {
            "source": self.source.value,
            "topic": self.topic.value if self.topic else None,
            "confidence": self.confidence,
            "matched": self.matched,
            "reason": self.reason,
            "unavailable": self.unavailable,
        }


@dataclass(frozen=True)
class SourceAvailability:
    """What this project actually holds. Routing never picks an empty source."""

    documents: bool = True
    ifc: bool = False
    site_reports: bool = False
    structured: bool = True


DEFAULT_AVAILABILITY = SourceAvailability()

_AVAILABLE_ATTRIBUTE = {
    KnowledgeSource.DOCUMENTS: "documents",
    KnowledgeSource.IFC_MODEL: "ifc",
    KnowledgeSource.SITE_REPORTS: "site_reports",
    KnowledgeSource.PROJECT_STRUCTURED: "structured",
}


def route_question(
    question: str,
    *,
    availability: SourceAvailability = DEFAULT_AVAILABILITY,
) -> RoutingDecision:
    """Pick the source that should answer, or fall back to documents.

    Falling back is the safe direction: document retrieval is what happened to
    every question before this existed, so an unrouted question behaves exactly
    as it always did. Routing only ever redirects *away* from the vector store
    on a confident match against an available source.
    """
    text = _normalise(question)
    if not text:
        return RoutingDecision(
            KnowledgeSource.DOCUMENTS, None, 0.0, None,
            "No question text; nothing to route on.",
        )

    # A question that asks what a document *says* is a document question, even
    # when it also names a task or a material.
    asks_what_a_document_says = any(_phrase(text, hint) for hint in DOCUMENT_INTENT)

    unavailable: list[str] = []
    for source, topic, phrases in ROUTES:
        match = next((phrase for phrase in phrases if _phrase(text, phrase)), None)
        if not match:
            continue
        if source is not KnowledgeSource.DOCUMENTS and asks_what_a_document_says:
            # The subject is structured but the question is about wording.
            continue
        if not getattr(availability, _AVAILABLE_ATTRIBUTE[source]):
            unavailable.append(source.value)
            continue
        return RoutingDecision(
            source=source, topic=topic, confidence=0.85, matched=match,
            reason=f"The question says {match!r}, which this project answers from {source.value}.",
            unavailable=unavailable,
        )

    return RoutingDecision(
        source=KnowledgeSource.DOCUMENTS, topic=None, confidence=0.3, matched=None,
        reason=(
            "Nothing identified a better source, so the question goes to document "
            "retrieval — the same place every question went before routing existed."
        ),
        unavailable=unavailable,
    )
