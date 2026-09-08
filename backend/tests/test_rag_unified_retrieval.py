"""Unified retrieval across documents and ingested files.

Retrieval is the part of RAG where an authorization mistake is silent. A
document list that shows too much is noticed; an answer that quotes a file
somebody was never meant to read arrives as a helpful paragraph with a page
number on it. So the assertions here are mostly about what does **not** come
back.

The one invariant everything else rests on:

    an empty readable-id set means *zero readable sources of that type*.
    It never means "all".

Every layer is tested for it separately — the store, the retrieval function,
and the endpoint — because each is reachable on its own and a caller that
skipped one would be relying on another to hold the line.

No test here makes a network call: the embedding and answering clients are
both injected stubs.
"""

from __future__ import annotations

import uuid
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import rag as rag_api
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.company import Company
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentType, ProjectStatus, UserRole, UserStatus
from app.models.ingestion import IngestedFile
from app.models.project import Project, ProjectMember
from app.models.rbac import ProjectParty
from app.models.user import User
from app.schemas.rag import RagCitation, RagQueryRequest
from app.services import rbac
from app.services.document_access import (
    assert_ingested_file_readable, readable_ingested_file_ids,
)
from app.services.rag import ingestion
from app.services.rag.answering import AnswerService
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.retrieval import retrieve
from app.services.rag.store import ChunkSource, PgVectorStore, PreparedChunk
from tests.embedding_stub import STUB_MODEL, StubEmbeddingClient, zero_vector

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")


# --- stubs ------------------------------------------------------------------


class _StubAnswerClient:
    """Echoes a fixed answer, so citation construction is what is under test."""

    def __init__(self, text_out="The answer is here [1]."):
        self._text = text_out
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        message = type("M", (), {"content": self._text})()
        return type("R", (), {"choices": [type("C", (), {"message": message})()]})()


def _embeddings() -> EmbeddingService:
    return EmbeddingService(client=StubEmbeddingClient(), model=STUB_MODEL)


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
        # Rollback *is* the teardown. Nothing below commits, so an interrupted
        # run strands nothing — which matters here more than usual: these
        # fixtures create users whose configurable role is deliberately
        # narrower than their legacy enum role, and a stranded one of those
        # trips the RBAC equivalence gate in a completely unrelated suite.
        session.rollback()
        session.close()


@pytest.fixture()
def world(db, monkeypatch):
    """Two projects, each holding one indexed document and one indexed file.

    Plus the three people whose access differs: the office manager on project
    A, the manager of project B, and a contractor's representative who is on
    project A for an outside party.
    """
    suffix = uuid4().hex[:10]
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    rbac.seed_disciplines(db)
    roles = rbac.seed_roles(db)
    office = Company(name=f"Retrieval Office {suffix}", kind="CONSULTING_OFFICE",
                     is_tenant=False, is_active=True)
    db.add(office)
    db.flush()

    def user(name, role_code, legacy=UserRole.ENGINEER):
        role = roles[role_code]
        person = User(
            full_name=name, email=f"{name.lower()}-{suffix}@example.com",
            hashed_password="x", role=legacy, status=UserStatus.ACTIVE,
            company_id=office.id, org_role_id=role.id,
            is_internal=role.is_internal_only,
        )
        db.add(person)
        db.flush()
        return person

    manager_a = user("RetPmA", "project_manager", UserRole.PROJECT_MANAGER)
    manager_b = user("RetPmB", "project_manager", UserRole.PROJECT_MANAGER)
    contractor = user("RetContractor", "contractor_representative")
    stranger = user("RetStranger", "project_manager", UserRole.PROJECT_MANAGER)

    def project(name, manager):
        row = Project(name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
                      company_id=office.id, project_manager_id=manager.id,
                      owner_id=manager.id)
        db.add(row)
        db.flush()
        return row

    project_a = project("Retrieval A", manager_a)
    project_b = project("Retrieval B", manager_b)

    party = ProjectParty(project_id=project_a.id, kind="MAIN_CONTRACTOR",
                         display_name=f"Barakat {suffix}", is_primary=True)
    db.add(party)
    db.flush()

    db.add_all([
        ProjectMember(project_id=project_a.id, user_id=manager_a.id,
                      role_on_project=manager_a.role,
                      project_role_id=roles["project_manager"].id, is_active=True),
        ProjectMember(project_id=project_b.id, user_id=manager_b.id,
                      role_on_project=manager_b.role,
                      project_role_id=roles["project_manager"].id, is_active=True),
        ProjectMember(project_id=project_a.id, user_id=contractor.id,
                      role_on_project=contractor.role,
                      project_role_id=roles["contractor_representative"].id,
                      party_id=party.id, is_active=True),
    ])
    db.flush()

    built = {
        "office": office, "project_a": project_a, "project_b": project_b,
        "manager_a": manager_a, "manager_b": manager_b,
        "contractor": contractor, "stranger": stranger, "party": party,
    }
    for key, proj, owner in (("a", project_a, manager_a), ("b", project_b, manager_b)):
        built[f"doc_{key}"] = _document(db, proj, owner, f"{key.upper()} Contract")
        built[f"file_{key}"] = _file(db, proj, owner, f"{key}-specification.pdf")
    db.flush()

    yield built


