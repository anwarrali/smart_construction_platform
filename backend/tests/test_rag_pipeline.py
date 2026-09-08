"""The RAG pipeline: extraction, chunking, embeddings, similarity, retrieval, answering.

No test in this file makes a network call. `EmbeddingService` and
`AnswerService` both take an injectable client, so a stub is passed in
everywhere — the suite runs with no OPENAI_API_KEY and costs nothing.

The properties under test are the ones that make an answer trustworthy:
a chunk always knows its true page, retrieval never crosses a project or a
permission boundary, and an unsupported question produces a refusal rather
than a fabrication.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentType, ProjectStatus, UserRole, UserStatus
from app.models.project import Project
from app.models.user import User
from app.services.rag import answering, chunking, ingestion
from app.services.rag.answering import (
    NOT_FOUND_MESSAGE, NOT_FOUND_TOKEN, AnswerService, build_context,
)
from app.services.rag.chunking import chunk_page, chunk_pages, count_tokens
from app.services.rag.embeddings import EmbeddingError, EmbeddingService
from app.services.rag.pdf_text import (
    DocumentTextError, PageText, assert_indexable, extract_pages, resolve_upload_path,
)
from app.services.rag.retrieval import RetrievedChunk, retrieve
from tests.pdf_fixture import build_pdf
from app.services.rag.store import (
    ChunkSource, PgVectorStore, PreparedChunk, ScoredChunk, VectorDimensionMismatch,
)
from tests.embedding_stub import StubEmbeddingClient

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")


# --- stubs ------------------------------------------------------------------


# The embedding stub lives in `tests/embedding_stub.py`: the `embedding`
# column is `vector(N)`, so every stub has to agree with
# `RAG_EMBEDDING_DIMENSIONS`, and three copies of that agreement was three
# places to forget it.
_StubEmbeddingClient = StubEmbeddingClient


class _StubAnswerClient:
    """A chat client that returns whatever it was told to."""

    def __init__(self, reply: str):
        self._reply = reply
        self.chat = self
        self.completions = self
        self.last_messages = None

    def create(self, model, messages, temperature=None):
        self.last_messages = messages
        return _StubCompletion(self._reply)


class _StubCompletion:
    def __init__(self, content):
        self.choices = [_StubChoice(content)]


class _StubChoice:
    def __init__(self, content):
        self.message = _StubMessage(content)


class _StubMessage:
    def __init__(self, content):
        self.content = content


def _embedding_service() -> EmbeddingService:
    return EmbeddingService(client=_StubEmbeddingClient(), model="stub-embedding")


# --- fixtures ---------------------------------------------------------------


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _make_pdf(path: Path, pages: list[str]) -> Path:
    """A real multi-page PDF with known text per page.

    Built by hand (see `tests/pdf_fixture`) rather than with reportlab, so the
    suite gains no dependency for a fixture — and it is a genuine PDF, so the
    extractor is actually exercised rather than mocked.
    """
    return build_pdf(path, pages)


# --- PDF page extraction ----------------------------------------------------


def test_pages_are_extracted_separately_and_keep_their_numbers(tmp_path):
    """Page identity is what makes a citation checkable."""
    path = _make_pdf(tmp_path / "spec.pdf", [
        "Page one covers concrete curing times.",
        "Page two covers retention and payment terms.",
        "Page three covers safety helmet requirements.",
    ])
    pages = extract_pages(path)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert "curing" in pages[0].text
    assert "retention" in pages[1].text
    assert "helmet" in pages[2].text


def test_a_non_pdf_is_refused_before_parsing(tmp_path):
    """mime_type is client-supplied; the magic bytes are not."""
    fake = tmp_path / "notreally.pdf"
    fake.write_bytes(b"PK\x03\x04 this is a zip file")
    with pytest.raises(DocumentTextError, match="Only PDF documents"):
        assert_indexable(fake)


def test_an_oversized_file_is_refused_with_the_limit_named(tmp_path, monkeypatch):
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-1.4" + b"0" * 2_000_000)
    monkeypatch.setattr("app.services.rag.pdf_text.settings.RAG_MAX_FILE_MB", 1)
    with pytest.raises(DocumentTextError, match="indexing limit"):
        assert_indexable(big)


def test_a_scanned_pdf_says_so_instead_of_failing_vaguely(tmp_path):
    """The most common real failure deserves the most actionable message."""
    path = _make_pdf(tmp_path / "scan.pdf", ["", ""])
    with pytest.raises(DocumentTextError, match="no extractable text layer"):
        extract_pages(path)


def test_file_url_resolves_under_the_upload_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.rag.pdf_text.settings.UPLOAD_DIR", str(tmp_path))
    resolved = resolve_upload_path("http://localhost:8000/uploads/documents/abc.pdf")
    assert resolved == (tmp_path / "documents/abc.pdf").resolve()


def test_a_traversing_file_url_is_refused(monkeypatch, tmp_path):
    """The value is ours, but a guard that only runs on untrusted input rots."""
    monkeypatch.setattr("app.services.rag.pdf_text.settings.UPLOAD_DIR", str(tmp_path))
    with pytest.raises(DocumentTextError, match="outside the upload directory"):
        resolve_upload_path("http://localhost:8000/uploads/../../etc/passwd")


# --- chunking ---------------------------------------------------------------


def test_a_chunk_never_spans_two_pages():
    """The rule the whole citation guarantee rests on."""
    pages = [
        PageText(page_number=1, text=" ".join(["alpha"] * 400)),
        PageText(page_number=2, text=" ".join(["beta"] * 400)),
    ]
    chunks = chunk_pages(pages, max_tokens=100, overlap=10)

    for chunk in chunks:
        words = set(chunk.content.split())
        assert not ({"alpha"} < words and {"beta"} < words), "a chunk mixed two pages"
    assert {chunk.page_number for chunk in chunks} == {1, 2}


def test_chunks_are_numbered_continuously_across_pages():
    pages = [
        PageText(page_number=1, text=" ".join(["alpha"] * 300)),
        PageText(page_number=2, text=" ".join(["beta"] * 300)),
    ]
    chunks = chunk_pages(pages, max_tokens=100, overlap=10)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunks_respect_the_token_budget():
    page = PageText(page_number=1, text=" ".join(["word"] * 1000))
    chunks = chunk_page(page, start_index=0, max_tokens=120, overlap=20)
    assert chunks, "expected at least one chunk"
    assert all(chunk.token_count <= 120 for chunk in chunks)


def test_overlap_carries_context_between_neighbouring_chunks():
    page = PageText(page_number=1, text=" ".join(str(n) for n in range(400)))
    chunks = chunk_page(page, start_index=0, max_tokens=100, overlap=25)
    assert len(chunks) > 1
    first_tail = set(chunks[0].content.split()[-25:])
    second_head = set(chunks[1].content.split()[:25])
    assert first_tail & second_head, "overlap did not carry any shared tokens"


def test_a_pathological_overlap_cannot_loop_forever():
    """Overlap >= chunk size would never advance the window."""
    page = PageText(page_number=1, text=" ".join(["word"] * 300))
    chunks = chunk_page(page, start_index=0, max_tokens=50, overlap=50)
    assert chunks and len(chunks) < 100


def test_an_empty_page_produces_no_chunks():
    assert chunk_page(PageText(page_number=1, text="   "), start_index=0) == []


def test_token_counting_is_positive_for_real_text():
    assert count_tokens("retention is five per cent of each payment") > 0


# --- embedding service ------------------------------------------------------


def test_the_embedding_service_preserves_input_order():
    """Vectors are zipped back onto chunks positionally; order is correctness."""
    service = _embedding_service()
    result = service.embed(["concrete concrete", "retention", "safety helmet"])

    assert len(result.vectors) == 3
    vocab = _StubEmbeddingClient.VOCAB
    assert result.vectors[0][vocab.index("concrete")] == 2.0
    assert result.vectors[1][vocab.index("retention")] == 1.0
    assert result.vectors[2][vocab.index("helmet")] == 1.0


def test_the_embedding_service_reorders_by_provider_index():
    """The API documents `index` precisely because arrival order is not fixed."""

    class _ShuffledClient(_StubEmbeddingClient):
        def create(self, model, input):  # noqa: A002
            response = super().create(model, input)
            response.data = list(reversed(response.data))
            return response

    service = EmbeddingService(client=_ShuffledClient(), model="stub")
    vocab = _StubEmbeddingClient.VOCAB
    result = service.embed(["concrete", "retention"])
    assert result.vectors[0][vocab.index("concrete")] == 1.0
    assert result.vectors[1][vocab.index("retention")] == 1.0


def test_a_provider_failure_becomes_an_embedding_error():
    class _FailingClient:
        def __init__(self):
            self.embeddings = self

        def create(self, model, input):  # noqa: A002
            raise RuntimeError("upstream is down")

    with pytest.raises(EmbeddingError, match="rejected the request"):
        EmbeddingService(client=_FailingClient(), model="stub").embed(["anything"])


def test_embedding_nothing_calls_no_provider():
    client = _StubEmbeddingClient()
    result = EmbeddingService(client=client, model="stub").embed([])
    assert result.vectors == [] and client.calls == 0


# The `cosine_similarity` tests stood here. The function is gone: pgvector
# computes the distance and PostgreSQL does the ordering, so a Python
# implementation would be dead code and a test of it would be a test of
# nothing the application runs. `test_the_store_returns_the_most_relevant_
# chunk_first` below covers the behaviour that mattered.


# --- vector store -----------------------------------------------------------


@pytest.fixture()
def world(db):
    """Two projects with one document each, so isolation is testable."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        full_name=f"RagUser{suffix}",
        email=f"raguser.{suffix}@constro.io",
        hashed_password="x",
        role=UserRole.PROJECT_MANAGER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()

    def project(name):
        item = Project(
            name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
            owner_id=user.id, project_manager_id=user.id,
        )
        db.add(item)
        db.flush()
        return item

    def document(project_item, title):
        doc = Document(
            project_id=project_item.id,
            uploaded_by_id=user.id,
            title=title,
            document_type=DocumentType.CONTRACT,
            file_url=f"http://localhost:8000/uploads/documents/{uuid.uuid4().hex}.pdf",
        )
        db.add(doc)
        db.flush()
        return doc

    project_a, project_b = project("Alpha"), project("Beta")
    return {
        "user": user,
        "project_a": project_a,
        "project_b": project_b,
        "doc_a": document(project_a, "Alpha Contract"),
        "doc_b": document(project_b, "Beta Contract"),
    }


