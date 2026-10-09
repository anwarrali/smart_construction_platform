"""Automatic indexing: a file the ingestion pipeline finishes becomes searchable.

    upload ─► persist ─► (same commit) enqueue rag.index_file ─► worker ─► chunks

Pins the six properties the feature is accountable for: a successful ingestion
queues exactly one job, a failed or text-less one queues none, a worker turns
the job into chunks, a failure is retried through the job runner without
losing the file, nothing is indexed twice, and a worker can never see a job
whose file is not yet committed.

Fixtures come from `test_rag_ingested_files.py` so a file here is exactly what
the pipeline produces. Embeddings are stubbed; no test makes a network call.
Jobs go to the session's private queue (`conftest.py`), and `run_pending` is
the worker, in this thread.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.ingestion import IngestedFile
from app.services.ingestion import pipeline
from app.services.jobs.runner import run_pending
from app.services.private_storage import private_storage
from app.services.rag import ingestion
from tests.pdf_fixture import build_pdf
from tests.test_rag_ingested_files import (  # noqa: F401 - fixtures used by name
    _FailingEmbeddingClient,
    _embeddings,
    chunks_of,
    db,
    make_file,
    pdf_file,
    world,
)

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")


@pytest.fixture(autouse=True)
def empty_queue():
    """Each test starts with nothing queued, so `run_pending` runs only its own jobs.

    The session's queue is private to the test run, but shared between these
    tests — several queue a job on purpose and never run it.
    """
    def clear():
        with SessionLocal() as session:
            session.execute(text("DELETE FROM background_jobs WHERE queue = :queue"),
                            {"queue": settings.JOB_QUEUE})
            session.commit()
    clear()
    yield
    clear()


@pytest.fixture(autouse=True)
def auto_index_on(monkeypatch):
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_AUTO_INDEX_ENABLED", True)
    # Ingestion runs inline in these tests, so the pipeline's own trigger is
    # exercised directly; the indexing it queues is what we then run.
    monkeypatch.setattr(settings, "INGESTION_BACKGROUND_PROCESSING_ENABLED", False)


@pytest.fixture()
def embeddings(monkeypatch):
    """Point the worker's indexing at a stub; `.fail(True)` makes the provider fail."""
    state = {"fail": False}

    def factory():
        return _embeddings(_FailingEmbeddingClient() if state["fail"] else None)

    monkeypatch.setattr(ingestion, "EmbeddingService", factory)

    class Control:
        @staticmethod
        def fail(value: bool) -> None:
            state["fail"] = value

    return Control


def index_jobs(db, file_id) -> list[BackgroundJob]:
    db.expire_all()
    return (
        db.query(BackgroundJob)
        .filter(BackgroundJob.kind == "rag.index_file",
                BackgroundJob.payload["file_id"].astext == str(file_id))
        .order_by(BackgroundJob.created_at)
        .all()
    )


def ingest(db, world, filename, payload) -> IngestedFile:
    """Upload through the real pipeline: register, queue, process, commit."""
    file = pipeline.register_bytes(
        db, project_id=world["project"].id, uploader_id=world["manager"].id,
        filename=filename, payload=payload,
    )
    pipeline.dispatch(db, file)
    db.commit()
    return file


def pdf_bytes(world, pages) -> bytes:
    return build_pdf(world["tmp"] / f"{uuid4().hex}.pdf", pages).read_bytes()


# --- 1. a successful ingestion queues exactly one indexing job ---------------------

def test_a_successful_ingestion_queues_exactly_one_indexing_job(db, world):
    file = ingest(db, world, "specification.pdf",
                  pdf_bytes(world, ["Retention is five per cent of each interim payment."]))

    assert file.status in {"READY", "PARTIAL"}
    jobs = index_jobs(db, file.id)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == "QUEUED"
    # Ids only: the worker re-reads the file; no content travels in the job.
    assert job.payload == {"file_id": str(file.id), "force": False}
    assert job.project_id == file.project_id
    assert job.dedupe_key == f"rag.index:{file.id}"
    # Queued, not done: no indexing happened inside the upload.
    db.expire_all()
    assert db.get(IngestedFile, file.id).index_status == ingestion.STATUS_NOT_INDEXED
    assert chunks_of(db, file) == []


# --- 2. a failed or unindexable ingestion queues nothing ---------------------------

def test_a_failed_ingestion_queues_no_indexing_job(db, world):
    file = ingest(db, world, "broken.pdf", b"%PDF-1.7\nthis is not a readable document\n")
    assert file.status == "FAILED"
    assert index_jobs(db, file.id) == []


def test_a_file_with_no_text_queues_no_indexing_job(db, world):
    """A drawing settles READY but has nothing to embed; a job could only fail."""
    file = make_file(db, world, category="DRAWING", extraction="NONE", filename="plan.dwg")
    pipeline._queue_indexing(db, file)
    db.commit()
    assert index_jobs(db, file.id) == []


def test_a_retried_upload_of_the_same_bytes_is_not_indexed_twice(db, world):
    payload = pdf_bytes(world, ["The defects liability period is twelve months."])
    first = ingest(db, world, "contract.pdf", payload)
    second = ingest(db, world, "contract (1).pdf", payload)
    assert second.duplicate_of_id == first.id
    assert len(index_jobs(db, first.id)) == 1
    assert index_jobs(db, second.id) == [], "its text is already searchable through the first"


