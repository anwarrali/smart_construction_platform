"""Indexing a file from the unified ingestion pipeline.

The properties under test are the ones that make this integration safe rather
than merely working:

* **The gate is the pipeline's own verdict.** A scan is refused without the
  file being opened, because the ingestion pipeline already opened it once and
  wrote down what it found.
* **Unindexable is not failed.** A drawing that will never yield text leaves
  no error and no changed status, so it cannot be mistaken for something a
  retry might fix.
* **Two sources, one state machine.** Document chunks and ingested-file chunks
  coexist, each knows exactly one parent, and neither path can produce a chunk
  with no source or two.
* **Re-indexing cannot duplicate.** The delete-then-insert is inside the
  caller's transaction, so an interrupted run rolls back to the previous state
  rather than to an empty one.
* **A project boundary is not crossable.** Chunks carry the project of the
  file they came from, and a file in another project is not even visible.

No test here makes a network call: `EmbeddingService` takes an injectable
client, so a deterministic stub is passed in everywhere.
"""

from __future__ import annotations

import io
import zipfile
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import rag as rag_api
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentType, ProjectStatus, UserRole, UserStatus
from app.models.ingestion import IngestedFile
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.rag import ingestion, text_source
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.pdf_text import DocumentTextError
from app.services.rag.store import ChunkSource, PgVectorStore
from tests.embedding_stub import STUB_MODEL, StubEmbeddingClient, zero_vector
from tests.pdf_fixture import build_pdf

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")


# --- stubs ------------------------------------------------------------------


class _FailingEmbeddingClient:
    def __init__(self):
        self.embeddings = self

    def create(self, model, input):  # noqa: A002
        raise RuntimeError("the embedding provider is unreachable")


def _embeddings(client=None) -> EmbeddingService:
    return EmbeddingService(client=client or StubEmbeddingClient(), model=STUB_MODEL)


# --- world ------------------------------------------------------------------


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


