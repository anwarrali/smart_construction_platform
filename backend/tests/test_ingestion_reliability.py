"""Ingestion that fails honestly, and library documents indexed off the request.

Three changes, each pinned here:

  * **A broken run is a failed job.** When a processing run itself breaks —
    the database, a commit, a defect — the file is marked FAILED with
    PROCESSING_FAILED and the error is raised to the job runner, which retries
    it. A *bad file* stays what it was: recorded FAILED, not retried.
  * **Library PDFs are indexed in the background.** A Documents-library upload
    whose bytes are a PDF queues `rag.index_document` in its own transaction;
    the worker runs the same `index_document` the manual endpoint does.
  * **The file API reports indexing.** `indexStatus`, `indexedAt` and
    `indexError` sit beside the processing `status`.

Fixtures come from `test_rag_ingested_files.py`; embeddings are stubbed and no
test makes a network call. `run_pending` is the worker, in this thread, on the
session's private queue.
"""

from __future__ import annotations

import asyncio
import io
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import text

from app.api import documents as documents_api
from app.api import ingestion as ingestion_api
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentType
from app.models.ingestion import IngestedFile, IngestionJob
from app.services.ingestion import pipeline
from app.services.jobs.runner import run_pending
from app.services.private_storage import private_storage
from app.services.rag import ingestion
from tests.pdf_fixture import build_pdf
from tests.test_rag_ingested_files import (  # noqa: F401 - fixtures used by name
    _FailingEmbeddingClient,
    _embeddings,
    db,
    world,
)

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")


@pytest.fixture(autouse=True)
def isolated(world, monkeypatch):
    """An empty queue per test, the switches on, and the upload side effects removed.

    `world` cleans up projects and files; a library upload also writes a
    notification and a domain event, which have to go first or the project
    cannot be deleted.
    """
    def clear_queue():
        with SessionLocal() as session:
            session.execute(text("DELETE FROM background_jobs WHERE queue = :q"), {"q": settings.JOB_QUEUE})
            session.commit()

    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_AUTO_INDEX_ENABLED", True)
    clear_queue()
    yield
    clear_queue()
    with SessionLocal() as session:
        ids = [world["project"].id, world["other"].id]
        for statement in ("DELETE FROM notifications WHERE project_id = ANY(:p)",
                          "DELETE FROM domain_events WHERE project_id = ANY(:p)"):
            session.execute(text(statement), {"p": ids})
        session.commit()


@pytest.fixture()
def embeddings(monkeypatch):
    state = {"fail": False}
    monkeypatch.setattr(
        ingestion, "EmbeddingService",
        lambda: _embeddings(_FailingEmbeddingClient() if state["fail"] else None),
    )

    class Control:
        @staticmethod
        def fail(value: bool) -> None:
            state["fail"] = value

    return Control


def pdf_bytes(world, pages) -> bytes:
    return build_pdf(world["tmp"] / f"{uuid4().hex}.pdf", pages).read_bytes()


def jobs(db, kind, key, value) -> list[BackgroundJob]:
    db.expire_all()
    return (db.query(BackgroundJob)
            .filter(BackgroundJob.kind == kind, BackgroundJob.payload[key].astext == str(value))
            .order_by(BackgroundJob.created_at).all())


def due_now(db, job) -> None:
    db.execute(text("UPDATE background_jobs SET run_after = now() WHERE id = :id"), {"id": job.id})
    db.commit()


def upload_queued(db, world, filename, payload, monkeypatch) -> IngestedFile:
    """What the upload endpoint does with background processing on."""
    monkeypatch.setattr(settings, "INGESTION_BACKGROUND_PROCESSING_ENABLED", True)
    file = pipeline.register_bytes(
        db, project_id=world["project"].id, uploader_id=world["manager"].id,
        filename=filename, payload=payload,
    )
    pipeline.dispatch(db, file)
    pipeline.submit(db, file)
    db.commit()
    return file


# --- a broken run is a failed, retried job -----------------------------------------

def test_a_run_that_breaks_marks_the_file_failed_and_is_retried(db, world, monkeypatch, embeddings):
    file = upload_queued(db, world, "specification.pdf",
                         pdf_bytes(world, ["Retention is five per cent."]), monkeypatch)
    real_run = pipeline.run

    def broken(*_args, **_kwargs):
        raise RuntimeError("the database connection was lost")

    monkeypatch.setattr(pipeline, "run", broken)
    assert run_pending() == [("ingestion.process_file", "QUEUED")], "a broken run is retried"

    [job] = jobs(db, "ingestion.process_file", "file_id", file.id)
    assert job.attempts == 1 and "connection was lost" in job.last_error
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.status == "FAILED", "never left QUEUED with no explanation"
    assert refreshed.error_code == "PROCESSING_FAILED"
    assert "RuntimeError" in refreshed.error_message
    published = ingestion_api._serialize(refreshed).error
    assert published["code"] == "PROCESSING_FAILED"
    assert "connection" not in str(published), "the internal detail is never published"
    ingestion_row = (db.query(IngestionJob).filter(IngestionJob.file_id == file.id)
                     .order_by(IngestionJob.created_at.desc()).first())
    assert ingestion_row.status == "FAILED"

    # The retry, once due and with the fault gone, finishes the file.
    monkeypatch.setattr(pipeline, "run", real_run)
    due_now(db, job)
    assert run_pending() == [("ingestion.process_file", "SUCCEEDED"), ("rag.index_file", "SUCCEEDED")]
    [job] = jobs(db, "ingestion.process_file", "file_id", file.id)
    assert job.attempts == 2
    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.status == "READY" and refreshed.error_code is None


