"""Retrieval-augmented question answering over project documents.

Layered so that each concern can be replaced without disturbing the others:

    pdf_text    PDF on disk  -> text, one page at a time
    chunking    page text    -> token-bounded, page-tagged chunks
    embeddings  text         -> vectors (OpenAI, client injectable)
    store       vectors      -> storage + similarity, behind `VectorStore`
    ingestion   orchestrates the above, owns the indexing state machine
    retrieval   question     -> top-k chunks, within an authorized scope
    answering   chunks       -> grounded answer + citations

`store` is the only module that knows vectors are kept in JSONB. Swapping in
pgvector means writing one more `VectorStore` and changing one factory line.
"""

from app.services.rag.answering import Answer, AnswerError, AnswerService, Citation
from app.services.rag.chunking import Chunk, chunk_pages, count_tokens
from app.services.rag.embeddings import EmbeddingError, EmbeddingService
from app.services.rag.ingestion import (
    STATUS_FAILED,
    STATUS_INDEXING,
    STATUS_NOT_INDEXED,
    STATUS_READY,
    IndexingFailed,
    IndexingInProgress,
    chunk_count,
    index_document,
)
from app.services.rag.pdf_text import DocumentTextError, PageText, extract_pages
from app.services.rag.retrieval import RetrievedChunk, retrieve
from app.services.rag.store import (
    JsonbVectorStore,
    PreparedChunk,
    ScoredChunk,
    VectorStore,
    cosine_similarity,
    get_vector_store,
)

__all__ = [
    "Answer", "AnswerError", "AnswerService", "Citation",
    "Chunk", "chunk_pages", "count_tokens",
    "EmbeddingError", "EmbeddingService",
    "STATUS_FAILED", "STATUS_INDEXING", "STATUS_NOT_INDEXED", "STATUS_READY",
    "IndexingFailed", "IndexingInProgress", "chunk_count", "index_document",
    "DocumentTextError", "PageText", "extract_pages",
    "RetrievedChunk", "retrieve",
    "JsonbVectorStore", "PreparedChunk", "ScoredChunk", "VectorStore",
    "cosine_similarity", "get_vector_store",
]