def _document(db, project, owner, title) -> Document:
    row = Document(
        project_id=project.id, uploaded_by_id=owner.id, title=title,
        document_type=DocumentType.CONTRACT,
        file_url=f"http://testserver/uploads/documents/{uuid4()}.pdf",
        index_status=ingestion.STATUS_READY,
    )
    db.add(row)
    db.flush()
    return row


def _file(db, project, owner, filename) -> IngestedFile:
    row = IngestedFile(
        project_id=project.id, uploaded_by_id=owner.id,
        original_filename=filename, normalized_filename=filename,
        file_category="PDF", detected_format="PDF", file_size_bytes=1024,
        storage_key=f"ingest/{uuid4()}_{filename}",
        status="READY", index_status=ingestion.STATUS_READY,
        metadata_json={"processor": "pdf", "category": "PDF", "extraction": "TEXT",
                       "details": {}},
    )
    db.add(row)
    db.flush()
    return row


# --- chunk fixtures ---------------------------------------------------------


def store_chunks(db, source: ChunkSource, project_id, texts) -> int:
    service = _embeddings()
    embedded = service.embed(texts)
    prepared = [
        PreparedChunk(page_number=i + 1, chunk_index=i, content=content,
                      token_count=len(content.split()), embedding=vector)
        for i, (content, vector) in enumerate(zip(texts, embedded.vectors))
    ]
    stored = PgVectorStore().add_chunks(
        db, source=source, project_id=project_id, chunks=prepared,
        embedding_model=embedded.model, embedding_dim=embedded.dimension,
    )
    db.flush()
    return stored


def index_everything(db, world):
    """Distinct text per source, so a leak names itself in the assertion."""
    store_chunks(db, ChunkSource.from_document(world["doc_a"].id),
                 world["project_a"].id, ["Retention in document A is five per cent."])
    store_chunks(db, ChunkSource.from_ingested_file(world["file_a"].id),
                 world["project_a"].id, ["Retention in file A is six per cent."])
    store_chunks(db, ChunkSource.from_document(world["doc_b"].id),
                 world["project_b"].id, ["Retention in document B is seven per cent."])
    store_chunks(db, ChunkSource.from_ingested_file(world["file_b"].id),
                 world["project_b"].id, ["Retention in file B is eight per cent."])
    db.flush()


def search(db, world, *, project=None, documents=(), files=(), query="retention", k=10):
    return PgVectorStore().search(
        db,
        project_id=(project or world["project_a"]).id,
        readable_document_ids=list(documents),
        readable_ingested_file_ids=list(files),
        query_embedding=_embeddings().embed_one(query),
        k=k,
    )


def contents(results) -> set[str]:
    return {r.content for r in results}


# --- The store: both sources, one ranked list -------------------------------

def test_both_sources_appear_in_one_result_list(db, world):
    index_everything(db, world)
    results = search(db, world,
                     documents=[world["doc_a"].id], files=[world["file_a"].id])
    assert contents(results) == {
        "Retention in document A is five per cent.",
        "Retention in file A is six per cent.",
    }
    kinds = {r.source.kind for r in results}
    assert kinds == {"DOCUMENT", "INGESTED_FILE"}