def test_nothing_is_queued_with_automatic_indexing_switched_off(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_AUTO_INDEX_ENABLED", False)
    file = ingest(db, world, "specification.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    assert index_jobs(db, file.id) == []


def test_nothing_is_queued_with_rag_switched_off(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    file = ingest(db, world, "specification.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    assert index_jobs(db, file.id) == []


# --- 3. the worker turns the job into chunks -------------------------------------------

def test_the_worker_indexes_the_file_and_the_job_succeeds(db, world, embeddings):
    file = ingest(db, world, "specification.pdf",
                  pdf_bytes(world, ["Retention is five per cent of each interim payment."]))

    assert run_pending() == [("rag.index_file", "SUCCEEDED")]

    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.index_status == ingestion.STATUS_READY
    assert refreshed.indexed_at is not None
    assert chunks_of(db, file), "indexing must actually produce chunks"
    [job] = index_jobs(db, file.id)
    # What an operator can read off the job: queued, started, finished, attempts.
    assert job.status == "SUCCEEDED" and job.attempts == 1
    assert job.created_at <= job.started_at <= job.finished_at
    assert job.last_error is None


# --- 4. a failure is retried through the job runner, and the file survives ---------------

def test_an_indexing_failure_is_retried_and_the_file_is_kept(db, world, embeddings):
    file = ingest(db, world, "specification.pdf",
                  pdf_bytes(world, ["Retention is five per cent of each interim payment."]))
    embeddings.fail(True)

    assert run_pending() == [("rag.index_file", "QUEUED")], "a failure goes back on the queue"
    [job] = index_jobs(db, file.id)
    assert job.attempts == 1
    assert "unreachable" in job.last_error, "the reason is on the job"
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed is not None, "a failed index must not remove the file"
    assert refreshed.status in {"READY", "PARTIAL"}
    assert refreshed.index_status == ingestion.STATUS_FAILED, "never shown as indexed"
    assert chunks_of(db, file) == []
    with private_storage.local_path(refreshed.storage_key) as path:
        assert path.exists(), "the stored bytes stay where they were"

    # The retry, once due, succeeds: same job, second attempt.
    embeddings.fail(False)
    db.execute(text("UPDATE background_jobs SET run_after = now() WHERE id = :id"), {"id": job.id})
    db.commit()
    assert run_pending() == [("rag.index_file", "SUCCEEDED")]
    [job] = index_jobs(db, file.id)
    assert job.attempts == 2
    assert db.get(IngestedFile, file.id).index_status == ingestion.STATUS_READY
    assert chunks_of(db, file)


def test_a_file_that_keeps_failing_ends_failed_not_succeeded(db, world, embeddings, monkeypatch):
    monkeypatch.setattr(settings, "JOB_MAX_ATTEMPTS", 1)
    file = ingest(db, world, "specification.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    embeddings.fail(True)
    assert run_pending() == [("rag.index_file", "FAILED")]
    [job] = index_jobs(db, file.id)
    assert job.status == "FAILED" and job.last_error


# --- 5. nothing is indexed twice ---------------------------------------------------------

def test_the_same_trigger_twice_queues_one_job(db, world):
    """A second request while the first is queued joins it — automatic or manual."""
    file = pdf_file(db, world, ["Retention is five per cent."])
    ingestion.submit_ingested_file_index(db, file)
    db.commit()
    ingestion.submit_ingested_file_index(db, file)   # e.g. the manual "index" action
    db.commit()
    assert len(index_jobs(db, file.id)) == 1


def test_indexing_twice_leaves_one_set_of_chunks(db, world, embeddings):
    file = pdf_file(db, world, ["Retention is five per cent.", "The period is twelve months."])
    ingestion.submit_ingested_file_index(db, file)
    db.commit()
    run_pending()
    first = [(chunk.page_number, chunk.chunk_index, chunk.content) for chunk in chunks_of(db, file)]
    assert first

    # Again — a manual retry, or a job retried after a crash.
    ingestion.submit_ingested_file_index(db, file, force=True)
    db.commit()
    run_pending()
    second = [(chunk.page_number, chunk.chunk_index, chunk.content) for chunk in chunks_of(db, file)]
    assert second == first, "re-indexing replaces; it never appends"


# --- 6. a worker never sees a job whose file is not committed ------------------------------

def test_a_worker_cannot_start_before_the_upload_commits(db, world, embeddings):
    payload = pdf_bytes(world, ["Retention is five per cent of each interim payment."])
    uploading = SessionLocal()
    try:
        file = pipeline.register_bytes(
            uploading, project_id=world["project"].id, uploader_id=world["manager"].id,
            filename="specification.pdf", payload=payload,
        )
        pipeline.dispatch(uploading, file)       # settles READY and queues indexing
        file_id = file.id

        # Not committed: the worker sees neither the job nor the file.
        assert run_pending() == []
        with SessionLocal() as other:
            assert other.get(IngestedFile, file_id) is None

        uploading.commit()
    finally:
        uploading.close()

    # Committed together, so the worker that finds the job finds the file.
    assert run_pending() == [("rag.index_file", "SUCCEEDED")]
    db.expire_all()
    assert db.get(IngestedFile, file_id).index_status == ingestion.STATUS_READY


def test_a_rolled_back_upload_leaves_no_indexing_job(db, world):
    payload = pdf_bytes(world, ["Concrete grade C30."])
    uploading = SessionLocal()
    try:
        file = pipeline.register_bytes(
            uploading, project_id=world["project"].id, uploader_id=world["manager"].id,
            filename="specification.pdf", payload=payload,
        )
        pipeline.dispatch(uploading, file)
        file_id = file.id
        uploading.rollback()
    finally:
        uploading.close()
    assert index_jobs(db, file_id) == []
    assert run_pending() == []
