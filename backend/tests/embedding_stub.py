"""A deterministic embedding client, shared by every RAG test.

## Why it is shared

Three test modules had their own copy, each with a slightly different
vocabulary. That was tolerable while vectors were JSONB and any width would
store. It is not now: the `embedding` column is `vector(N)`, so every stub has
to agree with `RAG_EMBEDDING_DIMENSIONS` or its inserts are rejected — and
three copies of that agreement is three places to forget it.

## Why the vectors are padded rather than short

`vector(1536)` accepts exactly 1536 numbers. The meaningful part of these
vectors is still one dimension per vocabulary word, so a question about
"retention" genuinely scores higher against the passage that mentions
retention and the retrieval assertions stay meaningful rather than tautological.
The remaining dimensions are zeros.

Padding with zeros is mathematically inert for cosine similarity: a zero
contributes nothing to the dot product and nothing to either norm, so the
ranking over the padded vectors is identical to the ranking over the short
ones. The tests that assert `vector[VOCAB.index("concrete")] == 2.0` also keep
working, because the padding goes on the end.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.rag.embeddings import EmbeddingService

#: The union of every word the RAG test modules rely on. One list, so a test
#: can be moved between modules without silently losing its signal.
VOCAB = [
    "retention", "payment", "concrete", "curing", "safety", "helmet",
    "penalty", "delay", "warranty", "defect", "insurance", "scaffold",
]

#: The name recorded in `embedding_model`. Distinct from any real model, so a
#: row written by a test is recognisable in the database.
STUB_MODEL = "stub-embed"


def dimensions() -> int:
    """The width the column expects, read at call time.

    Not captured at import: a test may vary the setting, and a stub that
    disagreed with the column would fail as an opaque driver error rather than
    as the thing under test.
    """
    return settings.RAG_EMBEDDING_DIMENSIONS


def vector_for(text: str) -> list[float]:
    """One dimension per vocabulary word, zero-padded to the column width."""
    lowered = text.lower()
    counts = [float(lowered.count(word)) for word in VOCAB]
    # A non-zero tail so an input sharing no vocabulary is still a valid unit
    # vector rather than an all-zero one, which has no direction and would make
    # cosine similarity meaningless.
    counts.append(1.0)
    return counts + [0.0] * max(0, dimensions() - len(counts))


class _Item:
    def __init__(self, index: int, embedding: list[float]):
        self.index = index
        self.embedding = embedding


class _Usage:
    def __init__(self, total: int):
        self.total_tokens = total


class _Response:
    def __init__(self, data: list[_Item]):
        self.data = data
        self.usage = _Usage(10 * len(data))


class StubEmbeddingClient:
    """Shaped like the OpenAI client, with no network and no key."""

    VOCAB = VOCAB

    def __init__(self):
        # The OpenAI client exposes `.embeddings.create`; this object is both.
        self.embeddings = self
        self.calls = 0

    def create(self, model, input):  # noqa: A002 - the OpenAI kwarg is named `input`
        self.calls += 1
        return _Response([_Item(i, vector_for(item)) for i, item in enumerate(input)])


def stub_embedding_service(client: StubEmbeddingClient | None = None) -> EmbeddingService:
    return EmbeddingService(client=client or StubEmbeddingClient(), model=STUB_MODEL)


def zero_vector() -> list[float]:
    """A storable vector for tests that need a row but not a meaningful one."""
    return [0.0] * dimensions()