def test_every_result_names_exactly_one_source(db, world):
    index_everything(db, world)
    for result in search(db, world,
                         documents=[world["doc_a"].id], files=[world["file_a"].id]):
        assert (result.document_id is None) != (result.ingested_file_id is None)
        assert result.source.id in {world["doc_a"].id, world["file_a"].id}


def test_documents_only_when_the_file_set_is_empty(db, world):
    index_everything(db, world)
    results = search(db, world, documents=[world["doc_a"].id], files=[])
    assert contents(results) == {"Retention in document A is five per cent."}


def test_files_only_when_the_document_set_is_empty(db, world):
    index_everything(db, world)
    results = search(db, world, documents=[], files=[world["file_a"].id])
    assert contents(results) == {"Retention in file A is six per cent."}


# --- Attack 2 & 3 & 9: an empty set is zero, never "all" --------------------

def test_an_empty_document_set_returns_no_documents(db, world):
    """Attack 2. The most important invariant in this module."""
    index_everything(db, world)
    results = search(db, world, documents=[], files=[world["file_a"].id])
    assert all(r.document_id is None for r in results)
    assert "Retention in document A is five per cent." not in contents(results)


def test_an_empty_file_set_returns_no_files(db, world):
    """Attack 3."""
    index_everything(db, world)
    results = search(db, world, documents=[world["doc_a"].id], files=[])
    assert all(r.ingested_file_id is None for r in results)
    assert "Retention in file A is six per cent." not in contents(results)


def test_both_sets_empty_retrieves_nothing_at_all(db, world):
    """Not "the whole project" — the case a wrong implementation gets wrong."""
    index_everything(db, world)
    assert search(db, world, documents=[], files=[]) == []


def test_both_sets_empty_does_not_even_reach_the_database(db, world, monkeypatch):
    """The early return is the guarantee, not the SQL that would follow it."""
    index_everything(db, world)
    # Resolved before the patch: reading an expired ORM attribute would issue a
    # refresh query and trip the guard for a reason that has nothing to do with
    # the search.
    project_id = world["project_a"].id
    query_vector = _embeddings().embed_one("retention")

    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("an unscoped search must not build a query")

    monkeypatch.setattr(db, "execute", explode)
    try:
        assert PgVectorStore().search(
            db, project_id=project_id, readable_document_ids=[],
            readable_ingested_file_ids=[], query_embedding=query_vector, k=5,
        ) == []
    finally:
        # Undone here, not at teardown: `world` requested `monkeypatch` too, so
        # its finaliser — which purges via `db.execute` — runs first.
        monkeypatch.undo()


def test_a_zero_k_retrieves_nothing(db, world):
    index_everything(db, world)
    assert search(db, world, documents=[world["doc_a"].id],
                  files=[world["file_a"].id], k=0) == []


# --- Attack 1 & 4: project isolation ----------------------------------------

def test_knowing_another_projects_file_uuid_retrieves_nothing(db, world):
    """Attack 1. The id is valid, the query matches perfectly, the caller has
    access to project A — and the chunk belongs to project B."""
    index_everything(db, world)
    leaked = search(db, world, project=world["project_a"],
                    documents=[], files=[world["file_b"].id])
    assert leaked == []


def test_knowing_another_projects_document_uuid_retrieves_nothing(db, world):
    index_everything(db, world)
    leaked = search(db, world, project=world["project_a"],
                    documents=[world["doc_b"].id], files=[])
    assert leaked == []


def test_project_b_ids_under_project_a_return_nothing_of_either_type(db, world):
    """Attack 4, both source types at once."""
    index_everything(db, world)
    leaked = search(db, world, project=world["project_a"],
                    documents=[world["doc_b"].id], files=[world["file_b"].id])
    assert leaked == []


