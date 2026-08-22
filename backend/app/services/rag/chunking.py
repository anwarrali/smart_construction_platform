"""Cutting page text into retrieval-sized pieces.

Two rules, both of which exist to keep citations honest:

**A chunk never spans a page boundary.** Pages are chunked independently, so
every chunk has exactly one true page number. Merging pages first would make
retrieval marginally better at passages that straddle a page break and would
make every citation a guess — a bad trade in a system whose value is telling
someone *where* a clause is.

**Overlap is within a page only.** A chunk carries the tail of the previous
chunk so a sentence split across the boundary is still retrievable whole; that
tail is from the same page, so the page number stays true.

Tokens, not characters, because the retrieval budget and the embedding limit
are both counted in tokens. `tiktoken` when available, with a deterministic
word-based fallback so chunking — and its tests — work without it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings
from app.services.rag.pdf_text import PageText


@dataclass(frozen=True)
class Chunk:
    page_number: int
    chunk_index: int
    content: str
    token_count: int


@lru_cache(maxsize=4)
def _encoder(model: str):
    """The tokenizer for a model, or None to use the fallback.

    Cached because building one reads a vocabulary file, and indexing calls
    this once per chunk.
    """
    try:
        import tiktoken
    except ImportError:  # pragma: no cover - only in a build without tiktoken
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        # An unknown model name is not a reason to fail; cl100k_base is the
        # right encoding for every current OpenAI embedding model.
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def count_tokens(text: str, model: str | None = None) -> int:
    encoder = _encoder(model or settings.OPENAI_EMBEDDING_MODEL)
    if encoder is None:
        # Whitespace words are a systematic under-count of real tokens, so the
        # fallback deliberately over-estimates rather than risking a chunk
        # that exceeds the model's input limit.
        return max(1, int(len(text.split()) * 1.3))
    return len(encoder.encode(text))


def _split_tokens(text: str, model: str) -> tuple[list, object | None]:
    encoder = _encoder(model)
    if encoder is None:
        return text.split(), None
    return encoder.encode(text), encoder


def _join_tokens(pieces: list, encoder: object | None) -> str:
    if encoder is None:
        return " ".join(pieces)
    return encoder.decode(pieces)


def chunk_page(
    page: PageText,
    *,
    start_index: int,
    max_tokens: int | None = None,
    overlap: int | None = None,
    model: str | None = None,
) -> list[Chunk]:
    """Chunk one page. Never returns a chunk attributed to another page."""
    max_tokens = max_tokens or settings.RAG_CHUNK_TOKENS
    overlap = settings.RAG_CHUNK_OVERLAP if overlap is None else overlap
    model = model or settings.OPENAI_EMBEDDING_MODEL

    # Config validation already refuses overlap >= chunk size, but this
    # function is public and callable with explicit arguments; without the
    # clamp a bad pair would loop forever rather than fail.
    if overlap >= max_tokens:
        overlap = max_tokens // 4

    tokens, encoder = _split_tokens(page.text, model)
    if not tokens:
        return []

    chunks: list[Chunk] = []
    step = max_tokens - overlap
    position = 0
    index = start_index

    while position < len(tokens):
        window = tokens[position : position + max_tokens]
        content = _join_tokens(window, encoder).strip()
        if content:
            chunks.append(
                Chunk(
                    page_number=page.page_number,
                    chunk_index=index,
                    content=content,
                    token_count=len(window),
                )
            )
            index += 1
        # The final window is short; stop rather than emitting a chunk that is
        # entirely overlap of the one before it.
        if position + max_tokens >= len(tokens):
            break
        position += step

    return chunks


def chunk_pages(
    pages: list[PageText],
    *,
    max_tokens: int | None = None,
    overlap: int | None = None,
    model: str | None = None,
) -> list[Chunk]:
    """Chunk a whole document, numbering chunks continuously across pages."""
    chunks: list[Chunk] = []
    for page in pages:
        chunks.extend(
            chunk_page(
                page,
                start_index=len(chunks),
                max_tokens=max_tokens,
                overlap=overlap,
                model=model,
            )
        )
    return chunks
