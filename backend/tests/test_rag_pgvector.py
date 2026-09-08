"""The pgvector storage layer: the schema, the ordering, and the guard rails.

What moved is *where similarity is computed*. Everything above `store.py` is
unchanged, and the suites that cover it — retrieval scoping, citations,
project isolation — did not need editing beyond swapping the class name. That
containment was the point of putting a `VectorStore` in front of the vectors,
so these tests are about the parts that genuinely changed:

* the column is a real `vector(N)`, and the dimension is enforced by the
  database rather than checked at read time;
* ordering and the top-k limit happen in SQL;
* the HNSW index exists with the cosine operator class — an index built for L2
  would simply never be chosen, and the only symptom would be slowness;
* iterative scan is applied so a filtered query still returns k rows.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentType, ProjectStatus, UserRole, UserStatus
from app.models.project import Project
from app.models.user import User
from app.services.rag import store as store_module
from app.services.rag.store import (
    ChunkSource, PgVectorStore, PreparedChunk, VectorDimensionMismatch,
    get_vector_store,
)
from tests.embedding_stub import (
    STUB_MODEL, StubEmbeddingClient, dimensions, stub_embedding_service, zero_vector,
)


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
def world(db):
    """Flush-only. The `db` fixture's rollback is the whole teardown."""
    suffix = uuid4().hex[:10]
    user = User(full_name="VecPm", email=f"vecpm-{suffix}@example.com",
                hashed_password="x", role=UserRole.PROJECT_MANAGER,
                status=UserStatus.ACTIVE)
    db.add(user)
    db.flush()
    project = Project(name=f"Vector {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=user.id, project_manager_id=user.id)
    db.add(project)
    db.flush()
    document = Document(
        project_id=project.id, uploaded_by_id=user.id, title="Vector Contract",
        document_type=DocumentType.CONTRACT,
        file_url=f"http://testserver/uploads/documents/{uuid4()}.pdf",
    )
    db.add(document)
    db.flush()
    yield {"user": user, "project": project, "document": document}


def store_texts(db, world, texts) -> int:
    service = stub_embedding_service()
    embedded = service.embed(texts)
    prepared = [
        PreparedChunk(page_number=i + 1, chunk_index=i, content=content,
                      token_count=len(content.split()), embedding=vector)
        for i, (content, vector) in enumerate(zip(texts, embedded.vectors))
    ]
    count = PgVectorStore().add_chunks(
        db, source=ChunkSource.from_document(world["document"].id),
        project_id=world["project"].id, chunks=prepared,
        embedding_model=embedded.model, embedding_dim=embedded.dimension,
    )
    db.flush()
    return count


def search(db, world, query, k=5):
    return PgVectorStore().search(
        db, project_id=world["project"].id,
        readable_document_ids=[world["document"].id],
        readable_ingested_file_ids=[],
        query_embedding=stub_embedding_service().embed_one(query),
        k=k,
    )


# --- The schema -------------------------------------------------------------

def test_the_embedding_column_is_a_real_vector_of_the_configured_width(db):
    row = db.execute(text(
        "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
        "WHERE a.attrelid = 'document_chunks'::regclass AND a.attname = 'embedding'"
    )).scalar()
    assert row == f"vector({settings.RAG_EMBEDDING_DIMENSIONS})"


def test_the_hnsw_index_exists_with_the_cosine_operator_class(db):
    """An index built for L2 would never be chosen by a `<=>` query, and the
    only symptom would be a slow search returning correct answers."""
    definition = db.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname = 'ix_document_chunks_embedding_hnsw'"
    )).scalar()
    assert definition is not None, "the HNSW index is missing"
    assert "USING hnsw" in definition
    assert "vector_cosine_ops" in definition


def test_the_extension_is_installed(db):
    assert db.execute(text(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    )).scalar() is not None


def test_the_application_store_is_the_pgvector_one():
    assert isinstance(get_vector_store(), PgVectorStore)


