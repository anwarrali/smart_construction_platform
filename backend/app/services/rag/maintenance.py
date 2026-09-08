"""Re-embedding an existing corpus, and recovering runs that died.

Three jobs, and they are here together because they share one question — *is
this row's index still good?* — asked from three directions:

  * **`needs_reembedding`** asks it of a source's chunks, against the
    configured model. That is the model-change case.
  * **`reindex_project`** acts on the answer for a whole project, on the
    shared bounded pool.
  * **`recover_stale_jobs`** asks it of rows that claim to be indexing and are
    not, because the worker holding them is gone.

## What this deliberately does not do

It does not re-implement indexing. Every source goes through
`ingestion.index_document` / `index_ingested_file`, so a re-index and a first
index produce the same chunks by the same path — there is no second definition
of "indexed" to drift.

It also does not touch the HNSW index. pgvector maintains it on ordinary
INSERT and DELETE; a `REINDEX` per run would rebuild the whole structure to
replace a handful of rows. If index maintenance is ever genuinely needed it is
a database operation on a schedule, not something an application re-index does
on the user's behalf.

## Staleness is derived, never stored

A chunk records the model and dimension it was embedded with. A source is
stale when any of its chunks disagrees with the configured model — computed
by comparing those columns, not by a flag somebody has to remember to set.
A flag would be wrong the moment configuration changed without the flag being
updated, which is exactly the moment it matters.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.ingestion import IngestedFile
from app.models.rag_job import (
    ACTIVE_STATUSES, STATUS_COMPLETED, STATUS_FAILED, STATUS_PARTIAL,
    STATUS_QUEUED, STATUS_RUNNING, RagIndexJob,
)
from app.services import processing_pool
from app.services.rag import ingestion
from app.services.rag.ingestion import (
    STATUS_INDEXING, STATUS_READY,
    IndexingFailed, IndexingInProgress, NotIndexable,
)

logger = logging.getLogger("uvicorn.error").getChild("rag.maintenance")

#: Which sources a run touches.
SCOPE_STALE = "STALE"
SCOPE_FAILED = "FAILED"
SCOPE_ALL = "ALL"
SCOPES = (SCOPE_STALE, SCOPE_FAILED, SCOPE_ALL)

#: Published failure codes. Safe to return; carry no internal detail.
ERROR_ALREADY_RUNNING = "REINDEX_ALREADY_RUNNING"
ERROR_ATTEMPT_LIMIT = "REINDEX_ATTEMPT_LIMIT"
ERROR_TOO_MANY_SOURCES = "REINDEX_TOO_MANY_SOURCES"
ERROR_RUN_FAILED = "REINDEX_RUN_FAILED"

#: Recorded on a row the reaper took back, so "why is this FAILED when nobody
#: reported an error" has an answer.
STALE_RECOVERY_REASON = (
    "Indexing was interrupted and did not finish. The text was left unchanged; "
    "retry to index it again."
)


class ReindexRefused(Exception):
    """A run was not started, and the reason is safe to publish."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


# --- Which sources need re-embedding ----------------------------------------


def _stale_chunk_predicate():
    """A chunk that was embedded by something other than the current model.

    Both halves matter. The model name catches a switch between two models of
    the same width; the dimension catches a switch to a different width, which
    the `vector(N)` column would refuse to store — so those chunks are stale
    *and* unwritable until the schema moves with them.
    """
    return or_(
        DocumentChunk.embedding_model != settings.OPENAI_EMBEDDING_MODEL,
        DocumentChunk.embedding_dim != settings.RAG_EMBEDDING_DIMENSIONS,
    )


def source_needs_reembedding(db: Session, source) -> bool:
    """Whether this `Document` or `IngestedFile` holds outdated vectors.

    A source with no chunks at all is not stale — it is unindexed, which is a
    different thing and a different remedy.
    """
    column = (
        DocumentChunk.document_id if isinstance(source, Document)
        else DocumentChunk.ingested_file_id
    )
    return db.execute(
        select(func.count(DocumentChunk.id))
        .where(column == source.id, _stale_chunk_predicate())
    ).scalar() > 0


