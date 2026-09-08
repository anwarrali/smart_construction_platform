"""Retrieval-augmented question answering over project documents.

Layered so that each concern can be replaced without disturbing the others:

    pdf_text    PDF on disk  -> text, one page at a time
    text_source IngestedFile -> the same, reusing the ingestion processors
    chunking    page text    -> token-bounded, page-tagged chunks
    embeddings  text         -> vectors (OpenAI, client injectable)
    store       vectors      -> pgvector storage + similarity, behind `VectorStore`
    ingestion   orchestrates the above, owns the indexing state machine
    retrieval   question     -> top-k chunks, within an authorized scope
    answering   chunks       -> grounded answer + citations

`store` is the only module that knows how vectors are kept. That is what made
the move from JSONB to pgvector one new class and one factory line, with no
change to ingestion, retrieval, answering or the API.
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
    NotIndexable,
    chunk_count,
    index_document,
    index_ingested_file,
    index_ingested_file_job,
    ingested_file_chunk_count,
    submit_ingested_file_index,
)
from app.services.rag.pdf_text import DocumentTextError, PageText, extract_pages
from app.services.rag.retrieval import RetrievedChunk, retrieve
from app.services.rag.text_source import EXTRACTION_TEXT, is_indexable, why_not_indexable
from app.services.rag.store import (
    ChunkSource,
    PgVectorStore,
    PreparedChunk,
    ScoredChunk,
    VectorDimensionMismatch,
    VectorStore,
    get_vector_store,
)

__all__ = [
    "Answer", "AnswerError", "AnswerService", "Citation",
    "Chunk", "chunk_pages", "count_tokens",
    "EmbeddingError", "EmbeddingService",
    "STATUS_FAILED", "STATUS_INDEXING", "STATUS_NOT_INDEXED", "STATUS_READY",
    "IndexingFailed", "IndexingInProgress", "NotIndexable",
    "chunk_count", "index_document",
    "index_ingested_file", "index_ingested_file_job", "ingested_file_chunk_count",
    "submit_ingested_file_index",
    "EXTRACTION_TEXT", "is_indexable", "why_not_indexable",
    "DocumentTextError", "PageText", "extract_pages",
    "RetrievedChunk", "retrieve",
    "ChunkSource", "PgVectorStore", "PreparedChunk", "ScoredChunk",
    "VectorDimensionMismatch", "VectorStore", "get_vector_store",
]