# --- Round trip -------------------------------------------------------------

def test_a_vector_survives_the_round_trip_through_the_column(db, world):
    store_texts(db, world, ["Retention is five per cent."])
    stored = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["document"].id
    ).one()
    expected = stub_embedding_service().embed_one("Retention is five per cent.")
    assert len(stored.embedding) == dimensions()
    assert list(stored.embedding)[: len(expected)] == pytest.approx(expected, abs=1e-6)


def test_the_recorded_dimension_matches_the_column(db, world):
    store_texts(db, world, ["Retention is five per cent."])
    stored = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["document"].id
    ).one()
    assert stored.embedding_dim == dimensions()
    assert stored.embedding_model == STUB_MODEL


# --- Ordering, now done by PostgreSQL ---------------------------------------

def test_the_most_relevant_chunk_comes_back_first(db, world):
    store_texts(db, world, [
        "Concrete curing shall continue for seven days.",
        "Retention is five per cent of each interim payment.",
        "Every worker shall wear a safety helmet.",
    ])
    results = search(db, world, "what is the retention percentage")
    assert results
    assert "Retention" in results[0].content
    assert results[0].page_number == 2


def test_scores_are_similarities_not_distances(db, world):
    """`1 - cosine_distance`, so higher is better and an exact match is 1 —
    the contract every caller was written against before the move."""
    store_texts(db, world, ["Retention is five per cent of each interim payment."])
    results = search(db, world, "Retention is five per cent of each interim payment.")
    assert results
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


def test_scores_descend(db, world):
    store_texts(db, world, [
        "Retention is five per cent.",
        "Concrete curing rules.",
        "Scaffold inspection notes.",
    ])
    scores = [chunk.score for chunk in search(db, world, "retention payment")]
    assert scores == sorted(scores, reverse=True)


def test_the_limit_is_applied_by_the_database(db, world, monkeypatch):
    """k rows come back from SQL, not a full candidate set sorted in Python."""
    store_texts(db, world, [f"Clause {i} about concrete." for i in range(10)])
    assert len(search(db, world, "concrete", k=3)) == 3


# --- The dimension is enforced by the schema --------------------------------

def test_a_mismatched_vector_is_refused_before_it_reaches_the_driver(db, world):
    store = PgVectorStore()
    with pytest.raises(VectorDimensionMismatch) as refusal:
        store.add_chunks(
            db, source=ChunkSource.from_document(world["document"].id),
            project_id=world["project"].id,
            chunks=[PreparedChunk(page_number=1, chunk_index=0, content="x",
                                  token_count=1, embedding=[0.1, 0.2, 0.3])],
            embedding_model="a-different-model", embedding_dim=3,
        )
    message = str(refusal.value)
    assert "a-different-model" in message
    assert str(dimensions()) in message
    assert "schema migration" in message


def test_the_database_itself_refuses_a_mismatched_vector(db, world):
    """The store's check is a better error message, not the guarantee. The
    guarantee is the column type, and this is what proves it."""
    db.add(DocumentChunk(
        document_id=world["document"].id, project_id=world["project"].id,
        page_number=1, chunk_index=0, content="x", token_count=1,
        embedding=[0.1, 0.2], embedding_model="x", embedding_dim=2,
    ))
    with pytest.raises((DataError, SQLAlchemyError)):
        db.flush()
    db.rollback()


def test_a_query_of_the_wrong_width_returns_nothing_rather_than_erroring(db, world):
    """A search endpoint must not 500 because the corpus was embedded by a
    different model; an empty result is the truthful answer."""
    store_texts(db, world, ["Retention is five per cent."])
    assert PgVectorStore().search(
        db, project_id=world["project"].id,
        readable_document_ids=[world["document"].id],
        readable_ingested_file_ids=[],
        query_embedding=[0.1, 0.2], k=5,
    ) == []