def _store_chunks(db, store, document, texts, service=None):
    service = service or _embedding_service()
    embedded = service.embed(texts)
    prepared = [
        PreparedChunk(
            page_number=index + 1, chunk_index=index,
            content=content, token_count=len(content.split()), embedding=vector,
        )
        for index, (content, vector) in enumerate(zip(texts, embedded.vectors))
    ]
    return store.add_chunks(
        db,
        source=ChunkSource.from_document(document.id),
        project_id=document.project_id,
        chunks=prepared,
        embedding_model=embedded.model,
        embedding_dim=embedded.dimension,
    )


def test_the_store_returns_the_most_relevant_chunk_first(db, world):
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_a"], [
        "Concrete curing shall continue for seven days.",
        "Retention is five per cent of each interim payment.",
        "Every worker shall wear a safety helmet.",
    ])
    service = _embedding_service()
    results = store.search(
        db,
        project_id=world["project_a"].id,
        readable_document_ids=[world["doc_a"].id],
        readable_ingested_file_ids=[],
        query_embedding=service.embed_one("what is the retention percentage"),
        k=3,
    )
    assert results
    assert "Retention" in results[0].content
    assert results[0].page_number == 2


def test_the_store_never_crosses_a_project_boundary(db, world):
    """The outer boundary: a valid document id in the wrong project finds nothing."""
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_b"], ["Retention is ten per cent in project Beta."])
    service = _embedding_service()

    leaked = store.search(
        db,
        project_id=world["project_a"].id,          # project A ...
        readable_document_ids=[world["doc_b"].id],  # ... but project B's document
        readable_ingested_file_ids=[],
        query_embedding=service.embed_one("retention"),
        k=5,
    )
    assert leaked == []