@pytest.fixture()
def world(db, tmp_path, monkeypatch):
    suffix = uuid4().hex[:10]
    private = tmp_path / "private"
    private.mkdir()
    monkeypatch.setattr(settings, "PRIVATE_UPLOAD_DIR", str(private))
    monkeypatch.setenv("PRIVATE_UPLOAD_DIR", str(private))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(settings, "RAG_ENABLED", True)

    manager = User(full_name="RagPm", email=f"ragpm-{suffix}@example.com",
                   hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    outsider = User(full_name="RagOther", email=f"ragother-{suffix}@example.com",
                    hashed_password="x", role=UserRole.PROJECT_MANAGER, status=UserStatus.ACTIVE)
    owner = User(full_name="RagOwner", email=f"ragowner-{suffix}@example.com",
                 hashed_password="x", role=UserRole.OWNER, status=UserStatus.ACTIVE)
    db.add_all([manager, outsider, owner])
    db.flush()

    project = Project(name=f"Rag {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=manager.id)
    other = Project(name=f"Rag other {suffix}", status=ProjectStatus.ACTIVE,
                    owner_id=owner.id, project_manager_id=outsider.id)
    db.add_all([project, other])
    db.flush()
    db.add_all([
        ProjectMember(project_id=project.id, user_id=manager.id,
                      role_on_project=UserRole.PROJECT_MANAGER, is_active=True),
        ProjectMember(project_id=other.id, user_id=outsider.id,
                      role_on_project=UserRole.PROJECT_MANAGER, is_active=True),
    ])
    db.commit()
    try:
        yield {"project": project, "other": other, "manager": manager,
               "outsider": outsider, "owner": owner, "tmp": tmp_path}
    finally:
        _purge(db, [project.id, other.id], [manager.id, outsider.id, owner.id])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM document_chunks WHERE project_id = ANY(:projects)",
        "DELETE FROM ingestion_jobs WHERE file_id IN "
        "(SELECT id FROM ingested_files WHERE project_id = ANY(:projects))",
        "UPDATE ingested_files SET parent_file_id = NULL, duplicate_of_id = NULL "
        "WHERE project_id = ANY(:projects)",
        "DELETE FROM ingested_files WHERE project_id = ANY(:projects)",
        "DELETE FROM documents WHERE project_id = ANY(:projects)",
        "DELETE FROM ai_provider_calls WHERE project_id = ANY(:projects)",
        "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
        "DELETE FROM project_members WHERE project_id = ANY(:projects) OR user_id = ANY(:users)",
        "DELETE FROM projects WHERE id = ANY(:projects)",
        "DELETE FROM users WHERE id = ANY(:users)",
    ):
        try:
            db.execute(text(statement), params)
        except SQLAlchemyError:
            db.rollback()
    db.commit()


# --- builders ---------------------------------------------------------------


def _write(world, key: str, payload: bytes) -> str:
    from app.services.private_storage import LocalFilesystemStorage

    with LocalFilesystemStorage().writable_local_path(key) as target:
        target.write_bytes(payload)
    return key


def make_file(db, world, *, category="PDF", extraction="TEXT", payload=None,
              project=None, filename="specification.pdf", details=None) -> IngestedFile:
    """An ingested file exactly as the pipeline would have left it."""
    project = project or world["project"]
    key = _write(world, f"ingest/{uuid4()}_{filename}", payload or b"%PDF-1.7\n")
    file = IngestedFile(
        project_id=project.id,
        uploaded_by_id=world["manager"].id,
        original_filename=filename,
        normalized_filename=filename,
        file_category=category,
        detected_format=category,
        file_size_bytes=len(payload or b"%PDF-1.7\n"),
        storage_key=key,
        status="READY",
        processor_name=category.lower(),
        metadata_json={
            "processor": category.lower(),
            "category": category,
            "extraction": extraction,
            "details": details or {},
        },
    )
    db.add(file)
    db.commit()
    return file


def pdf_file(db, world, pages, **kwargs) -> IngestedFile:
    payload = build_pdf(world["tmp"] / f"{uuid4().hex}.pdf", pages).read_bytes()
    return make_file(db, world, category="PDF", extraction="TEXT",
                     payload=payload, **kwargs)


def docx_file(db, world, paragraphs, **kwargs) -> IngestedFile:
    buffer = io.BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in paragraphs)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document><w:body>{body}</w:body></w:document>',
        )
    return make_file(db, world, category="DOCX", extraction="TEXT",
                     payload=buffer.getvalue(), filename="method-statement.docx", **kwargs)


def make_document(db, world, title="Alpha Contract") -> Document:
    path = build_pdf(world["tmp"] / f"{uuid4().hex}.pdf",
                     ["Retention is five per cent of each interim payment."])
    relative = f"documents/{uuid4()}_{path.name}"
    target = world["tmp"] / "uploads" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(path.read_bytes())
    document = Document(
        project_id=world["project"].id, uploaded_by_id=world["manager"].id,
        title=title, document_type=DocumentType.CONTRACT,
        file_url=f"http://testserver/uploads/{relative}",
    )
    db.add(document)
    db.commit()
    return document


def index(db, file, **kwargs):
    return ingestion.index_ingested_file(
        db, file, embedding_service=_embeddings(), store=PgVectorStore(), **kwargs
    )


def chunks_of(db, file) -> list[DocumentChunk]:
    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.ingested_file_id == file.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )


# --- The gate: what may be indexed at all -----------------------------------

def test_a_text_pdf_is_indexed_and_reports_its_pages_and_chunks(db, world):
    file = pdf_file(db, world, ["Retention is five per cent.", "Concrete curing rules."])
    result = index(db, file)

    assert result.status == ingestion.STATUS_READY
    assert result.source == "INGESTED_FILE"
    assert result.document_id == file.id
    assert result.page_count == 2
    assert result.chunk_count >= 2
    assert result.indexed_at is not None

    db.refresh(file)
    assert file.index_status == ingestion.STATUS_READY
    assert file.indexed_at is not None
    assert file.index_error is None