def test_an_empty_chunk_list_does_not_trip_the_dimension_check(db, world):
    """Deleting a source's chunks by writing none must not need a dimension."""
    assert PgVectorStore().add_chunks(
        db, source=ChunkSource.from_document(world["document"].id),
        project_id=world["project"].id, chunks=[],
        embedding_model="irrelevant", embedding_dim=0,
    ) == 0


# --- Iterative scan ---------------------------------------------------------

def test_iterative_scan_is_set_for_the_transaction(db, world):
    """Filtered HNSW post-filters by default, so a selective filter silently
    returns fewer than k rows. This is the setting that prevents it."""
    store_texts(db, world, ["Retention is five per cent."])
    search(db, world, "retention")
    assert db.execute(text("SHOW hnsw.iterative_scan")).scalar() == \
        settings.RAG_HNSW_ITERATIVE_SCAN


def test_the_setting_can_be_switched_off_for_older_pgvector(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_HNSW_ITERATIVE_SCAN", "")
    store_texts(db, world, ["Retention is five per cent."])
    # No SET is issued, and the search still works.
    assert search(db, world, "retention")


def test_an_unrecognised_mode_is_ignored_rather_than_injected(db, world, monkeypatch):
    """The value reaches a `SET LOCAL`, which takes no bind parameters."""
    monkeypatch.setattr(
        settings, "RAG_HNSW_ITERATIVE_SCAN", "off; DROP TABLE document_chunks",
    )
    store_texts(db, world, ["Retention is five per cent."])
    assert search(db, world, "retention")
    assert db.execute(text("SELECT to_regclass('document_chunks')")).scalar() is not None


def test_every_accepted_mode_is_a_real_pgvector_value(db, world):
    for mode in store_module._ITERATIVE_SCAN_MODES:
        db.execute(text(f"SET LOCAL hnsw.iterative_scan = {mode}"))
    db.rollback()


# --- Scoping still holds ----------------------------------------------------

def test_an_empty_readable_set_still_means_zero_not_all(db, world):
    """The invariant that matters most, re-checked against the new backend."""
    store_texts(db, world, ["Retention is five per cent."])
    assert PgVectorStore().search(
        db, project_id=world["project"].id,
        readable_document_ids=[], readable_ingested_file_ids=[],
        query_embedding=zero_vector(), k=5,
    ) == []


def test_another_projects_id_retrieves_nothing(db, world):
    store_texts(db, world, ["Retention is five per cent."])
    assert PgVectorStore().search(
        db, project_id=uuid4(),
        readable_document_ids=[world["document"].id],
        readable_ingested_file_ids=[],
        query_embedding=stub_embedding_service().embed_one("retention"), k=5,
    ) == []


def test_re_storing_replaces_rather_than_appends(db, world):
    store_texts(db, world, ["First version of the clause."])
    store_texts(db, world, ["Second version.", "Another chunk."])
    remaining = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["document"].id
    ).all()
    assert len(remaining) == 2
    assert all("First version" not in chunk.content for chunk in remaining)


def test_deleting_a_source_removes_its_chunks(db, world):
    store_texts(db, world, ["one", "two", "three"])
    removed = PgVectorStore().delete_source(
        db, source=ChunkSource.from_document(world["document"].id)
    )
    assert removed == 3
    assert db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["document"].id
    ).count() == 0


# --- The shared stub --------------------------------------------------------

def test_the_stub_pads_to_the_column_width_without_changing_ranking(db, world):
    """Zeros contribute nothing to a dot product or a norm, so the padded
    vectors rank exactly as the short ones did."""
    client = StubEmbeddingClient()
    vector = client.create(model="x", input=["retention retention"]).data[0].embedding
    assert len(vector) == dimensions()
    assert vector[StubEmbeddingClient.VOCAB.index("retention")] == 2.0
    assert set(vector[len(StubEmbeddingClient.VOCAB) + 1:]) == {0.0}