def test_an_empty_readable_set_retrieves_nothing(db, world):
    """A user permitted to read no documents must not fall through to all."""
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_a"], ["Retention is five per cent."])
    service = _embedding_service()
    assert store.search(
        db, project_id=world["project_a"].id, readable_document_ids=[],
        readable_ingested_file_ids=[],
        query_embedding=service.embed_one("retention"), k=5,
    ) == []


def test_storing_again_replaces_rather_than_appends(db, world):
    """Re-indexing must not leave the previous run's text retrievable."""
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_a"], ["First version of the clause."])
    _store_chunks(db, store, world["doc_a"], ["Second version.", "Another chunk."])
    db.flush()

    remaining = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["doc_a"].id
    ).all()
    assert len(remaining) == 2
    assert all("First version" not in chunk.content for chunk in remaining)


def test_a_vector_of_the_wrong_width_cannot_be_stored_at_all(db, world):
    """What used to be a read-time skip is now a write-time refusal.

    The JSONB column accepted any length and `search` skipped rows whose width
    differed from the query's, because comparing across two embedding spaces
    produces confident nonsense. `vector(1536)` makes those rows
    unrepresentable, which is strictly stronger: the bad state cannot be
    reached rather than being tolerated and filtered.
    """
    store = PgVectorStore()
    with pytest.raises(VectorDimensionMismatch) as refusal:
        store.add_chunks(
            db,
            source=ChunkSource.from_document(world["doc_a"].id),
            project_id=world["project_a"].id,
            chunks=[PreparedChunk(page_number=1, chunk_index=0, content="x",
                                  token_count=1, embedding=[0.1, 0.2])],
            embedding_model="some-other-model",
            embedding_dim=2,
        )
    assert "requires a schema migration" in str(refusal.value)
    db.rollback()