def project_reembedding_summary(db: Session, project_id: uuid.UUID) -> dict:
    """What a project's corpus is embedded with, and how much of it is stale.

    Answers "does this project need re-embedding, and how much would it cost"
    without starting anything — which is what makes the decision deliberate
    rather than a button somebody presses to find out.
    """
    rows = db.execute(
        select(
            DocumentChunk.embedding_model,
            DocumentChunk.embedding_dim,
            func.count(DocumentChunk.id),
        )
        .where(DocumentChunk.project_id == project_id)
        .group_by(DocumentChunk.embedding_model, DocumentChunk.embedding_dim)
    ).all()

    current = settings.OPENAI_EMBEDDING_MODEL
    dimensions = settings.RAG_EMBEDDING_DIMENSIONS
    stale = sum(count for model, dim, count in rows
                if model != current or dim != dimensions)
    return {
        "configuredModel": current,
        "configuredDimensions": dimensions,
        "totalChunks": sum(count for _, _, count in rows),
        "staleChunks": stale,
        "needsReembedding": stale > 0,
        "models": [
            {"model": model, "dimensions": dim, "chunks": count,
             "current": model == current and dim == dimensions}
            for model, dim, count in rows
        ],
    }


# --- Selecting a project's sources ------------------------------------------


@dataclass(frozen=True)
class _Source:
    """One thing to re-index, with just enough to do it and report on it."""

    kind: str  #: "DOCUMENT" or "INGESTED_FILE"
    id: uuid.UUID

    @property
    def label(self) -> str:
        return "document" if self.kind == "DOCUMENT" else "file"


def _stale_source_ids(db: Session, project_id: uuid.UUID, column):
    """Ids in this project whose chunks disagree with the configured model."""
    return select(column).where(
        DocumentChunk.project_id == project_id,
        column.is_not(None),
        _stale_chunk_predicate(),
    ).distinct()


def eligible_sources(
    db: Session, project_id: uuid.UUID, *, scope: str = SCOPE_STALE
) -> list[_Source]:
    """The sources a run of this scope would touch, in a stable order.

    **The project filter is on every branch.** These queries are the data
    boundary: a run started for project A must not be able to select a source
    belonging to project B, however the caller reached it. Authorization at the
    API is the first gate; this is the second, and it is the one that survives
    somebody calling the service directly.

    Scopes, and why there are three:

      * `STALE` — only sources whose vectors disagree with the configured
        model. The default, because it is the model-change case and because it
        is the cheapest: a project already on the current model selects
        nothing and the run completes immediately.
      * `FAILED` — only sources whose last index failed. The retry case.
      * `ALL` — every source that has been indexed or attempted. The blunt
        instrument, for a corpus somebody has reason to distrust.

    A NOT_INDEXED source is in none of them. Re-indexing means indexing again;
    indexing something for the first time is `POST /rag/documents/{id}/index`,
    and doing it implicitly here would spend embedding credits on every file
    that ever landed in the project.
    """
    if scope not in SCOPES:
        raise ValueError(f"unknown reindex scope {scope!r}")

    sources: list[_Source] = []
    for kind, model, column in (
        ("DOCUMENT", Document, DocumentChunk.document_id),
        ("INGESTED_FILE", IngestedFile, DocumentChunk.ingested_file_id),
    ):
        query = select(model.id).where(model.project_id == project_id)
        if scope == SCOPE_STALE:
            query = query.where(
                model.index_status == STATUS_READY,
                model.id.in_(_stale_source_ids(db, project_id, column)),
            )
        elif scope == SCOPE_FAILED:
            query = query.where(model.index_status == ingestion.STATUS_FAILED)
        else:
            query = query.where(
                model.index_status.in_([STATUS_READY, ingestion.STATUS_FAILED])
            )
        # Ordered so a run is reproducible and a partial run's progress means
        # something: "it got through the first 40" is only useful if the order
        # is the same next time.
        sources.extend(
            _Source(kind=kind, id=row[0])
            for row in db.execute(query.order_by(model.created_at, model.id)).all()
        )
    return sources


# --- Re-indexing one source -------------------------------------------------


@dataclass
class SourceOutcome:
    source: _Source
    status: str  #: "SUCCEEDED" | "FAILED" | "SKIPPED"
    chunk_count: int = 0
    reason: str | None = None


