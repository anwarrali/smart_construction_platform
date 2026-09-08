"""The pipeline: upload → validate → classify → register → store → process.

    UPLOAD ─► VALIDATE ─► CLASSIFY ─► REGISTER ─► STORE ─► QUEUE
                                                             │
                                              ┌──────────────┘
                                              ▼
                                 EXTRACT ─► NORMALIZE ─► READY / PARTIAL / FAILED

Everything above the queue happens inside the HTTP request, because all of it
is cheap and all of it must be able to *refuse* the upload: a rejected file
should never occupy storage or produce a row. Everything below it happens on
the shared bounded pool, because parsing a 300-page specification inside a
request handler is how a web server stops answering.

## The three properties this module is responsible for

**A failed run never looks like a successful one.** Status, error code and
metadata are written in one commit at the end of a run. There is no window in
which a file reads READY with no metadata, or carries an error code and a
READY status.

**A file is stored exactly once, or not at all.** If registration fails after
the object is written, the object is deleted before the exception leaves. The
alternative is an orphaned object nobody can find, delete or account for.

**Errors are split by audience.** The row keeps the internal detail; the API
publishes only the code and the sentence from `errors.ERRORS`. A processor that
tried to open a path, or a library that named a temporary file, must not have
that reach a response.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from time import perf_counter

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.ingestion import IngestedFile, IngestionJob
from app.services import processing_pool
from app.services.file_intelligence import text_sample
from app.services.ingestion import state
from app.services.ingestion.categories import FileCategory, classify_file
from app.services.ingestion.contracts import ProcessorContext, ProcessorOutcome
from app.services.ingestion.errors import (
    PROCESSING_FAILED, STORAGE_UNAVAILABLE, IngestionRejected, ProcessingError,
)
from app.services.ingestion.processors import build_registry
from app.services.ingestion.validation import (
    INGEST_CATEGORY, sanitize_filename, validate_bytes,
)
from app.services.private_storage import private_storage

logger = logging.getLogger("uvicorn.error").getChild("ingestion.pipeline")

#: Built once, at import. `registry.register` refuses a duplicate claim, so a
#: category with two handlers fails here rather than dispatching to whichever
#: module happened to import first.
registry = build_registry()

#: Bytes read from a stored object to classify it. One megabyte is what every
#: existing upload path already reads for signature validation.
CLASSIFY_HEAD_BYTES = 1024 * 1024


# --- REGISTER ---------------------------------------------------------------

def _storage_key(filename: str) -> str:
    return f"{INGEST_CATEGORY}/{uuid.uuid4()}_{filename}"


def _classify_stored(file: IngestedFile) -> None:
    """Read the head of the stored object and record what it is.

    Total by construction: a classifier that cannot read a PDF must leave the
    file classified as OTHER rather than fail an upload that has otherwise
    succeeded — the same rule `api/documents._classify_upload` already applies.
    """
    head = b""
    try:
        with private_storage.open(file.storage_key) as handle:
            head = handle.read(CLASSIFY_HEAD_BYTES)
    except (OSError, ValueError):
        logger.exception("[Ingestion] could not read %s for classification", file.id)

    sample = None
    try:
        with private_storage.local_path(file.storage_key) as path:
            sample = text_sample(path, "PDF") if head.startswith(b"%PDF-") else None
    except Exception:  # pragma: no cover - sampling is advisory
        sample = None

    result = classify_file(
        filename=file.original_filename, head=head, text_sample=sample,
    )
    file.detected_format = result.detected_format
    file.file_category = result.category.value
    file.document_kind = result.document_kind
    file.classification_json = result.classification_json


def _mark_duplicate(db: Session, file: IngestedFile) -> None:
    """Point at an earlier file with identical bytes, when there is one."""
    if not file.checksum_sha256:
        return
    earlier = (
        db.query(IngestedFile)
        .filter(
            IngestedFile.project_id == file.project_id,
            IngestedFile.checksum_sha256 == file.checksum_sha256,
            IngestedFile.id != file.id,
        )
        .order_by(IngestedFile.created_at.asc())
        .first()
    )
    if earlier is not None:
        file.duplicate_of_id = earlier.duplicate_of_id or earlier.id


def _transition(file: IngestedFile, target: str) -> None:
    state.assert_transition(file.status, target)
    file.status = target
    file.progress = state.PROGRESS.get(target, file.progress)


async def register_upload(
    db: Session,
    *,
    project_id: uuid.UUID,
    uploader_id: uuid.UUID,
    upload: UploadFile,
) -> IngestedFile:
    """Store an uploaded file and register it, ready to be queued.

    Storage goes through `private_storage.save`, which is
    `file_storage.save_private_upload` — the platform's existing upload gate,
    with its allowlist, its magic-byte check and its size ceiling. Nothing here
    re-implements or relaxes any of that.

    Raises `fastapi.HTTPException` from the gate (415, 413, 400) for a refused
    upload; the caller lets those through unchanged so the unified endpoint
    answers exactly as the document and IFC endpoints already do.
    """
    original = (upload.filename or "file")[:255]
    storage_key, size = await private_storage.save(upload, INGEST_CATEGORY)

    file = IngestedFile(
        project_id=project_id,
        uploaded_by_id=uploader_id,
        original_filename=original,
        normalized_filename=sanitize_filename(original),
        content_type=(upload.content_type or "").split(";", 1)[0].strip() or None,
        file_size_bytes=size,
        storage_key=storage_key,
        file_category=FileCategory.OTHER.value,
        status=state.UPLOADED,
        progress=state.PROGRESS[state.UPLOADED],
    )
    try:
        _transition(file, state.VALIDATING)
        with private_storage.local_path(storage_key) as path:
            from app.services.ifc_parser import content_hash

            file.checksum_sha256 = content_hash(path)
        _classify_stored(file)
        _transition(file, state.CLASSIFIED)
        db.add(file)
        db.flush()
        _mark_duplicate(db, file)
    except Exception:
        # The object is already in storage and the row is not. Deleting it here
        # is what keeps storage accountable: every object has a row, and every
        # row has an object.
        private_storage.delete(storage_key)
        raise
    return file


def register_bytes(
    db: Session,
    *,
    project_id: uuid.UUID,
    uploader_id: uuid.UUID,
    filename: str,
    payload: bytes,
    parent: IngestedFile | None = None,
    depth: int = 0,
    package_path: str | None = None,
) -> IngestedFile:
    """Register bytes already in memory — a package member.

    Validation happens *before* storage, unlike the upload path where the gate
    is inside the streaming write. A member that fails the allowlist therefore
    never occupies a byte of storage.
    """
    safe = sanitize_filename(filename)
    validate_bytes(filename=safe, payload=payload)

    storage_key = _storage_key(safe)
    try:
        with private_storage.writable_local_path(storage_key) as target:
            target.write_bytes(payload)
    except (OSError, ValueError) as exc:
        raise IngestionRejected(STORAGE_UNAVAILABLE, str(exc)) from exc

    file = IngestedFile(
        project_id=project_id,
        uploaded_by_id=uploader_id,
        parent_file_id=parent.id if parent else None,
        original_filename=filename[:255],
        normalized_filename=safe,
        content_type=None,
        file_size_bytes=len(payload),
        storage_key=storage_key,
        file_category=FileCategory.OTHER.value,
        status=state.UPLOADED,
        progress=state.PROGRESS[state.UPLOADED],
    )
    try:
        _transition(file, state.VALIDATING)
        from app.services.ifc_parser import content_hash

        with private_storage.local_path(storage_key) as path:
            file.checksum_sha256 = content_hash(path)
        _classify_stored(file)
        if package_path:
            file.classification_json = {
                **file.classification_json, "packagePath": package_path,
            }
        _transition(file, state.CLASSIFIED)
        db.add(file)
        db.flush()
        _mark_duplicate(db, file)
    except Exception:
        private_storage.delete(storage_key)
        raise
    return file


# --- QUEUE ------------------------------------------------------------------

def queue(db: Session, file: IngestedFile) -> IngestionJob:
    """Move a classified file into the queue and record the job.

    The idempotency key is the checksum, matching `IFCProcessingJob`'s
    `parse-{file_hash}`: re-submitting the same bytes reuses the same job row
    and its attempt counter, so a double-clicked upload is visible as one job
    that ran twice rather than as two jobs that each look like the only one.
    """
    _transition(file, state.QUEUED)
    key = f"process-{file.checksum_sha256 or file.id}"
    job = (
        db.query(IngestionJob)
        .filter(
            IngestionJob.file_id == file.id,
            IngestionJob.job_type == "PROCESS",
            IngestionJob.idempotency_key == key,
        )
        .first()
    )
    if job is None:
        job = IngestionJob(file_id=file.id, job_type="PROCESS", idempotency_key=key,
                           status="QUEUED", attempt=1)
        db.add(job)
    else:
        job.status = "QUEUED"
        job.attempt += 1
        job.started_at = None
        job.completed_at = None
        job.duration_ms = None
        job.failure_code = None
        job.failure_message = None
    file.error_code = None
    file.error_message = None
    db.flush()
    return job


# --- PROCESS ----------------------------------------------------------------

def _settle(db: Session, file: IngestedFile, job: IngestionJob | None,
            outcome: ProcessorOutcome, started: float) -> None:
    """Write the whole result in one place, so no partial state can exist."""
    _transition(file, outcome.status)
    file.metadata_json = outcome.metadata or {}
    file.error_code = outcome.error_code
    file.error_message = (outcome.error_message or "")[:4000] or None
    file.processing_completed_at = datetime.now(timezone.utc)
    if job is not None:
        job.status = "FAILED" if outcome.status == state.FAILED else "COMPLETED"
        job.completed_at = file.processing_completed_at
        job.duration_ms = int((perf_counter() - started) * 1000)
        job.failure_code = outcome.error_code if outcome.status == state.FAILED else None
        job.failure_message = file.error_message if outcome.status == state.FAILED else None


def run(db: Session, file: IngestedFile, *, depth: int = 0) -> IngestedFile:
    """Process one file to a settled state. Never raises for a bad file.

    A processor failure is *data* — it belongs on the row, where a person can
    read it and retry — not an exception for a caller to interpret. The only
    thing that escapes is a programming error in the pipeline itself, and that
    is deliberately not caught.
    """
    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.file_id == file.id, IngestionJob.job_type == "PROCESS")
        .order_by(IngestionJob.created_at.desc())
        .first()
    )
    if file.status in {state.CLASSIFIED, state.READY, state.PARTIAL, state.FAILED}:
        job = queue(db, file)

    processor = registry.select(file)
    file.processor_name = processor.name
    file.processing_started_at = datetime.now(timezone.utc)
    started = perf_counter()
    if job is not None:
        job.status = "RUNNING"
        job.started_at = file.processing_started_at
    _transition(file, state.PROCESSING)
    db.flush()

    context = ProcessorContext(db=db, file=file, storage=private_storage, depth=depth)
    try:
        outcome = processor.process(context)
    except ProcessingError as exc:
        outcome = ProcessorOutcome.failed(exc.code, detail=exc.detail)
    except IngestionRejected as exc:
        outcome = ProcessorOutcome.failed(exc.code, detail=exc.detail)
    except Exception as exc:
        # An unexpected processor bug must not leave the file stuck in
        # PROCESSING forever. The type and message are kept internally; the
        # published code says only that processing did not complete.
        logger.exception("[Ingestion] processor %r failed on %s", processor.name, file.id)
        outcome = ProcessorOutcome.failed(
            PROCESSING_FAILED, detail=f"{type(exc).__name__}: {exc}",
        )

    _settle(db, file, job, outcome, started)
    return file


def process_file(file_id: uuid.UUID) -> None:
    """The background entry point: its own session, committed or rolled back.

    A background job cannot borrow the request's session — the request has
    ended and the session with it. Opening and closing one here is what the IFC
    jobs already do (`api/ifc._process_job`), for the same reason.
    """
    db = SessionLocal()
    try:
        file = db.get(IngestedFile, file_id)
        if file is None:
            return
        run(db, file)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[Ingestion] background processing failed for %s", file_id)
    finally:
        db.close()


def submit(file_id: uuid.UUID) -> None:
    """Hand the file to the shared bounded pool."""
    processing_pool.submit(process_file, file_id)


def dispatch(db: Session, file: IngestedFile) -> IngestedFile:
    """Queue a registered file, and start it the way this deployment does.

    With background processing off — the setting the tests and the synchronous
    deployments use — the work runs inline and the caller sees a settled file.
    With it on the file is left QUEUED, and the caller commits before calling
    `submit`: a background session opens its own transaction and would not see
    a row this one has not committed yet.
    """
    queue(db, file)
    if not settings.INGESTION_BACKGROUND_PROCESSING_ENABLED:
        run(db, file)
    return file