def test_a_query_of_the_wrong_width_retrieves_nothing_rather_than_erroring(db, world):
    """A search endpoint must not 500 because the corpus was embedded by a
    different model. Refusing returns no answer, which is the truth."""
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_a"], ["Retention is five per cent."])
    db.flush()
    assert store.search(
        db, project_id=world["project_a"].id,
        readable_document_ids=[world["doc_a"].id], readable_ingested_file_ids=[],
        query_embedding=[0.1, 0.2], k=5,
    ) == []


def test_delete_source_removes_every_chunk(db, world):
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_a"], ["one", "two", "three"])
    db.flush()
    assert store.delete_source(
        db, source=ChunkSource.from_document(world["doc_a"].id)
    ) == 3
    assert ingestion.chunk_count(db, world["doc_a"].id) == 0


# --- retrieval --------------------------------------------------------------


def test_retrieval_attaches_the_document_title_for_citations(db, world):
    store = PgVectorStore()
    _store_chunks(db, store, world["doc_a"], ["Retention is five per cent of each payment."])
    db.flush()

    results = retrieve(
        db,
        project_id=world["project_a"].id,
        readable_document_ids=[world["doc_a"].id],
        readable_ingested_file_ids=[],
        query="retention percentage",
        embedding_service=_embedding_service(),
        store=store,
    )
    assert results and results[0].source_title == "Alpha Contract"
    assert results[0].source_type == "DOCUMENT"


