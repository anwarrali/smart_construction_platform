"""Turning text into vectors, through the OpenAI client this project already uses.

Reuses the construction of `app.ai.construction_analysis_service` rather than
introducing a second OpenAI client: one place reads `OPENAI_API_KEY`, one place
sets the timeout, and no key is ever passed as an argument.

The service is a class taking an optional client so tests can inject a stub.
That is the same shape as `ConstructionVoiceAnalysisService`, and it is why the
whole test suite runs without an API key or a network.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger("uvicorn.error").getChild("rag.embeddings")

#: OpenAI rejects very large batches; this keeps requests comfortably inside
#: the limit while still amortising the round trip over many chunks.
BATCH_SIZE = 64


class EmbeddingError(Exception):
    """Embedding could not be produced. The message reaches `index_error`."""


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimension: int
    #: Prompt tokens reported by the provider, for `AIProviderCall`.
    total_tokens: int | None = None


class EmbeddingService:
    """Embeds text. Knows nothing about documents, chunks or storage."""

    def __init__(self, client: Any | None = None, model: str | None = None):
        self._client = client
        self._model = model or settings.OPENAI_EMBEDDING_MODEL

    @property
    def model(self) -> str:
        return self._model

    def _configured_client(self):
        if self._client is not None:
            return self._client
        # Imported here so this module can be imported — and unit-tested with
        # a stub — in an environment with no `openai` package installed.
        from app.ai.construction_analysis_service import OpenAI

        if not settings.OPENAI_API_KEY:
            raise EmbeddingError("OPENAI_API_KEY is not configured on this server")
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
        )
        return self._client

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a list of texts, preserving order.

        Order preservation is not incidental: the caller zips these vectors
        back onto its chunks positionally, so a reordered response would
        attach every chunk's text to another chunk's meaning — a corruption
        that produces plausible-looking nonsense rather than an error.
        """
        if not texts:
            return EmbeddingResult(vectors=[], model=self._model, dimension=0)

        client = self._configured_client()
        vectors: list[list[float]] = []
        total_tokens = 0
        started = time.monotonic()

        for offset in range(0, len(texts), BATCH_SIZE):
            batch = texts[offset : offset + BATCH_SIZE]
            try:
                response = client.embeddings.create(model=self._model, input=batch)
            except Exception as error:
                raise EmbeddingError(f"The embedding provider rejected the request: {error}")

            data = getattr(response, "data", None)
            if data is None or len(data) != len(batch):
                raise EmbeddingError("The embedding provider returned an unexpected response")
            # Sort by the provider's own index rather than trusting arrival
            # order — the API documents `index` precisely because order is not
            # guaranteed.
            ordered = sorted(data, key=lambda item: getattr(item, "index", 0))
            vectors.extend(list(item.embedding) for item in ordered)

            usage = getattr(response, "usage", None)
            if usage is not None:
                total_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)

        dimension = len(vectors[0]) if vectors else 0
        if any(len(vector) != dimension for vector in vectors):
            raise EmbeddingError("The embedding provider returned vectors of differing length")

        logger.debug(
            "embedded %s text(s) with %s in %.0fms",
            len(texts), self._model, (time.monotonic() - started) * 1000,
        )
        return EmbeddingResult(
            vectors=vectors,
            model=self._model,
            dimension=dimension,
            total_tokens=total_tokens or None,
        )

    def embed_one(self, text: str) -> list[float]:
        result = self.embed([text])
        if not result.vectors:
            raise EmbeddingError("The embedding provider returned no vector")
        return result.vectors[0]
