"""Turning retrieved passages into an answer that can be trusted.

The design constraint that shapes everything here: on a construction contract,
a confident wrong answer is worse than no answer. Someone acts on "retention is
10%" without checking. So three separate mechanisms push toward grounding, and
none of them relies on the model choosing to behave:

1. **The prompt forbids outside knowledge** and requires an explicit
   not-found response.
2. **Citations are built from the retrieved chunk records**, never parsed out
   of the model's prose. A citation therefore *cannot* point at a page that
   was not retrieved — the model has no channel to invent one.
3. **`found` is computed, not claimed.** If nothing was retrieved, the answer
   is the not-found message and no model call is made at all.

The model is asked to mark an unsupported answer with a sentinel token rather
than being trusted to phrase a refusal consistently, because "I could not find
that" and "The document does not specify" and a plausible fabrication are hard
to tell apart downstream. A sentinel is unambiguous.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from app.core.config import settings
from app.services.rag.retrieval import RetrievedChunk

logger = logging.getLogger("uvicorn.error").getChild("rag.answering")

#: What the model emits when the context does not support an answer.
NOT_FOUND_TOKEN = "INSUFFICIENT_CONTEXT"

#: What the user sees in that case.
NOT_FOUND_MESSAGE = (
    "That information was not found in the indexed documents."
)

SYSTEM_PROMPT = """You answer questions about construction project documents.

Rules, in order of importance:

1. Answer ONLY from the numbered context passages provided in the user message.
2. Never use general knowledge, industry norms, or assumptions to fill a gap.
   If the passages do not contain the answer, you do not know it.
3. If the passages do not support an answer, reply with exactly this token and
   nothing else: {token}
4. When you do answer, cite the passages you used inline as [1], [2], matching
   the numbers given. Every factual claim must carry a citation.
5. Do not invent figures, dates, clause numbers, or names. If a value is
   partially stated, say exactly what is stated and no more.
6. Be concise and specific. Quote the document's own wording for numbers,
   percentages and deadlines rather than paraphrasing them.
""".format(token=NOT_FOUND_TOKEN)


@dataclass(frozen=True)
class Citation:
    document_id: uuid.UUID
    title: str
    page: int
    snippet: str


@dataclass(frozen=True)
class Answer:
    answer: str
    found: bool
    citations: list[Citation]
    chunks_used: int


class AnswerError(Exception):
    """The answering model could not be reached or returned nothing usable."""


def build_context(chunks: Sequence[RetrievedChunk]) -> str:
    """The numbered passages the model may use, and nothing else.

    Each block names its document and page so the model can cite precisely,
    and so a human reading the prompt in a log can verify the answer's basis.
    """
    blocks = []
    for position, item in enumerate(chunks, start=1):
        blocks.append(
            f"[{position}] Document: {item.document_title} — page {item.chunk.page_number}\n"
            f"{item.chunk.content}"
        )
    return "\n\n".join(blocks)


def _snippet(text: str, limit: int = 300) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def _citations_from(chunks: Sequence[RetrievedChunk]) -> list[Citation]:
    """Citations built from the retrieved records themselves.

    Deliberately not derived from the model's output: parsing [1] markers out
    of prose would let a hallucinated marker become a citation, which is the
    exact failure this system exists to prevent. Over-citing a passage the
    model did not lean on is a far cheaper error than citing a page that was
    never retrieved.
    """
    return [
        Citation(
            document_id=item.chunk.document_id,
            title=item.document_title,
            page=item.chunk.page_number,
            snippet=_snippet(item.chunk.content),
        )
        for item in chunks
    ]


class AnswerService:
    """Generates a grounded answer. Client injectable, so tests need no network."""

    def __init__(self, client: Any | None = None, model: str | None = None):
        self._client = client
        self._model = model or settings.OPENAI_RAG_MODEL

    @property
    def model(self) -> str:
        return self._model

    def _configured_client(self):
        if self._client is not None:
            return self._client
        from app.ai.construction_analysis_service import OpenAI

        if not settings.OPENAI_API_KEY:
            raise AnswerError("OPENAI_API_KEY is not configured on this server")
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
        return self._client

    def answer(self, question: str, chunks: Sequence[RetrievedChunk]) -> Answer:
        # Nothing retrieved means nothing to ground an answer in. Saying so
        # without calling the model is both cheaper and safer: a model given
        # an empty context is being invited to improvise.
        if not chunks:
            return Answer(
                answer=NOT_FOUND_MESSAGE, found=False, citations=[], chunks_used=0
            )

        context = build_context(chunks)
        user_message = (
            f"Context passages:\n\n{context}\n\n"
            f"Question: {question.strip()}\n\n"
            f"Answer using only the passages above."
        )

        client = self._configured_client()
        started = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                # Low but not zero: deterministic enough to be reproducible,
                # without the degenerate repetition greedy decoding can show.
                temperature=0.1,
            )
        except Exception as error:
            raise AnswerError(f"The answering model could not be reached: {error}")

        try:
            text = (response.choices[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError):
            raise AnswerError("The answering model returned an unexpected response")

        latency = int((time.monotonic() - started) * 1000)
        logger.debug("rag answer in %sms using %s chunk(s)", latency, len(chunks))

        if not text:
            raise AnswerError("The answering model returned an empty response")

        # The sentinel may arrive alone or wrapped in a sentence; either way it
        # means the same thing, and the user gets our wording rather than the
        # model's.
        if NOT_FOUND_TOKEN in text:
            return Answer(
                answer=NOT_FOUND_MESSAGE,
                found=False,
                citations=[],
                chunks_used=len(chunks),
            )

        return Answer(
            answer=text,
            found=True,
            citations=_citations_from(chunks),
            chunks_used=len(chunks),
        )