def test_a_mixed_id_list_yields_only_the_in_project_half(db, world):
    """The project filter is applied to every arm, not just the first."""
    index_everything(db, world)
    results = search(
        db, world, project=world["project_a"],
        documents=[world["doc_a"].id, world["doc_b"].id],
        files=[world["file_a"].id, world["file_b"].id],
    )
    assert contents(results) == {
        "Retention in document A is five per cent.",
        "Retention in file A is six per cent.",
    }


def test_nonexistent_ids_retrieve_nothing_rather_than_everything(db, world):
    index_everything(db, world)
    assert search(db, world, documents=[uuid4()], files=[uuid4()]) == []


# --- Attack 5: only one source type authorized ------------------------------

def test_when_only_documents_are_authorized_only_documents_appear(db, world):
    index_everything(db, world)
    results = search(db, world, documents=[world["doc_a"].id], files=[])
    assert results and all(r.source.kind == "DOCUMENT" for r in results)


def test_when_only_files_are_authorized_only_files_appear(db, world):
    index_everything(db, world)
    results = search(db, world, documents=[], files=[world["file_a"].id])
    assert results and all(r.source.kind == "INGESTED_FILE" for r in results)


# --- Retrieval: titles and provenance ---------------------------------------

def test_a_file_result_is_titled_by_its_original_filename(db, world):
    index_everything(db, world)
    results = retrieve(
        db, project_id=world["project_a"].id, readable_document_ids=[],
        readable_ingested_file_ids=[world["file_a"].id],
        query="retention", embedding_service=_embeddings(), store=PgVectorStore(),
    )
    assert results
    assert results[0].source_title == "a-specification.pdf"
    assert results[0].source_type == "INGESTED_FILE"


def test_a_document_result_keeps_its_title(db, world):
    index_everything(db, world)
    results = retrieve(
        db, project_id=world["project_a"].id,
        readable_document_ids=[world["doc_a"].id], readable_ingested_file_ids=[],
        query="retention", embedding_service=_embeddings(), store=PgVectorStore(),
    )
    assert results and results[0].source_title == "A Contract"
    assert results[0].source_type == "DOCUMENT"


def test_a_title_is_never_a_storage_key(db, world):
    """The one thing a filename must not leak into."""
    index_everything(db, world)
    results = retrieve(
        db, project_id=world["project_a"].id, readable_document_ids=[],
        readable_ingested_file_ids=[world["file_a"].id],
        query="retention", embedding_service=_embeddings(), store=PgVectorStore(),
    )
    assert results
    for item in results:
        assert "ingest/" not in item.source_title
        assert world["file_a"].storage_key not in item.source_title


def test_retrieval_with_both_empty_sets_returns_nothing(db, world):
    index_everything(db, world)
    assert retrieve(
        db, project_id=world["project_a"].id, readable_document_ids=[],
        readable_ingested_file_ids=[], query="retention",
        embedding_service=_embeddings(), store=PgVectorStore(),
    ) == []


def test_retrieval_requires_the_file_set_to_be_passed_explicitly(db, world):
    """No default that could silently mean "documents only" — or "all"."""
    with pytest.raises(TypeError):
        retrieve(
            db, project_id=world["project_a"].id,
            readable_document_ids=[world["doc_a"].id], query="retention",
        )


def test_the_store_requires_both_sets_to_be_passed_explicitly(db, world):
    with pytest.raises(TypeError):
        PgVectorStore().search(
            db, project_id=world["project_a"].id,
            readable_document_ids=[], query_embedding=zero_vector(), k=5,
        )


# --- Citations --------------------------------------------------------------

def _answer(db, world, *, documents=(), files=()):
    retrieved = retrieve(
        db, project_id=world["project_a"].id,
        readable_document_ids=list(documents), readable_ingested_file_ids=list(files),
        query="retention", embedding_service=_embeddings(), store=PgVectorStore(),
    )
    return AnswerService(client=_StubAnswerClient(), model="stub").answer(
        "what is the retention?", retrieved
    )


def test_a_document_citation_is_unchanged(db, world):
    index_everything(db, world)
    answer = _answer(db, world, documents=[world["doc_a"].id])
    assert answer.citations
    citation = answer.citations[0]
    assert citation.source_type == "DOCUMENT"
    assert citation.document_id == world["doc_a"].id
    assert citation.ingested_file_id is None
    assert citation.title == "A Contract"