def test_a_run_that_keeps_breaking_ends_failed_not_succeeded(db, world, monkeypatch):
    monkeypatch.setattr(settings, "JOB_MAX_ATTEMPTS", 1)
    file = upload_queued(db, world, "specification.pdf",
                         pdf_bytes(world, ["Retention is five per cent."]), monkeypatch)
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("deadlock")))
    assert run_pending() == [("ingestion.process_file", "FAILED")]
    db.expire_all()
    assert db.get(IngestedFile, file.id).status == "FAILED"


def test_a_bad_file_is_recorded_failed_and_not_retried(db, world, monkeypatch):
    """Corruption is data: retrying cannot change it, so the job ran and succeeded."""
    file = upload_queued(db, world, "broken.pdf", b"%PDF-1.7\nnot a readable document\n", monkeypatch)
    assert run_pending() == [("ingestion.process_file", "SUCCEEDED")]
    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.status == "FAILED"
    assert refreshed.error_code != "PROCESSING_FAILED"
    assert jobs(db, "rag.index_file", "file_id", file.id) == [], "nothing to index"


def test_a_successful_run_queues_indexing_in_the_same_commit(db, world, monkeypatch, embeddings):
    file = upload_queued(db, world, "specification.pdf",
                         pdf_bytes(world, ["Retention is five per cent."]), monkeypatch)
    assert run_pending() == [("ingestion.process_file", "SUCCEEDED"), ("rag.index_file", "SUCCEEDED")]
    db.expire_all()
    refreshed = db.get(IngestedFile, file.id)
    assert refreshed.status == "READY" and refreshed.index_status == "READY"


# --- the file API reports indexing --------------------------------------------------

def test_the_file_api_reports_index_state_beside_processing(db, world, monkeypatch, embeddings):
    file = upload_queued(db, world, "specification.pdf",
                         pdf_bytes(world, ["Retention is five per cent."]), monkeypatch)
    before = ingestion_api._serialize(db.get(IngestedFile, file.id)).model_dump(by_alias=True)
    assert before["indexStatus"] == "NOT_INDEXED" and before["indexedAt"] is None

    run_pending()
    db.expire_all()
    after = ingestion_api._serialize(db.get(IngestedFile, file.id)).model_dump(by_alias=True)
    assert after["status"] == "READY"
    assert after["indexStatus"] == "READY" and after["indexedAt"] is not None
    assert after["indexError"] is None


def test_a_failed_index_is_visible_on_the_file(db, world, monkeypatch, embeddings):
    embeddings.fail(True)
    file = upload_queued(db, world, "specification.pdf",
                         pdf_bytes(world, ["Retention is five per cent."]), monkeypatch)
    run_pending()
    db.expire_all()
    out = ingestion_api._serialize(db.get(IngestedFile, file.id)).model_dump(by_alias=True)
    assert out["status"] == "READY", "processing succeeded; only indexing failed"
    assert out["indexStatus"] == "FAILED" and out["indexError"]


# --- library documents ----------------------------------------------------------------

def upload_document(db, world, filename, payload, *, project=None, user=None):
    handle = UploadFile(filename=filename, file=io.BytesIO(payload),
                        headers={"content-type": "application/octet-stream"})
    return asyncio.run(documents_api.upload_document(
        file=handle, project_id=str((project or world["project"]).id), title=filename,
        document_type=None, task_id=None, notes=None,
        db=db, current_user=user or world["manager"],
    ))


def document_chunks(db, document_id) -> list[DocumentChunk]:
    return db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()


def test_a_library_pdf_upload_queues_exactly_one_index_job(db, world):
    document = upload_document(db, world, "contract.pdf",
                               pdf_bytes(world, ["The defects liability period is twelve months."]))
    [job] = jobs(db, "rag.index_document", "document_id", document.id)
    assert job.status == "QUEUED"
    assert job.payload == {"document_id": str(document.id), "force": False}
    assert job.project_id == world["project"].id
    assert job.dedupe_key == f"rag.document:{document.id}"
    db.expire_all()
    assert db.get(Document, document.id).index_status == "NOT_INDEXED", "nothing ran in the request"