def test_a_word_document_is_indexed_as_a_single_citable_page(db, world):
    """A Word file has no pages until something renders it. Page 1 is where a
    reader opening it would find the passage, which is what a citation means."""
    file = docx_file(db, world, ["METHOD STATEMENT", "Concrete pour sequence."])
    result = index(db, file)

    assert result.status == ingestion.STATUS_READY
    assert result.page_count == 1
    stored = chunks_of(db, file)
    assert stored
    assert {chunk.page_number for chunk in stored} == {1}
    assert "Concrete pour sequence" in " ".join(chunk.content for chunk in stored)


@pytest.mark.parametrize(
    "category,extraction",
    [
        ("DRAWING", "NONE"),
        ("XLSX", "METADATA"),
        ("ZIP_PACKAGE", "PACKAGE"),
        ("IMAGE", "NONE"),
        ("IFC", "METADATA"),
    ],
)
def test_a_file_with_no_extracted_text_is_refused_without_being_opened(
    db, world, category, extraction, monkeypatch
):
    """The pipeline already opened it once. Reopening to re-decide would be
    paying twice for an answer that is already on the record."""
    file = make_file(db, world, category=category, extraction=extraction)

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("the file must not be opened to decide indexability")

    monkeypatch.setattr(text_source, "pages_for", explode)

    with pytest.raises(ingestion.NotIndexable) as refusal:
        index(db, file)
    assert "cannot be indexed" in str(refusal.value)


def test_being_unindexable_is_not_a_failure_and_leaves_no_trace(db, world):
    """A drawing will never yield text. Recording a failure would make it look
    like something a retry could fix, and would put an error on a healthy row."""
    file = make_file(db, world, category="DRAWING", extraction="NONE")
    with pytest.raises(ingestion.NotIndexable):
        index(db, file)

    db.refresh(file)
    assert file.index_status == ingestion.STATUS_NOT_INDEXED
    assert file.index_error is None
    assert file.indexed_at is None


def test_a_file_that_has_not_finished_processing_says_so(db, world):
    file = make_file(db, world, category="PDF", extraction=None)
    file.metadata_json = {}
    db.commit()
    assert text_source.is_indexable(file) is False
    assert "not finished processing" in text_source.why_not_indexable(file)


def test_a_text_verdict_for_a_format_with_no_reader_is_refused_loudly(db, world):
    """A processor gaining text extraction without a reader being added here
    is a bug worth surfacing, not a reason to index an empty string."""
    file = make_file(db, world, category="XLSX", extraction="TEXT")
    assert text_source.is_indexable(file) is False
    assert "not supported yet" in text_source.why_not_indexable(file)


def test_the_reason_carries_the_processors_own_limitation_when_it_has_one(db, world):
    file = make_file(
        db, world, category="DRAWING", extraction="NONE",
        details={"limitation": "DWG is a closed binary format."},
    )
    assert "closed binary format" in text_source.why_not_indexable(file)


# --- Failure handling -------------------------------------------------------

def test_a_scanned_pdf_fails_with_a_reason_a_person_can_act_on(db, world):
    """`extraction` said TEXT, but the bytes turned out unreadable. That IS a
    failure — something was attempted — unlike a file the pipeline already
    knew had no text."""
    file = pdf_file(db, world, [""])
    with pytest.raises(ingestion.IndexingFailed) as failure:
        index(db, file)

    db.refresh(file)
    assert file.index_status == ingestion.STATUS_FAILED
    assert file.index_error
    assert "text layer" in file.index_error or "no readable" in file.index_error.lower()
    assert file.indexed_at is None
    assert str(failure.value)
    assert chunks_of(db, file) == []


def test_a_missing_stored_object_fails_rather_than_crashing(db, world):
    from app.services.private_storage import private_storage

    file = pdf_file(db, world, ["Retention is five per cent."])
    private_storage.delete(file.storage_key)

    with pytest.raises(ingestion.IndexingFailed):
        index(db, file)
    db.refresh(file)
    assert file.index_status == ingestion.STATUS_FAILED
    assert file.index_error