def reindex_source(db: Session, source: _Source, *, force: bool = False) -> SourceOutcome:
    """Re-index one existing source, through the ordinary indexing pipeline.

    No original upload is needed: a `Document` is read back from its stored
    file and an `IngestedFile` from private storage, exactly as a first index
    does. `add_chunks` replaces rather than appends, so running this twice
    produces the same chunks, not twice as many.

    Every failure mode is caught and reported rather than raised. A run over
    100 sources must not lose the 72 that worked because the 73rd was corrupt,
    and the session must come back usable — which the state machine guarantees
    by rolling back before it records a failure.
    """
    row = db.get(Document if source.kind == "DOCUMENT" else IngestedFile, source.id)
    if row is None:
        # Deleted between selection and execution. Not a failure of anything.
        return SourceOutcome(source, "SKIPPED", reason="no longer exists")

    try:
        if source.kind == "DOCUMENT":
            result = ingestion.index_document(db, row, force=force)
        else:
            result = ingestion.index_ingested_file(db, row, force=force)
    except NotIndexable as error:
        # The file never had text to index. Skipping is the correct outcome
        # and leaves the row untouched.
        return SourceOutcome(source, "SKIPPED", reason=str(error))
    except IndexingInProgress:
        # Somebody else is indexing it right now. Stepping aside is right:
        # seizing a live run is what `force` is for, and a bulk re-index is
        # not the place to use it.
        return SourceOutcome(source, "SKIPPED", reason="already being indexed")
    except IndexingFailed as error:
        # Already persisted to the row's `index_error` by the state machine.
        return SourceOutcome(source, "FAILED", reason=str(error))
    except Exception as error:  # pragma: no cover - defensive
        # A defect rather than a data problem. The row may still read
        # INDEXING; the reaper is what recovers it.
        logger.exception("[RAG] re-index of %s %s raised", source.label, source.id)
        db.rollback()
        return SourceOutcome(source, "FAILED", reason=f"{type(error).__name__}")

    return SourceOutcome(source, "SUCCEEDED", chunk_count=result.chunk_count)


# --- The project run --------------------------------------------------------