def test_a_library_file_that_is_not_a_pdf_queues_nothing(db, world):
    """Eligibility is decided by the bytes: an image is stored, not indexed."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    document = upload_document(db, world, "site-photo.png", png)
    assert document.detected_format != "PDF"
    assert jobs(db, "rag.index_document", "document_id", document.id) == []


def test_a_file_disguised_as_a_pdf_is_refused_before_anything_is_queued(db, world):
    """The existing upload check: bytes that do not match the extension never land."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refusal:
        upload_document(db, world, "notes.pdf", b"plain text pretending to be a pdf\n")
    assert refusal.value.status_code == 415
    db.rollback()
    assert db.query(BackgroundJob).filter(BackgroundJob.kind == "rag.index_document",
                                          BackgroundJob.project_id == world["project"].id).count() == 0


def test_a_library_pdf_over_the_indexing_limit_queues_nothing(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_MAX_FILE_MB", 0)
    document = upload_document(db, world, "contract.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    assert jobs(db, "rag.index_document", "document_id", document.id) == []


def test_library_auto_indexing_follows_the_switch(db, world, monkeypatch):
    monkeypatch.setattr(settings, "RAG_AUTO_INDEX_ENABLED", False)
    document = upload_document(db, world, "contract.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    assert jobs(db, "rag.index_document", "document_id", document.id) == []


def test_the_worker_indexes_a_library_document(db, world, embeddings):
    document = upload_document(db, world, "contract.pdf",
                               pdf_bytes(world, ["The defects liability period is twelve months."]))
    assert run_pending() == [("rag.index_document", "SUCCEEDED")]
    db.expire_all()
    refreshed = db.get(Document, document.id)
    assert refreshed.index_status == "READY" and refreshed.page_count == 1
    chunks = document_chunks(db, document.id)
    assert chunks and {chunk.project_id for chunk in chunks} == {world["project"].id}


def test_a_library_index_failure_is_retried_and_the_document_kept(db, world, embeddings):
    document = upload_document(db, world, "contract.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    embeddings.fail(True)
    assert run_pending() == [("rag.index_document", "QUEUED")]
    [job] = jobs(db, "rag.index_document", "document_id", document.id)
    assert "unreachable" in job.last_error
    refreshed = db.get(Document, document.id)
    assert refreshed is not None and refreshed.index_status == "FAILED"
    with private_storage.local_path(refreshed.storage_key) as path:
        assert path.exists(), "a failed index never removes the stored document"

    embeddings.fail(False)
    due_now(db, job)
    assert run_pending() == [("rag.index_document", "SUCCEEDED")]
    db.expire_all()
    assert db.get(Document, document.id).index_status == "READY"


def test_indexing_a_library_document_twice_leaves_one_set_of_chunks(db, world, embeddings):
    document = upload_document(db, world, "contract.pdf",
                               pdf_bytes(world, ["Retention is five per cent.", "Twelve months."]))
    run_pending()
    first = sorted((c.page_number, c.chunk_index, c.content) for c in document_chunks(db, document.id))
    ingestion.submit_document_index(db, db.get(Document, document.id), force=True)
    db.commit()
    ingestion.submit_document_index(db, db.get(Document, document.id), force=True)  # joins the first
    db.commit()
    assert len(jobs(db, "rag.index_document", "document_id", document.id)) == 2, "one done, one live"
    run_pending()
    second = sorted((c.page_number, c.chunk_index, c.content) for c in document_chunks(db, document.id))
    assert second == first


def test_the_manual_document_endpoint_still_indexes_synchronously(db, world, monkeypatch):
    """The Document Assistant reads page and chunk counts from this response."""
    from app.api import rag as rag_api

    monkeypatch.setattr(ingestion, "EmbeddingService", lambda: _embeddings())
    monkeypatch.setattr(settings, "RAG_AUTO_INDEX_ENABLED", False)
    document = upload_document(db, world, "contract.pdf", pdf_bytes(world, ["Concrete grade C30."]))
    result = rag_api.index_document(document_id=document.id, force=False, db=db,
                                    current_user=world["manager"])
    assert result.status == "READY" and result.chunk_count > 0 and result.page_count == 1


def test_a_rolled_back_library_upload_leaves_no_index_job(db, world):
    """The job is part of the upload's transaction, so it cannot outlive it."""
    session = SessionLocal()
    try:
        document = Document(project_id=world["project"].id, uploaded_by_id=world["manager"].id,
                            title="draft.pdf", document_type=DocumentType.OTHER, storage_key="documents/x.pdf",
                            file_url="private://documents/x.pdf", file_size_bytes=10,
                            detected_format="PDF")
        session.add(document)
        session.flush()
        ingestion.submit_document_index(session, document)
        assert run_pending() == [], "uncommitted work is invisible to the worker"
        document_id = document.id
        session.rollback()
    finally:
        session.close()
    assert jobs(db, "rag.index_document", "document_id", document_id) == []


def test_a_stranger_cannot_upload_to_trigger_indexing(db, world):
    """Indexing is reached only through an authorized upload."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as refusal:
        upload_document(db, world, "contract.pdf", pdf_bytes(world, ["Concrete."]), user=world["outsider"])
    assert refusal.value.status_code == 403
    db.rollback()
    assert db.query(BackgroundJob).filter(BackgroundJob.kind == "rag.index_document",
                                          BackgroundJob.project_id == world["project"].id).count() == 0