def test_a_file_citation_names_the_file(db, world):
    index_everything(db, world)
    answer = _answer(db, world, files=[world["file_a"].id])
    citation = answer.citations[0]
    assert citation.source_type == "INGESTED_FILE"
    assert citation.ingested_file_id == world["file_a"].id
    assert citation.document_id is None
    assert citation.title == "a-specification.pdf"


def test_mixed_citations_each_name_their_own_source(db, world):
    index_everything(db, world)
    answer = _answer(db, world,
                     documents=[world["doc_a"].id], files=[world["file_a"].id])
    by_type = {c.source_type: c for c in answer.citations}
    assert set(by_type) == {"DOCUMENT", "INGESTED_FILE"}
    assert by_type["DOCUMENT"].document_id == world["doc_a"].id
    assert by_type["INGESTED_FILE"].ingested_file_id == world["file_a"].id


def test_a_citation_can_never_name_nothing_or_both():
    with pytest.raises(ValueError):
        ChunkSource()
    with pytest.raises(ValueError):
        ChunkSource(document_id=uuid4(), ingested_file_id=uuid4())


def test_the_wire_citation_keeps_the_document_field_populated(db, world):
    """Backwards compatibility, at the schema boundary a client actually reads."""
    index_everything(db, world)
    answer = _answer(db, world, documents=[world["doc_a"].id])
    citation = answer.citations[0]
    payload = RagCitation(
        source_type=citation.source_type, document_id=citation.document_id,
        ingested_file_id=citation.ingested_file_id, title=citation.title,
        page=citation.page, snippet=citation.snippet,
    ).model_dump(by_alias=True)
    assert payload["documentId"] == world["doc_a"].id
    assert payload["ingestedFileId"] is None
    assert payload["sourceType"] == "DOCUMENT"
    assert set(payload) == {
        "sourceType", "documentId", "ingestedFileId", "title", "page", "snippet",
    }


# --- readable_ingested_file_ids ---------------------------------------------

def test_office_staff_read_every_file_on_their_project(db, world):
    ids = readable_ingested_file_ids(db, world["manager_a"], world["project_a"].id)
    assert ids == [world["file_a"].id]


def test_someone_with_no_project_access_reads_no_files(db, world):
    assert readable_ingested_file_ids(
        db, world["stranger"], world["project_a"].id
    ) == []


def test_a_manager_of_another_project_reads_no_files_here(db, world):
    assert readable_ingested_file_ids(
        db, world["manager_b"], world["project_a"].id
    ) == []


def test_an_external_participant_reads_only_their_own_uploads(db, world):
    """The derivation of `party_document_scope`: there is no share table for
    ingested files, so the shared set is empty and the rule reduces to own
    uploads. Deny-by-default, not an oversight."""
    assert readable_ingested_file_ids(
        db, world["contractor"], world["project_a"].id
    ) == []

    theirs = _file(db, world["project_a"], world["contractor"], "contractor-rfi.pdf")
    db.flush()
    assert readable_ingested_file_ids(
        db, world["contractor"], world["project_a"].id
    ) == [theirs.id]


def test_losing_document_view_removes_every_readable_file(db, world, monkeypatch):
    """Project access alone is not enough. The file library's own code governs."""
    import app.services.document_access as access

    monkeypatch.setattr(
        access, "has_permission",
        lambda db, user, code, project_id=None: code != "document.view",
    )
    assert readable_ingested_file_ids(
        db, world["manager_a"], world["project_a"].id
    ) == []


def test_asserting_readability_refuses_an_unshared_file(db, world):
    with pytest.raises(HTTPException) as refusal:
        assert_ingested_file_readable(db, world["contractor"], world["file_a"])
    assert refusal.value.status_code == 403

    with pytest.raises(HTTPException) as refusal:
        assert_ingested_file_readable(db, world["stranger"], world["file_a"])
    assert refusal.value.status_code == 404


# --- The endpoint -----------------------------------------------------------


def _query(db, world, user, project=None, document_id=None):
    return rag_api.query_documents(
        payload=RagQueryRequest(
            project_id=(project or world["project_a"]).id,
            query="what is the retention percentage?",
            document_id=document_id,
        ),
        db=db, current_user=user,
    )