def test_an_embedding_provider_failure_is_recorded_and_retryable(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    with pytest.raises(ingestion.IndexingFailed):
        ingestion.index_ingested_file(
            db, file,
            embedding_service=_embeddings(_FailingEmbeddingClient()),
            store=PgVectorStore(),
        )
    db.refresh(file)
    assert file.index_status == ingestion.STATUS_FAILED
    assert file.index_error
    assert chunks_of(db, file) == []

    # And the retry works, which is what makes FAILED distinct from NOT_INDEXABLE.
    result = index(db, file)
    assert result.status == ingestion.STATUS_READY
    db.refresh(file)
    assert file.index_error is None
    assert chunks_of(db, file)


def test_a_failed_run_never_leaves_the_row_looking_indexed(db, world):
    file = pdf_file(db, world, [""])
    with pytest.raises(ingestion.IndexingFailed):
        index(db, file)
    db.refresh(file)
    # FAILED with no indexed_at, and no chunks. Every other combination would
    # let retrieval treat a half-written index as usable.
    assert (file.index_status, file.indexed_at) == (ingestion.STATUS_FAILED, None)


# --- Status transitions -----------------------------------------------------

def test_a_new_file_starts_not_indexed(db, world):
    file = make_file(db, world)
    assert file.index_status == ingestion.STATUS_NOT_INDEXED
    assert file.indexed_at is None
    assert file.index_error is None


def test_a_second_run_is_refused_while_one_is_under_way(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    db.execute(
        text("UPDATE ingested_files SET index_status = 'INDEXING' WHERE id = :id"),
        {"id": file.id},
    )
    db.commit()

    with pytest.raises(ingestion.IndexingInProgress):
        index(db, file)


def test_force_recovers_a_row_stranded_by_an_interrupted_run(db, world):
    """The one case the concurrency guard cannot tell from a live run."""
    file = pdf_file(db, world, ["Retention is five per cent."])
    db.execute(
        text("UPDATE ingested_files SET index_status = 'INDEXING' WHERE id = :id"),
        {"id": file.id},
    )
    db.commit()

    result = index(db, file, force=True)
    assert result.status == ingestion.STATUS_READY
    db.refresh(file)
    assert file.index_status == ingestion.STATUS_READY


def test_re_indexing_clears_a_previous_error(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    db.execute(
        text("UPDATE ingested_files SET index_status='FAILED', index_error='old' WHERE id=:id"),
        {"id": file.id},
    )
    db.commit()
    index(db, file)
    db.refresh(file)
    assert file.index_error is None


# --- Chunk provenance -------------------------------------------------------

def test_chunks_from_a_file_name_the_file_and_never_a_document(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    index(db, file)

    stored = chunks_of(db, file)
    assert stored
    for chunk in stored:
        assert chunk.ingested_file_id == file.id
        assert chunk.document_id is None
        assert chunk.project_id == world["project"].id
        # chunk → ingested_file → project, answerable without a join guess.
        assert chunk.source_id == file.id


def test_the_two_kinds_of_chunk_coexist_in_the_same_project(db, world):
    document = make_document(db, world)
    ingestion.index_document(
        db, document, embedding_service=_embeddings(), store=PgVectorStore()
    )
    file = pdf_file(db, world, ["Concrete curing shall continue for seven days."])
    index(db, file)

    document_chunks = (
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
    )
    file_chunks = chunks_of(db, file)
    assert document_chunks and file_chunks

    # Each names exactly one parent, and they are different parents.
    assert all(chunk.ingested_file_id is None for chunk in document_chunks)
    assert all(chunk.document_id is None for chunk in file_chunks)
    assert ingestion.chunk_count(db, document.id) == len(document_chunks)
    assert ingestion.ingested_file_chunk_count(db, file.id) == len(file_chunks)


def test_a_chunk_with_no_source_is_rejected_by_the_database(db, world):
    """The CHECK constraint, not a convention. Application code can be wrong."""
    db.add(DocumentChunk(
        project_id=world["project"].id, page_number=1, chunk_index=0,
        content="orphan", token_count=1, embedding=zero_vector(),
        embedding_model="stub", embedding_dim=len(zero_vector()),
    ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_a_chunk_claiming_two_sources_is_rejected_by_the_database(db, world):
    document = make_document(db, world)
    file = make_file(db, world)
    db.add(DocumentChunk(
        document_id=document.id, ingested_file_id=file.id,
        project_id=world["project"].id, page_number=1, chunk_index=0,
        content="two parents", token_count=1, embedding=zero_vector(),
        embedding_model="stub", embedding_dim=len(zero_vector()),
    ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_chunk_source_value_object_refuses_the_same_two_mistakes():
    with pytest.raises(ValueError):
        ChunkSource()
    with pytest.raises(ValueError):
        ChunkSource(document_id=uuid4(), ingested_file_id=uuid4())
    assert ChunkSource.from_document(uuid4()).kind == "DOCUMENT"
    assert ChunkSource.from_ingested_file(uuid4()).kind == "INGESTED_FILE"


def test_deleting_a_file_takes_its_chunks_with_it(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    index(db, file)
    assert chunks_of(db, file)

    file_id = file.id
    db.execute(text("DELETE FROM ingested_files WHERE id = :id"), {"id": file_id})
    db.commit()
    assert db.query(DocumentChunk).filter(
        DocumentChunk.ingested_file_id == file_id).count() == 0


# --- Idempotency ------------------------------------------------------------

def test_indexing_the_same_file_twice_does_not_duplicate_chunks(db, world):
    file = pdf_file(db, world, ["Retention is five per cent.", "Concrete curing."])
    first = index(db, file)
    second = index(db, file)

    assert first.chunk_count == second.chunk_count
    assert len(chunks_of(db, file)) == second.chunk_count


def test_re_indexing_replaces_the_previous_text_rather_than_adding_to_it(db, world):
    """A corrected file must stop answering from its outdated text."""
    file = docx_file(db, world, ["First version of the clause."])
    index(db, file)
    assert any("First version" in chunk.content for chunk in chunks_of(db, file))

    # The stored object is replaced, as a re-upload would.
    _write(world, file.storage_key, _docx_bytes(["Second version of the clause."]))
    index(db, file)

    remaining = chunks_of(db, file)
    assert remaining
    assert all("First version" not in chunk.content for chunk in remaining)
    assert any("Second version" in chunk.content for chunk in remaining)


def _docx_bytes(paragraphs) -> bytes:
    buffer = io.BytesIO()
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in paragraphs)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document><w:body>{body}</w:body></w:document>',
        )
    return buffer.getvalue()


def test_a_failed_second_run_removes_the_first_runs_chunks(db, world):
    """A stale index is worse than no index: it answers, and it is wrong."""
    file = pdf_file(db, world, ["Retention is five per cent."])
    index(db, file)
    assert chunks_of(db, file)

    with pytest.raises(ingestion.IndexingFailed):
        ingestion.index_ingested_file(
            db, file,
            embedding_service=_embeddings(_FailingEmbeddingClient()),
            store=PgVectorStore(),
        )
    db.refresh(file)
    assert file.index_status == ingestion.STATUS_FAILED
    assert chunks_of(db, file) == []


def test_indexing_one_file_leaves_another_files_chunks_alone(db, world):
    first = pdf_file(db, world, ["Retention is five per cent."])
    second = pdf_file(db, world, ["Concrete curing shall continue."])
    index(db, first)
    index(db, second)
    index(db, first)

    assert chunks_of(db, first)
    assert chunks_of(db, second)
    assert all("Concrete" not in chunk.content for chunk in chunks_of(db, first))


# --- Project isolation ------------------------------------------------------

def test_chunks_carry_the_project_of_the_file_they_came_from(db, world):
    theirs = pdf_file(db, world, ["Retention is ten per cent in the other project."],
                      project=world["other"])
    index(db, theirs)
    assert all(chunk.project_id == world["other"].id for chunk in chunks_of(db, theirs))
    assert db.query(DocumentChunk).filter(
        DocumentChunk.ingested_file_id == theirs.id,
        DocumentChunk.project_id == world["project"].id,
    ).count() == 0


def test_a_stranger_cannot_see_or_index_another_projects_file(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    for call in (
        lambda: rag_api.index_ingested_file(
            file_id=file.id, force=False, db=db, current_user=world["outsider"]),
        lambda: rag_api.ingested_file_index_status(
            file_id=file.id, db=db, current_user=world["outsider"]),
    ):
        with pytest.raises(HTTPException) as refusal:
            call()
        # 404, not 403: confirming that an id exists is itself information.
        assert refusal.value.status_code == 404


def test_a_file_id_offered_as_a_document_id_retrieves_nothing(db, world):
    """The two id spaces do not blur into one.

    Unified retrieval made these chunks reachable — through
    `readable_ingested_file_ids`, and only through it. Passing a file's id in
    the *document* set must still find nothing, or the two authorization
    resolutions would be interchangeable and the weaker one would win.
    """
    file = pdf_file(db, world, ["Retention is five per cent of each payment."])
    index(db, file)
    service = _embeddings()

    results = PgVectorStore().search(
        db,
        project_id=world["project"].id,
        readable_document_ids=[file.id],  # the file's own id, in the wrong set
        readable_ingested_file_ids=[],
        query_embedding=service.embed_one("retention"),
        k=5,
    )
    assert results == []

    # And through the right set it is found, so the assertion above is about
    # the id space rather than about the chunk being unreachable at all.
    found = PgVectorStore().search(
        db,
        project_id=world["project"].id,
        readable_document_ids=[],
        readable_ingested_file_ids=[file.id],
        query_embedding=service.embed_one("retention"),
        k=5,
    )
    assert found and found[0].ingested_file_id == file.id


# --- The legacy Document path still works -----------------------------------

def test_the_document_path_is_unchanged(db, world):
    document = make_document(db, world)
    result = ingestion.index_document(
        db, document, embedding_service=_embeddings(), store=PgVectorStore()
    )
    assert result.status == ingestion.STATUS_READY
    assert result.source == "DOCUMENT"
    assert result.document_id == document.id
    db.refresh(document)
    assert document.index_status == ingestion.STATUS_READY
    # `page_count` is a Document column the ingested-file path has no notion of,
    # and it is still maintained.
    assert document.page_count == 1
    assert all(
        chunk.document_id == document.id and chunk.ingested_file_id is None
        for chunk in db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document.id).all()
    )


def test_document_chunks_are_still_retrievable_after_files_exist_alongside(db, world):
    """The regression that would matter most: adding a second source must not
    change what the existing retrieval path finds."""
    document = make_document(db, world)
    ingestion.index_document(
        db, document, embedding_service=_embeddings(), store=PgVectorStore()
    )
    index(db, pdf_file(db, world, ["Retention is ninety per cent, from a file."]))

    service = _embeddings()
    results = PgVectorStore().search(
        db, project_id=world["project"].id, readable_document_ids=[document.id],
        readable_ingested_file_ids=[],
        query_embedding=service.embed_one("retention"), k=5,
    )
    assert results
    assert all(chunk.document_id == document.id for chunk in results)
    assert "five per cent" in results[0].content


# --- API --------------------------------------------------------------------

def test_the_status_endpoint_explains_an_unindexable_file(db, world):
    file = make_file(db, world, category="DRAWING", extraction="NONE")
    payload = rag_api.ingested_file_index_status(
        file_id=file.id, db=db, current_user=world["manager"]
    )
    assert payload.file_id == file.id
    assert payload.status == ingestion.STATUS_NOT_INDEXED
    assert payload.extraction == "NONE"
    assert payload.indexable is False
    assert payload.not_indexable_reason
    assert payload.chunk_count == 0


def test_the_status_endpoint_reports_an_indexed_file(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    index(db, file)
    payload = rag_api.ingested_file_index_status(
        file_id=file.id, db=db, current_user=world["manager"]
    )
    assert payload.status == ingestion.STATUS_READY
    assert payload.indexable is True
    assert payload.not_indexable_reason is None
    assert payload.chunk_count > 0
    assert payload.indexed_at is not None


def test_the_index_endpoint_queues_the_work_rather_than_doing_it(db, world, monkeypatch):
    """Heavy work must not run in the request path."""
    queued = []
    monkeypatch.setattr(
        rag_api.rag, "submit_ingested_file_index",
        lambda file_id, **kwargs: queued.append((file_id, kwargs)),
    )
    file = pdf_file(db, world, ["Retention is five per cent."])
    payload = rag_api.index_ingested_file(
        file_id=file.id, force=False, db=db, current_user=world["manager"]
    )
    assert queued == [(file.id, {"force": False})]
    assert payload.status == ingestion.STATUS_NOT_INDEXED


def test_the_index_endpoint_refuses_an_unindexable_file_with_the_reason(db, world):
    file = make_file(db, world, category="IMAGE", extraction="NONE")
    with pytest.raises(HTTPException) as refusal:
        rag_api.index_ingested_file(
            file_id=file.id, force=False, db=db, current_user=world["manager"]
        )
    assert refusal.value.status_code == 400
    assert "cannot be indexed" in refusal.value.detail


def test_the_index_endpoint_refuses_while_a_run_is_under_way(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    db.execute(
        text("UPDATE ingested_files SET index_status = 'INDEXING' WHERE id = :id"),
        {"id": file.id},
    )
    db.commit()
    with pytest.raises(HTTPException) as refusal:
        rag_api.index_ingested_file(
            file_id=file.id, force=False, db=db, current_user=world["manager"]
        )
    assert refusal.value.status_code == 409


def test_the_endpoints_report_unavailable_when_rag_is_switched_off(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    file = make_file(db, world)
    for call in (
        lambda: rag_api.index_ingested_file(
            file_id=file.id, force=False, db=db, current_user=world["manager"]),
        lambda: rag_api.ingested_file_index_status(
            file_id=file.id, db=db, current_user=world["manager"]),
    ):
        with pytest.raises(HTTPException) as refusal:
            call()
        assert refusal.value.status_code == 503


def test_an_unknown_file_is_a_404(db, world):
    with pytest.raises(HTTPException) as refusal:
        rag_api.ingested_file_index_status(
            file_id=uuid4(), db=db, current_user=world["manager"]
        )
    assert refusal.value.status_code == 404


# --- The background job -----------------------------------------------------

def test_the_background_job_runs_on_the_shared_bounded_pool(monkeypatch):
    """Not a new executor. `IFC_MAX_CONCURRENT_PROCESSING` stays one ceiling
    over all heavy work."""
    submitted = []
    monkeypatch.setattr(
        ingestion.processing_pool, "submit",
        lambda job, *args, **kwargs: submitted.append((job, args, kwargs)),
    )
    file_id = uuid4()
    ingestion.submit_ingested_file_index(file_id, force=True)
    assert submitted == [(ingestion.index_ingested_file_job, (file_id,), {"force": True})]


def test_the_background_job_indexes_and_closes_its_own_session(db, world):
    file = pdf_file(db, world, ["Retention is five per cent."])
    db.commit()
    ingestion.index_ingested_file_job(file.id)

    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.index_status == ingestion.STATUS_READY
    assert chunks_of(db, file)


def test_the_background_job_swallows_a_missing_file(db, world):
    # A file deleted between queuing and running is not an error worth waking
    # anybody for.
    ingestion.index_ingested_file_job(uuid4())


def test_the_background_job_records_a_failure_without_raising(db, world):
    file = pdf_file(db, world, [""])
    db.commit()
    ingestion.index_ingested_file_job(file.id)

    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.index_status == ingestion.STATUS_FAILED
    assert refreshed.index_error


def test_the_background_job_leaves_an_unindexable_file_untouched(db, world):
    file = make_file(db, world, category="DRAWING", extraction="NONE")
    ingestion.index_ingested_file_job(file.id)

    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.index_status == ingestion.STATUS_NOT_INDEXED
    assert refreshed.index_error is None