def test_retrieval_with_no_readable_documents_returns_nothing(db, world):
    assert retrieve(
        db, project_id=world["project_a"].id, readable_document_ids=[],
        readable_ingested_file_ids=[],
        query="anything", embedding_service=_embedding_service(), store=PgVectorStore(),
    ) == []


# --- answering and citations ------------------------------------------------


def _retrieved(document_id, title="Alpha Contract", page=14, content="Retention is 5%."):
    return RetrievedChunk(
        chunk=ScoredChunk(
            chunk_id=uuid.uuid4(), source=ChunkSource.from_document(document_id),
            page_number=page, chunk_index=0, content=content, score=0.9,
        ),
        source_title=title,
    )


def test_a_grounded_answer_carries_citations_to_the_retrieved_page():
    document_id = uuid.uuid4()
    chunks = [_retrieved(document_id, page=14)]
    service = AnswerService(client=_StubAnswerClient("Retention is 5% [1]."), model="stub")

    result = service.answer("What is the retention?", chunks)

    assert result.found is True
    assert result.chunks_used == 1
    assert len(result.citations) == 1
    citation = result.citations[0]
    assert citation.document_id == document_id
    assert citation.page == 14
    assert citation.title == "Alpha Contract"


def test_citations_can_only_reference_retrieved_chunks():
    """The core anti-hallucination property.

    The model is made to claim a page that was never retrieved. Because
    citations are built from the chunk records rather than parsed from prose,
    the invented page cannot appear.
    """
    document_id = uuid.uuid4()
    chunks = [_retrieved(document_id, page=14)]
    liar = _StubAnswerClient("Retention is 5% as stated on page 99 [7].")
    result = AnswerService(client=liar, model="stub").answer("retention?", chunks)

    assert [citation.page for citation in result.citations] == [14]
    assert all(citation.document_id == document_id for citation in result.citations)


def test_the_snippet_comes_from_the_chunk_it_cites():
    document_id = uuid.uuid4()
    content = "Retention shall be five per cent of the value of work executed."
    chunks = [_retrieved(document_id, content=content)]
    result = AnswerService(client=_StubAnswerClient("Five per cent [1]."), model="stub").answer(
        "retention?", chunks
    )
    assert result.citations[0].snippet in content or content.startswith(
        result.citations[0].snippet.rstrip("…")
    )


def test_an_unsupported_question_reports_not_found():
    """The sentinel path: a refusal must be unambiguous, not phrased."""
    chunks = [_retrieved(uuid.uuid4())]
    service = AnswerService(client=_StubAnswerClient(NOT_FOUND_TOKEN), model="stub")

    result = service.answer("What is the site manager's shoe size?", chunks)

    assert result.found is False
    assert result.answer == NOT_FOUND_MESSAGE
    assert result.citations == []


def test_no_retrieved_chunks_short_circuits_without_calling_the_model():
    """An empty context is an invitation to improvise; do not extend it."""
    client = _StubAnswerClient("this should never be returned")
    result = AnswerService(client=client, model="stub").answer("anything", [])

    assert result.found is False
    assert result.answer == NOT_FOUND_MESSAGE
    assert result.chunks_used == 0
    assert client.last_messages is None, "the model was called with no context"


def test_the_prompt_forbids_outside_knowledge_and_demands_citations():
    """Grounding is a prompt contract; assert the contract is actually sent."""
    chunks = [_retrieved(uuid.uuid4())]
    client = _StubAnswerClient("Answer [1].")
    AnswerService(client=client, model="stub").answer("retention?", chunks)

    system = client.last_messages[0]["content"]
    assert "ONLY from the numbered context" in system
    assert "Never use general knowledge" in system
    assert NOT_FOUND_TOKEN in system
    assert "Every factual claim must carry a citation" in system


def test_the_context_names_the_document_and_page_of_each_passage():
    chunks = [_retrieved(uuid.uuid4(), title="Main Contract", page=7)]
    context = build_context(chunks)
    assert "[1]" in context and "Main Contract" in context and "page 7" in context