def request_project_reindex(
    db: Session, *, project_id: uuid.UUID, requested_by_id: uuid.UUID,
    scope: str = SCOPE_STALE,
) -> RagIndexJob:
    """Create the job row, or refuse because one is already active.

    **The refusal is a database guarantee, not a check.** Two simultaneous
    requests both insert; the partial unique index lets exactly one through and
    the other gets an `IntegrityError`, which becomes `ReindexRefused`. Reading
    first and inserting second would be a race whose loser starts a second full
    re-embedding pass over the same project.

    Nothing heavy happens here. The caller commits and hands the id to the
    pool.
    """
    if scope not in SCOPES:
        raise ValueError(f"unknown reindex scope {scope!r}")

    sources = eligible_sources(db, project_id, scope=scope)
    if len(sources) > settings.RAG_REINDEX_MAX_SOURCES:
        raise ReindexRefused(
            ERROR_TOO_MANY_SOURCES,
            f"{len(sources)} sources exceed the {settings.RAG_REINDEX_MAX_SOURCES} "
            "limit for one run. Re-index in narrower scopes, or raise the limit "
            "deliberately.",
        )

    job = RagIndexJob(
        project_id=project_id, requested_by_id=requested_by_id, scope=scope,
        status=STATUS_QUEUED, total_sources=len(sources),
        embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise ReindexRefused(
            ERROR_ALREADY_RUNNING,
            "A re-index is already running for this project. Wait for it to "
            "finish, or read its status.",
        ) from error
    return job


def run_project_reindex(job_id: uuid.UUID) -> None:
    """Execute one queued run. The background entry point.

    Its own session, because the request that created the job has ended and
    taken its session with it — the same shape every other background job in
    this codebase uses.

    **Transaction boundaries.** There is no single transaction around the run.
    Each source is committed by the indexing state machine as it finishes, so a
    crash at source 73 leaves 1–72 genuinely indexed rather than rolling back
    an hour of embedding work. The job row's counters are committed alongside,
    so its progress is real rather than a guess made at the end.
    """
    db = SessionLocal()
    started = perf_counter()
    try:
        job = db.get(RagIndexJob, job_id)
        if job is None:
            return
        if job.status != STATUS_QUEUED:
            # Already running or already settled. Re-submitting a job is not
            # an error — the reaper may have re-queued it — but running it
            # twice concurrently would be.
            logger.info("[RAG] reindex job %s is %s; not starting", job_id, job.status)
            return
        if job.attempt > settings.RAG_REINDEX_MAX_ATTEMPTS:
            _settle(db, job, STATUS_FAILED, started,
                    code=ERROR_ATTEMPT_LIMIT,
                    message=f"gave up after {job.attempt - 1} attempts")
            return

        project_id = job.project_id
        scope = job.scope
        job.status = STATUS_RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.embedding_model = settings.OPENAI_EMBEDDING_MODEL
        db.commit()

        sources = eligible_sources(db, project_id, scope=scope)
        job = db.get(RagIndexJob, job_id)
        job.total_sources = len(sources)
        db.commit()

        logger.info(
            "[RAG] reindex started: project=%s scope=%s sources=%s model=%s",
            project_id, scope, len(sources), settings.OPENAI_EMBEDDING_MODEL,
        )

        succeeded = failed = skipped = chunks = 0
        for source in sources:
            outcome = reindex_source(db, source)
            if outcome.status == "SUCCEEDED":
                succeeded += 1
                chunks += outcome.chunk_count
            elif outcome.status == "FAILED":
                failed += 1
                logger.warning(
                    "[RAG] reindex could not process %s %s: %s",
                    source.label, source.id, outcome.reason,
                )
            else:
                skipped += 1

            # Committed per source, so an interrupted run's counters are true.
            job = db.get(RagIndexJob, job_id)
            job.processed_sources = succeeded + failed + skipped
            job.succeeded_sources = succeeded
            job.failed_sources = failed
            job.skipped_sources = skipped
            job.chunk_count = chunks
            db.commit()

        job = db.get(RagIndexJob, job_id)
        if failed and succeeded:
            status = STATUS_PARTIAL
        elif failed:
            status = STATUS_FAILED
        else:
            status = STATUS_COMPLETED
        _settle(
            db, job, status, started,
            code=ERROR_RUN_FAILED if status == STATUS_FAILED else None,
            message=f"{failed} of {len(sources)} sources failed" if failed else None,
        )
        logger.info(
            "[RAG] reindex finished: project=%s status=%s succeeded=%s failed=%s "
            "skipped=%s chunks=%s",
            project_id, status, succeeded, failed, skipped, chunks,
        )
    except Exception as error:  # pragma: no cover - defensive
        logger.exception("[RAG] reindex job %s failed", job_id)
        db.rollback()
        job = db.get(RagIndexJob, job_id)
        if job is not None and job.is_active:
            _settle(db, job, STATUS_FAILED, started,
                    code=ERROR_RUN_FAILED, message=f"{type(error).__name__}: {error}")
    finally:
        db.close()


def _settle(db: Session, job: RagIndexJob, status: str, started: float,
            *, code: str | None = None, message: str | None = None) -> None:
    job.status = status
    job.completed_at = datetime.now(timezone.utc)
    job.duration_ms = int((perf_counter() - started) * 1000)
    job.failure_code = code
    job.failure_message = (message or "")[:2000] or None
    db.commit()


def submit_project_reindex(job_id: uuid.UUID) -> None:
    """Hand the run to the shared bounded pool.

    The *same* pool IFC parsing, file processing and single-file indexing use,
    so `IFC_MAX_CONCURRENT_PROCESSING` stays one ceiling over all heavy work
    rather than one of several. A re-index that embedded hundreds of chunks in
    the request path is exactly what this avoids.
    """
    processing_pool.submit(run_project_reindex, job_id)


# --- Stale recovery ---------------------------------------------------------


@dataclass
class RecoveryReport:
    documents: int = 0
    files: int = 0
    jobs: int = 0
    #: Ids touched, for the log line. Never returned to a client.
    details: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.documents + self.files + self.jobs


def _stale_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(
        minutes=max(1, settings.RAG_INDEX_STALE_MINUTES)
    )


def recover_stale_jobs(db: Session) -> RecoveryReport:
    """Take back rows whose indexing run is gone, and re-open them for retry.

    A worker that dies mid-index leaves `index_status = INDEXING` forever: the
    concurrency guard cannot tell a dead run from a live one, so every later
    attempt is refused as "already being indexed". Before this, the only way
    out was somebody noticing and passing `force=true`.

    ## What makes a row stale

    It has been INDEXING since before the cutoff. `index_started_at` is
    stamped by `_claim` and cleared when a run settles, so it means exactly
    "this run began then" — unlike `updated_at`, which any edit moves, or
    `indexed_at`, which is written only on success.

    A NULL start on an INDEXING row is treated as stale. Those are rows
    claimed before that column existed; they have been stuck at least as long
    as the migration is old, which is longer than any cutoff.

    ## What it does not do

    **It does not delete chunks.** The previous run's text is left exactly
    where it is. Deleting would turn a recoverable interruption into data loss
    for a source that may still be perfectly indexed — the run might have died
    after writing every chunk and before writing the status. Retrying replaces
    them wholesale anyway, because `add_chunks` replaces rather than appends.

    **It does not retry automatically.** The row moves to FAILED with a
    readable reason, which makes it eligible for an explicit retry or a
    `FAILED`-scoped project run. An automatic retry here would be a loop with
    no bound: a source that fails deterministically would be picked up by
    every sweep forever.
    """
    cutoff = _stale_cutoff()
    report = RecoveryReport()

    for model, attribute in ((Document, "documents"), (IngestedFile, "files")):
        stale = db.execute(
            select(model.id).where(
                model.index_status == STATUS_INDEXING,
                or_(model.index_started_at < cutoff, model.index_started_at.is_(None)),
            )
        ).scalars().all()
        if not stale:
            continue
        db.execute(
            update(model).where(model.id.in_(stale)).values(
                index_status=ingestion.STATUS_FAILED,
                index_error=STALE_RECOVERY_REASON,
                index_started_at=None,
                indexed_at=None,
            )
        )
        setattr(report, attribute, len(stale))
        report.details.extend(f"{model.__name__.lower()}:{item}" for item in stale)

    # A project run whose worker died leaves the job row RUNNING with the same
    # problem, and its partial unique index then blocks every future run for
    # that project. Re-queued rather than failed, so the work resumes — bounded
    # by `attempt`, which is what stops that being an infinite loop.
    stale_jobs = db.execute(
        select(RagIndexJob).where(
            RagIndexJob.status == STATUS_RUNNING,
            or_(RagIndexJob.started_at < cutoff, RagIndexJob.started_at.is_(None)),
        )
    ).scalars().all()
    for job in stale_jobs:
        if job.attempt >= settings.RAG_REINDEX_MAX_ATTEMPTS:
            job.status = STATUS_FAILED
            job.failure_code = ERROR_ATTEMPT_LIMIT
            job.failure_message = (
                f"interrupted {job.attempt} times; not retried again"
            )
            job.completed_at = datetime.now(timezone.utc)
        else:
            job.status = STATUS_QUEUED
            job.attempt += 1
            job.started_at = None
            job.failure_code = None
            job.failure_message = None
        report.jobs += 1
        report.details.append(f"ragindexjob:{job.id}")

    db.commit()

    if report.total:
        # Ids only. No document titles, no filenames, no text.
        logger.info(
            "[RAG] recovered %s stranded indexing run(s) older than %s minutes: %s",
            report.total, settings.RAG_INDEX_STALE_MINUTES, ", ".join(report.details[:50]),
        )
    # Re-queued jobs are handed back to the pool after the commit, so the pool
    # worker sees a QUEUED row rather than one this transaction still holds.
    for job in stale_jobs:
        if job.status == STATUS_QUEUED:
            submit_project_reindex(job.id)
    return report


def latest_job(db: Session, project_id: uuid.UUID) -> RagIndexJob | None:
    """The most recent run for a project, active or settled."""
    return db.execute(
        select(RagIndexJob)
        .where(RagIndexJob.project_id == project_id)
        .order_by(RagIndexJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def active_job(db: Session, project_id: uuid.UUID) -> RagIndexJob | None:
    return db.execute(
        select(RagIndexJob).where(
            RagIndexJob.project_id == project_id,
            RagIndexJob.status.in_(ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()
