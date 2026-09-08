"""Re-embedding, project re-index, and recovering runs that died.

The three things this covers are the ones that only matter once a corpus has
existed for a while:

* **staleness is derived**, so changing the embedding model is detectable
  without anybody having remembered to set a flag;
* **a run is idempotent and partial-safe** — re-indexing twice produces the
  same chunks, and source 73 failing does not lose sources 1–72;
* **a stranded `INDEXING` row is recoverable**, which before this was only
  possible if somebody noticed and passed `force=true`.

Flush-only fixtures: the `db` fixture's rollback is the whole teardown, so an
interrupted run strands nothing. That matters more than usual here — these
tests deliberately create rows in odd states.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
from app.models.rag_job import (
    STATUS_COMPLETED, STATUS_FAILED, STATUS_PARTIAL, STATUS_QUEUED,
    STATUS_RUNNING, RagIndexJob,
)
from app.models.user import User
from app.schemas.rag import RagReindexRequest
from app.services.rag import ingestion, maintenance
from app.services.rag.store import ChunkSource, PgVectorStore, PreparedChunk
from tests.embedding_stub import STUB_MODEL, stub_embedding_service, zero_vector

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")


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


@pytest.fixture(autouse=True)
def no_background_pool(monkeypatch):
    """Nothing in this module wants real background execution.

    `recover_stale_jobs` re-submits a recovered run to the shared pool, and a
    pool worker opens its *own* session. Against a test whose transaction is
    still open and holding row locks, that worker blocks until the test ends —
    which turned an eighteen-second module into a twenty-six-minute one.

    Stubbing the pool keeps the assertions about *what would be submitted*,
    which is the part worth testing; that the pool then runs it is
    `processing_pool`'s own contract, covered in its own tests.
    """
    submitted: list[tuple] = []
    monkeypatch.setattr(
        maintenance.processing_pool, "submit",
        lambda job, *args, **kwargs: submitted.append((job, args, kwargs)),
    )
    return submitted


@pytest.fixture()
def world(db, monkeypatch):
    """Two projects, so every isolation assertion has somewhere to leak to."""
    suffix = uuid4().hex[:10]
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    # The stub writes chunks under this name; making it the configured model
    # is what makes "already current" the default state.
    monkeypatch.setattr(settings, "OPENAI_EMBEDDING_MODEL", STUB_MODEL)

    manager = User(full_name="MaintPm", email=f"maintpm-{suffix}@example.com",
                   hashed_password="x", role=UserRole.PROJECT_MANAGER,
                   status=UserStatus.ACTIVE)
    stranger = User(full_name="MaintOther", email=f"maintother-{suffix}@example.com",
                    hashed_password="x", role=UserRole.PROJECT_MANAGER,
                    status=UserStatus.ACTIVE)
    db.add_all([manager, stranger])
    db.flush()

    def project(name, owner):
        row = Project(name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=owner.id)
        db.add(row)
        db.flush()
        db.add(ProjectMember(project_id=row.id, user_id=owner.id,
                             role_on_project=owner.role, is_active=True))
        return row

    project_a = project("Maint A", manager)
    project_b = project("Maint B", stranger)
    db.flush()
    try:
        yield {"a": project_a, "b": project_b, "manager": manager, "stranger": stranger}
    finally:
        # Most tests here only flush, and the `db` fixture's rollback is their
        # whole teardown. A handful must **commit**, because
        # `run_project_reindex` opens its own session and can only see
        # committed rows — and a commit takes this whole world with it.
        #
        # So the purge runs unconditionally rather than only for those tests:
        # it deletes nothing when nothing was committed, and it is the
        # difference between a suite that cleans up after itself and one that
        # slowly fills a shared development database.
        _purge(db, [project_a.id, project_b.id], [manager.id, stranger.id])


def _purge(db, project_ids, user_ids):
    db.rollback()
    params = {"projects": list(project_ids), "users": list(user_ids)}
    for statement in (
        "DELETE FROM rag_index_jobs WHERE project_id = ANY(:projects)",
        "DELETE FROM document_chunks WHERE project_id = ANY(:projects)",
        "DELETE FROM ingestion_jobs WHERE file_id IN "
        "(SELECT id FROM ingested_files WHERE project_id = ANY(:projects))",
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


def make_document(db, project, owner, *, status=ingestion.STATUS_READY, title="Contract"):
    row = Document(
        project_id=project.id, uploaded_by_id=owner.id, title=title,
        document_type=DocumentType.CONTRACT,
        file_url=f"http://testserver/uploads/documents/{uuid4()}.pdf",
        index_status=status,
    )
    db.add(row)
    db.flush()
    return row


def make_file(db, project, owner, *, status=ingestion.STATUS_READY, name="spec.pdf"):
    row = IngestedFile(
        project_id=project.id, uploaded_by_id=owner.id,
        original_filename=name, normalized_filename=name,
        file_category="PDF", detected_format="PDF", file_size_bytes=1024,
        storage_key=f"ingest/{uuid4()}_{name}", status="READY",
        index_status=status,
        metadata_json={"processor": "pdf", "category": "PDF", "extraction": "TEXT",
                       "details": {}},
    )
    db.add(row)
    db.flush()
    return row


def give_chunks(db, source, project, *, model=None, dim=None, count=2):
    """Chunks written directly, so a test can choose the model they claim."""
    is_document = isinstance(source, Document)
    for index in range(count):
        db.add(DocumentChunk(
            document_id=source.id if is_document else None,
            ingested_file_id=None if is_document else source.id,
            project_id=project.id, page_number=index + 1, chunk_index=index,
            content=f"chunk {index}", token_count=2, embedding=zero_vector(),
            embedding_model=model or settings.OPENAI_EMBEDDING_MODEL,
            embedding_dim=dim if dim is not None else settings.RAG_EMBEDDING_DIMENSIONS,
        ))
    db.flush()


def chunks_for(db, source):
    column = (DocumentChunk.document_id if isinstance(source, Document)
              else DocumentChunk.ingested_file_id)
    return db.query(DocumentChunk).filter(column == source.id).all()


# --- Staleness detection ----------------------------------------------------

def test_a_source_on_the_current_model_is_not_stale(db, world):
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"])
    assert maintenance.source_needs_reembedding(db, document) is False


def test_a_source_embedded_by_another_model_is_stale(db, world):
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"], model="text-embedding-ada-002")
    assert maintenance.source_needs_reembedding(db, document) is True


def test_a_source_embedded_at_another_width_is_stale(db, world):
    """Catches a switch to a model the `vector(N)` column could not even store."""
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"], dim=3072)
    assert maintenance.source_needs_reembedding(db, document) is True


def test_an_unindexed_source_is_not_stale(db, world):
    """Unindexed and stale are different problems with different remedies."""
    document = make_document(db, world["a"], world["manager"],
                             status=ingestion.STATUS_NOT_INDEXED)
    assert maintenance.source_needs_reembedding(db, document) is False


def test_staleness_follows_configuration_rather_than_a_stored_flag(db, world, monkeypatch):
    """The whole point of deriving it: changing the setting changes the answer
    with no migration and nothing to remember to update."""
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"])
    assert maintenance.source_needs_reembedding(db, document) is False

    monkeypatch.setattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    assert maintenance.source_needs_reembedding(db, document) is True


def test_the_project_summary_reports_what_the_corpus_is_embedded_with(db, world):
    current = make_document(db, world["a"], world["manager"], title="Current")
    old = make_document(db, world["a"], world["manager"], title="Old")
    give_chunks(db, current, world["a"], count=3)
    give_chunks(db, old, world["a"], model="text-embedding-ada-002", count=2)

    summary = maintenance.project_reembedding_summary(db, world["a"].id)
    assert summary["totalChunks"] == 5
    assert summary["staleChunks"] == 2
    assert summary["needsReembedding"] is True
    assert summary["configuredModel"] == STUB_MODEL
    by_model = {entry["model"]: entry for entry in summary["models"]}
    assert by_model[STUB_MODEL]["current"] is True
    assert by_model["text-embedding-ada-002"]["current"] is False


def test_the_summary_of_a_current_project_says_no_reembedding_needed(db, world):
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"])
    assert maintenance.project_reembedding_summary(
        db, world["a"].id)["needsReembedding"] is False


def test_the_summary_never_counts_another_projects_chunks(db, world):
    mine = make_document(db, world["a"], world["manager"])
    theirs = make_document(db, world["b"], world["stranger"])
    give_chunks(db, mine, world["a"], count=2)
    give_chunks(db, theirs, world["b"], model="other", count=5)

    summary = maintenance.project_reembedding_summary(db, world["a"].id)
    assert summary["totalChunks"] == 2
    assert summary["staleChunks"] == 0


# --- Source selection -------------------------------------------------------

def test_the_stale_scope_selects_only_outdated_sources(db, world):
    current = make_document(db, world["a"], world["manager"], title="Current")
    stale = make_document(db, world["a"], world["manager"], title="Stale")
    give_chunks(db, current, world["a"])
    give_chunks(db, stale, world["a"], model="text-embedding-ada-002")

    ids = {s.id for s in maintenance.eligible_sources(db, world["a"].id,
                                                      scope=maintenance.SCOPE_STALE)}
    assert ids == {stale.id}


def test_the_failed_scope_selects_only_failed_sources(db, world):
    ready = make_document(db, world["a"], world["manager"], title="Ready")
    failed = make_document(db, world["a"], world["manager"], title="Failed",
                           status=ingestion.STATUS_FAILED)
    give_chunks(db, ready, world["a"])

    ids = {s.id for s in maintenance.eligible_sources(db, world["a"].id,
                                                      scope=maintenance.SCOPE_FAILED)}
    assert ids == {failed.id}


def test_the_all_scope_selects_both_source_types(db, world):
    document = make_document(db, world["a"], world["manager"])
    file = make_file(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"])
    give_chunks(db, file, world["a"])

    sources = maintenance.eligible_sources(db, world["a"].id, scope=maintenance.SCOPE_ALL)
    assert {s.kind for s in sources} == {"DOCUMENT", "INGESTED_FILE"}
    assert {s.id for s in sources} == {document.id, file.id}


def test_an_unindexed_source_is_never_selected(db, world):
    """Re-indexing means indexing again. Indexing something for the first time
    here would spend embedding credits on every file that ever landed."""
    make_document(db, world["a"], world["manager"],
                  status=ingestion.STATUS_NOT_INDEXED)
    for scope in maintenance.SCOPES:
        assert maintenance.eligible_sources(db, world["a"].id, scope=scope) == []


def test_selection_never_crosses_a_project_boundary(db, world):
    """The data boundary, which survives somebody calling the service directly."""
    mine = make_document(db, world["a"], world["manager"])
    theirs = make_document(db, world["b"], world["stranger"])
    give_chunks(db, mine, world["a"], model="old")
    give_chunks(db, theirs, world["b"], model="old")

    for scope in maintenance.SCOPES:
        ids = {s.id for s in maintenance.eligible_sources(db, world["a"].id, scope=scope)}
        assert theirs.id not in ids
    assert {s.id for s in maintenance.eligible_sources(
        db, world["a"].id, scope=maintenance.SCOPE_STALE)} == {mine.id}


def test_an_unknown_scope_is_refused(db, world):
    with pytest.raises(ValueError, match="unknown reindex scope"):
        maintenance.eligible_sources(db, world["a"].id, scope="EVERYTHING")


# --- Job creation and duplicate prevention ----------------------------------

def test_requesting_a_reindex_records_what_it_will_do(db, world):
    stale = make_document(db, world["a"], world["manager"])
    give_chunks(db, stale, world["a"], model="old")

    job = maintenance.request_project_reindex(
        db, project_id=world["a"].id, requested_by_id=world["manager"].id,
    )
    assert job.status == STATUS_QUEUED
    assert job.scope == maintenance.SCOPE_STALE
    assert job.total_sources == 1
    assert job.embedding_model == STUB_MODEL
    assert job.attempt == 1


def test_a_second_run_for_the_same_project_is_refused(db, world):
    """The partial unique index, not a check-then-insert race."""
    maintenance.request_project_reindex(
        db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    db.flush()
    with pytest.raises(maintenance.ReindexRefused) as refusal:
        maintenance.request_project_reindex(
            db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    assert refusal.value.code == maintenance.ERROR_ALREADY_RUNNING


def test_the_database_itself_refuses_two_active_runs(db, world):
    """The guarantee is the index. The service's refusal is a nicer message."""
    for _ in range(2):
        db.add(RagIndexJob(project_id=world["a"].id,
                           requested_by_id=world["manager"].id,
                           status=STATUS_RUNNING))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_two_different_projects_may_run_at_once(db, world):
    maintenance.request_project_reindex(
        db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    maintenance.request_project_reindex(
        db, project_id=world["b"].id, requested_by_id=world["stranger"].id)
    db.flush()
    assert db.query(RagIndexJob).count() >= 2


def test_a_settled_run_does_not_block_the_next_one(db, world):
    first = maintenance.request_project_reindex(
        db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    first.status = STATUS_COMPLETED
    db.flush()
    second = maintenance.request_project_reindex(
        db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    assert second.id != first.id


def test_too_many_sources_is_refused_before_anything_starts(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_REINDEX_MAX_SOURCES", 1)
    for index in range(2):
        document = make_document(db, world["a"], world["manager"], title=f"D{index}")
        give_chunks(db, document, world["a"], model="old")

    with pytest.raises(maintenance.ReindexRefused) as refusal:
        maintenance.request_project_reindex(
            db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    assert refusal.value.code == maintenance.ERROR_TOO_MANY_SOURCES
    assert db.query(RagIndexJob).filter(
        RagIndexJob.project_id == world["a"].id).count() == 0


# --- Stale recovery ---------------------------------------------------------

def _age(db, source, minutes):
    model = Document if isinstance(source, Document) else IngestedFile
    db.execute(
        text(f"UPDATE {model.__tablename__} SET index_status='INDEXING', "
             "index_started_at = :started WHERE id = :id"),
        {"started": datetime.now(timezone.utc) - timedelta(minutes=minutes),
         "id": source.id},
    )
    db.flush()


def test_a_fresh_indexing_run_is_left_alone(db, world, monkeypatch):
    """The single most important property: the reaper must not seize a live run."""
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    document = make_document(db, world["a"], world["manager"])
    _age(db, document, minutes=2)

    maintenance.recover_stale_jobs(db)
    # Asserted on this row, not on the sweep's global count: the sweep is a
    # system-wide operation by design, so a count is about whatever else the
    # database happens to hold.
    db.refresh(document)
    assert document.index_status == ingestion.STATUS_INDEXING
    assert document.index_error is None


def test_a_stranded_document_is_recovered_with_a_readable_reason(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    document = make_document(db, world["a"], world["manager"])
    _age(db, document, minutes=90)

    maintenance.recover_stale_jobs(db)
    db.refresh(document)
    assert document.index_status == ingestion.STATUS_FAILED
    assert document.index_error == maintenance.STALE_RECOVERY_REASON
    assert document.index_started_at is None


def test_a_stranded_ingested_file_is_recovered_too(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    file = make_file(db, world["a"], world["manager"])
    _age(db, file, minutes=90)

    maintenance.recover_stale_jobs(db)
    db.refresh(file)
    assert file.index_status == ingestion.STATUS_FAILED


def test_a_row_claimed_before_the_timestamp_existed_is_treated_as_stale(db, world):
    """Rows stuck in INDEXING from before `index_started_at` was added have a
    NULL start. They have been stuck at least as long as the migration is old."""
    document = make_document(db, world["a"], world["manager"])
    db.execute(text("UPDATE documents SET index_status='INDEXING', "
                    "index_started_at=NULL WHERE id=:id"), {"id": document.id})
    db.flush()

    maintenance.recover_stale_jobs(db)
    db.refresh(document)
    assert document.index_status == ingestion.STATUS_FAILED


def test_recovery_never_deletes_the_previous_runs_chunks(db, world, monkeypatch):
    """A run may have died *after* writing every chunk. Deleting would turn a
    recoverable interruption into data loss."""
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"], count=3)
    _age(db, document, minutes=90)

    maintenance.recover_stale_jobs(db)
    assert len(chunks_for(db, document)) == 3


def test_recovery_leaves_settled_rows_untouched(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    ready = make_document(db, world["a"], world["manager"], title="Ready")
    failed = make_document(db, world["a"], world["manager"], title="Failed",
                           status=ingestion.STATUS_FAILED)
    db.flush()

    maintenance.recover_stale_jobs(db)
    db.refresh(ready)
    db.refresh(failed)
    assert ready.index_status == ingestion.STATUS_READY
    assert failed.index_status == ingestion.STATUS_FAILED


def test_a_recovered_row_can_be_indexed_again(db, world, monkeypatch):
    """Recovery is only useful if it actually unblocks the row: before this,
    an INDEXING row refused every later attempt as "already being indexed"."""
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    document = make_document(db, world["a"], world["manager"])
    _age(db, document, minutes=90)
    maintenance.recover_stale_jobs(db)
    db.refresh(document)

    # The claim now succeeds where it would previously have raised.
    target = ingestion._Target.for_document(document)
    ingestion._claim(db, target, force=False)
    db.refresh(document)
    assert document.index_status == ingestion.STATUS_INDEXING
    assert document.index_started_at is not None


def test_a_stranded_project_job_is_requeued_and_resubmitted(
    db, world, monkeypatch, no_background_pool
):
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    job = RagIndexJob(project_id=world["a"].id, requested_by_id=world["manager"].id,
                      status=STATUS_RUNNING,
                      started_at=datetime.now(timezone.utc) - timedelta(minutes=90))
    db.add(job)
    db.flush()

    maintenance.recover_stale_jobs(db)
    db.refresh(job)
    assert job.status == STATUS_QUEUED
    assert job.attempt == 2
    assert any(args == (job.id,) for _, args, _ in no_background_pool)


def test_a_job_that_keeps_dying_is_given_up_on(db, world, monkeypatch):
    """Bounded, so a deterministically failing run is not retried forever."""
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    monkeypatch.setattr(settings, "RAG_REINDEX_MAX_ATTEMPTS", 3)

    job = RagIndexJob(project_id=world["a"].id, requested_by_id=world["manager"].id,
                      status=STATUS_RUNNING, attempt=3,
                      started_at=datetime.now(timezone.utc) - timedelta(minutes=90))
    db.add(job)
    db.flush()

    maintenance.recover_stale_jobs(db)
    db.refresh(job)
    assert job.status == STATUS_FAILED
    assert job.failure_code == maintenance.ERROR_ATTEMPT_LIMIT


def test_a_fresh_project_job_is_left_alone(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    job = RagIndexJob(project_id=world["a"].id, requested_by_id=world["manager"].id,
                      status=STATUS_RUNNING, started_at=datetime.now(timezone.utc))
    db.add(job)
    db.flush()
    maintenance.recover_stale_jobs(db)
    db.refresh(job)
    assert job.status == STATUS_RUNNING


def test_the_recovery_report_counts_what_it_touched(db, world, monkeypatch):
    """The report drives a log line, so it has to be honest about the count."""
    monkeypatch.setattr(settings, "RAG_INDEX_STALE_MINUTES", 30)
    before = maintenance.recover_stale_jobs(db).total

    document = make_document(db, world["a"], world["manager"])
    _age(db, document, minutes=90)
    after = maintenance.recover_stale_jobs(db)
    # Exactly one more than a sweep over the same database a moment earlier,
    # which is the only count that is stable regardless of what else exists.
    assert after.total == before + 1
    assert any(str(document.id) in detail for detail in after.details)


# --- The API ----------------------------------------------------------------

def _request(db, world, user, project=None, scope=None):
    return rag_api.reindex_project(
        project_id=(project or world["a"]).id,
        payload=RagReindexRequest(scope=scope) if scope else None,
        db=db, current_user=user,
    )


@pytest.fixture()
def no_pool(monkeypatch):
    """The endpoint must enqueue, not execute. Captures what it submitted."""
    submitted = []
    monkeypatch.setattr(maintenance, "submit_project_reindex",
                        lambda job_id: submitted.append(job_id))
    return submitted


def test_the_endpoint_enqueues_and_returns_without_embedding_anything(db, world, no_pool):
    stale = make_document(db, world["a"], world["manager"])
    give_chunks(db, stale, world["a"], model="old")

    payload = _request(db, world, world["manager"])
    assert payload.status == STATUS_QUEUED
    assert payload.total_sources == 1
    assert payload.job_id is not None
    # The heavy work went to the pool, not to this request.
    assert no_pool == [payload.job_id]


def test_the_endpoint_reports_the_corpus_state_without_starting_anything(db, world):
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"], model="old", count=4)

    payload = rag_api.project_reindex_status(
        project_id=world["a"].id, db=db, current_user=world["manager"])
    assert payload.status is None  # never re-indexed
    assert payload.embedding_summary["staleChunks"] == 4
    assert payload.embedding_summary["needsReembedding"] is True


def test_a_stranger_cannot_reindex_another_project(db, world, no_pool):
    """Project isolation at the API boundary."""
    with pytest.raises(HTTPException) as refusal:
        _request(db, world, world["stranger"], project=world["a"])
    assert refusal.value.status_code == 403
    assert no_pool == []


def test_a_stranger_cannot_read_another_projects_reindex_status(db, world):
    with pytest.raises(HTTPException) as refusal:
        rag_api.project_reindex_status(
            project_id=world["a"].id, db=db, current_user=world["stranger"])
    assert refusal.value.status_code == 403


def test_losing_the_upload_permission_blocks_a_reindex(db, world, no_pool, monkeypatch):
    """`document.view` is not enough: a run spends embedding credits."""
    import app.services.authorization as authorization

    monkeypatch.setattr(
        authorization, "has_permission",
        lambda db, user, code, project_id=None: code != "document.upload",
    )
    with pytest.raises(HTTPException) as refusal:
        _request(db, world, world["manager"])
    assert refusal.value.status_code == 403


def test_a_duplicate_request_is_a_409(db, world, no_pool):
    _request(db, world, world["manager"])
    with pytest.raises(HTTPException) as refusal:
        _request(db, world, world["manager"])
    assert refusal.value.status_code == 409
    assert refusal.value.detail["code"] == maintenance.ERROR_ALREADY_RUNNING


def test_the_endpoints_report_unavailable_when_rag_is_off(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    for call in (
        lambda: _request(db, world, world["manager"]),
        lambda: rag_api.project_reindex_status(
            project_id=world["a"].id, db=db, current_user=world["manager"]),
    ):
        with pytest.raises(HTTPException) as refusal:
            call()
        assert refusal.value.status_code == 503


def test_the_status_response_never_carries_internal_failure_detail(db, world):
    job = RagIndexJob(
        project_id=world["a"].id, requested_by_id=world["manager"].id,
        status=STATUS_FAILED, failure_code=maintenance.ERROR_RUN_FAILED,
        failure_message="Traceback: /srv/private_uploads/secret.pdf exploded",
    )
    db.add(job)
    db.flush()

    payload = rag_api.project_reindex_status(
        project_id=world["a"].id, db=db, current_user=world["manager"])
    rendered = payload.model_dump_json()
    assert payload.failure_code == maintenance.ERROR_RUN_FAILED
    assert "Traceback" not in rendered
    assert "private_uploads" not in rendered


def test_an_explicit_scope_is_honoured(db, world, no_pool):
    failed = make_document(db, world["a"], world["manager"],
                           status=ingestion.STATUS_FAILED)
    payload = _request(db, world, world["manager"], scope=maintenance.SCOPE_FAILED)
    assert payload.scope == maintenance.SCOPE_FAILED
    assert payload.total_sources == 1
    assert failed.id


# --- The run ----------------------------------------------------------------

def test_a_run_over_a_project_with_nothing_stale_completes_immediately(db, world):
    document = make_document(db, world["a"], world["manager"])
    give_chunks(db, document, world["a"])
    job = maintenance.request_project_reindex(
        db, project_id=world["a"].id, requested_by_id=world["manager"].id)
    db.commit()

    maintenance.run_project_reindex(job.id)

    db.expire_all()
    settled = db.get(RagIndexJob, job.id)
    assert settled.status == STATUS_COMPLETED
    assert settled.total_sources == 0
    assert settled.duration_ms is not None


def test_a_run_that_is_no_longer_queued_does_not_start(db, world):
    """Re-submitting a job is not an error; running it twice would be."""
    job = RagIndexJob(project_id=world["a"].id, requested_by_id=world["manager"].id,
                      status=STATUS_RUNNING)
    db.add(job)
    db.commit()

    maintenance.run_project_reindex(job.id)
    db.expire_all()
    unchanged = db.get(RagIndexJob, job.id)
    assert unchanged.status == STATUS_RUNNING
    assert unchanged.started_at is None


def test_a_missing_job_is_not_an_error(db, world):
    maintenance.run_project_reindex(uuid4())


def test_a_run_past_the_attempt_limit_gives_up(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_REINDEX_MAX_ATTEMPTS", 2)
    job = RagIndexJob(project_id=world["a"].id, requested_by_id=world["manager"].id,
                      status=STATUS_QUEUED, attempt=5)
    db.add(job)
    db.commit()

    maintenance.run_project_reindex(job.id)
    db.expire_all()
    settled = db.get(RagIndexJob, job.id)
    assert settled.status == STATUS_FAILED
    assert settled.failure_code == maintenance.ERROR_ATTEMPT_LIMIT


# --- Per-source outcomes ----------------------------------------------------

def test_a_source_that_vanished_is_skipped_not_failed(db, world):
    outcome = maintenance.reindex_source(
        db, maintenance._Source(kind="DOCUMENT", id=uuid4()))
    assert outcome.status == "SKIPPED"
    assert "no longer exists" in outcome.reason


def test_a_file_with_no_text_is_skipped_not_failed(db, world):
    """`NotIndexable` is a permanent property, not a retryable failure."""
    file = make_file(db, world["a"], world["manager"], name="plan.dwg")
    file.file_category = "DRAWING"
    file.metadata_json = {"extraction": "NONE", "details": {}}
    db.flush()

    outcome = maintenance.reindex_source(
        db, maintenance._Source(kind="INGESTED_FILE", id=file.id))
    assert outcome.status == "SKIPPED"


def test_a_source_already_being_indexed_is_stepped_around(db, world):
    """A bulk run must not seize a live single-source run."""
    document = make_document(db, world["a"], world["manager"])
    _age(db, document, minutes=1)
    db.commit()

    outcome = maintenance.reindex_source(
        db, maintenance._Source(kind="DOCUMENT", id=document.id))
    assert outcome.status == "SKIPPED"
    assert "already being indexed" in outcome.reason


def test_a_failing_source_is_reported_and_leaves_the_session_usable(db, world):
    """The property partial progress depends on: source 73 failing must not
    take the session — and therefore sources 74 onward — with it."""
    document = make_document(db, world["a"], world["manager"])
    db.commit()

    outcome = maintenance.reindex_source(
        db, maintenance._Source(kind="DOCUMENT", id=document.id))
    assert outcome.status == "FAILED"
    # The session still works, which is what lets the run continue.
    assert db.execute(text("SELECT 1")).scalar() == 1
    db.refresh(document)
    assert document.index_status == ingestion.STATUS_FAILED


# --- Concurrency ------------------------------------------------------------

def test_the_run_is_submitted_to_the_shared_bounded_pool(no_background_pool):
    """Not a new executor. `IFC_MAX_CONCURRENT_PROCESSING` stays one ceiling."""
    job_id = uuid4()
    maintenance.submit_project_reindex(job_id)
    assert no_background_pool == [(maintenance.run_project_reindex, (job_id,), {})]


def test_the_reaper_tick_uses_its_own_advisory_lock():
    """A slow reminder sweep on one worker must not stop the reaper on another."""
    from app.services import scheduler

    assert scheduler.RAG_REAPER_LOCK_KEY != scheduler.REMINDER_LOCK_KEY
    assert "ragReaper" in scheduler.status()