@pytest.fixture()
def stubbed_services(monkeypatch):
    monkeypatch.setattr(rag_api, "EmbeddingService", lambda *a, **k: _embeddings())
    monkeypatch.setattr(
        rag_api, "AnswerService",
        lambda *a, **k: AnswerService(client=_StubAnswerClient(), model="stub"),
    )


def test_the_query_endpoint_answers_from_both_sources(db, world, stubbed_services):
    index_everything(db, world)
    response = _query(db, world, world["manager_a"])
    assert response.found
    kinds = {c.source_type for c in response.citations}
    assert kinds == {"DOCUMENT", "INGESTED_FILE"}
    titles = {c.title for c in response.citations}
    assert titles == {"A Contract", "a-specification.pdf"}


def test_an_external_participant_gets_no_file_citations(db, world, stubbed_services):
    """The party rule reaching all the way through to an answer."""
    index_everything(db, world)
    response = _query(db, world, world["contractor"])
    assert all(c.source_type != "INGESTED_FILE" for c in response.citations)
    assert all("specification" not in c.title for c in response.citations)


def test_a_caller_without_project_access_is_refused(db, world, stubbed_services):
    with pytest.raises(HTTPException) as refusal:
        _query(db, world, world["stranger"])
    assert refusal.value.status_code == 403


def test_naming_a_document_excludes_every_file(db, world, stubbed_services):
    """An explicit instruction to look in one place must not widen."""
    index_everything(db, world)
    response = _query(db, world, world["manager_a"], document_id=world["doc_a"].id)
    assert response.citations
    assert all(c.source_type == "DOCUMENT" for c in response.citations)
    assert all(c.document_id == world["doc_a"].id for c in response.citations)


def test_an_unindexed_file_is_not_retrieved(db, world, stubbed_services):
    """READY is the gate. A half-written index must stay unreachable."""
    index_everything(db, world)
    db.execute(
        text("UPDATE ingested_files SET index_status = 'FAILED' WHERE id = :id"),
        {"id": world["file_a"].id},
    )
    db.flush()
    response = _query(db, world, world["manager_a"])
    assert all(c.source_type != "INGESTED_FILE" for c in response.citations)


def test_the_endpoint_returns_nothing_when_neither_source_is_readable(
    db, world, stubbed_services, monkeypatch
):
    index_everything(db, world)
    monkeypatch.setattr(rag_api, "readable_document_ids", lambda *a, **k: [])
    monkeypatch.setattr(rag_api, "readable_ingested_file_ids", lambda *a, **k: [])
    response = _query(db, world, world["manager_a"])
    assert response.found is False
    assert response.citations == []


def test_the_response_shape_is_unchanged_for_a_document_only_project(
    db, world, stubbed_services
):
    """Legacy compatibility at the wire level: a project with no indexed files
    produces exactly the citations it always did."""
    index_everything(db, world)
    db.execute(
        text("UPDATE ingested_files SET index_status = 'NOT_INDEXED' WHERE id = :id"),
        {"id": world["file_a"].id},
    )
    db.flush()
    response = _query(db, world, world["manager_a"])
    assert response.citations
    for citation in response.citations:
        assert citation.source_type == "DOCUMENT"
        assert citation.document_id is not None
        assert citation.ingested_file_id is None


# --- Chunk-level sanity -----------------------------------------------------

def test_chunks_of_both_kinds_coexist_and_keep_their_project(db, world):
    index_everything(db, world)
    rows = db.query(DocumentChunk).filter(
        DocumentChunk.project_id.in_([world["project_a"].id, world["project_b"].id])
    ).all()
    assert len(rows) == 4
    for row in rows:
        assert (row.document_id is None) != (row.ingested_file_id is None)
    per_project = {}
    for row in rows:
        per_project.setdefault(row.project_id, set()).add(row.source_id)
    assert per_project[world["project_a"].id] == {world["doc_a"].id, world["file_a"].id}
    assert per_project[world["project_b"].id] == {world["doc_b"].id, world["file_b"].id}
