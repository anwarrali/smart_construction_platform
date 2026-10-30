"""The queue's operations: enqueue, claim, heartbeat, finish, reap.

Each operation is one short transaction of its own, never the work's: a worker
claims a job and commits, runs it with sessions of its own, then records the
outcome and commits again. A job that dies half-way therefore leaves a RUNNING
row with an old heartbeat — which `reap` hands back — rather than a rolled-back
claim nobody can see.

## The ceiling is global

`claim` serializes on a transaction-scoped advisory lock and refuses when
`IFC_MAX_CONCURRENT_PROCESSING` jobs are already running in the queue. That is
the whole fleet's ceiling: every API process and every worker counts against
the same number. The in-memory pool this replaces bounded each process
separately, so two uvicorn workers quietly allowed twice the memory the setting
was written to cap.
"""

from __future__ import annotations

import os
import socket
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.background_job import (
    ACTIVE_DEDUPE_INDEX,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_REJECTED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    BackgroundJob,
)

#: Serializes claims, so the running-count check and the claim are one step.
CLAIM_LOCK_KEY = 776_120_440

#: First retry waits this long, doubling each attempt.
RETRY_BASE_SECONDS = 30


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    kind: str
    payload: dict = field(default_factory=dict)
    attempt: int = 1


def worker_identity() -> str:
    """Who holds a job: host, process and thread, enough to find it in logs."""
    return f"{socket.gethostname()}:{os.getpid()}:{threading.current_thread().name}"[:120]


def enqueue(
    db: Session,
    kind: str,
    payload: dict | None = None,
    *,
    dedupe_key: str | None = None,
    project_id: uuid.UUID | None = None,
    max_attempts: int | None = None,
    queue: str | None = None,
) -> uuid.UUID:
    """Add a job in the caller's transaction, and return its id.

    Nothing runs until the caller commits — which is the point: a job for an
    upload that rolled back never exists. With a `dedupe_key`, a second request
    while one is still queued or running returns the live job's id instead of
    queuing the work twice.
    """
    queue = queue or settings.JOB_QUEUE
    values = {
        "id": uuid.uuid4(),
        "queue": queue,
        "kind": kind,
        "payload": _jsonable(payload or {}),
        "dedupe_key": dedupe_key,
        "project_id": project_id,
        "max_attempts": max_attempts or settings.JOB_MAX_ATTEMPTS,
        "status": STATUS_QUEUED,
    }
    statement = insert(BackgroundJob).values(**values)
    if dedupe_key is None:
        return db.execute(statement.returning(BackgroundJob.id)).scalar_one()
    statement = statement.on_conflict_do_nothing(
        index_elements=["queue", "dedupe_key"],
        index_where=text("status IN ('QUEUED', 'RUNNING') AND dedupe_key IS NOT NULL"),
    ).returning(BackgroundJob.id)
    # Twice at most: the live job we collided with can finish between the
    # insert and the lookup, and then the second insert simply succeeds.
    for _ in range(2):
        inserted = db.execute(statement).scalar()
        if inserted is not None:
            return inserted
        live = db.execute(
            text(
                "SELECT id FROM background_jobs WHERE queue = :queue AND dedupe_key = :key "
                "AND status IN ('QUEUED', 'RUNNING')"
            ),
            {"queue": queue, "key": dedupe_key},
        ).scalar()
        if live is not None:
            return live
    raise RuntimeError(f"Could not enqueue {kind!r} with dedupe key {dedupe_key!r}")


def claim(db: Session, *, worker: str, capacity: int, queue: str | None = None) -> ClaimedJob | None:
    """Take the next due job, or None if there is none or the ceiling is reached."""
    queue = queue or settings.JOB_QUEUE
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CLAIM_LOCK_KEY})
        running = db.execute(
            text("SELECT count(*) FROM background_jobs WHERE queue = :queue AND status = 'RUNNING'"),
            {"queue": queue},
        ).scalar_one()
        if running >= capacity:
            db.rollback()
            return None
        row = db.execute(
            text(
                """
                UPDATE background_jobs SET
                    status = 'RUNNING', attempts = attempts + 1, locked_by = :worker,
                    started_at = now(), heartbeat_at = now(), finished_at = NULL, updated_at = now()
                WHERE id = (
                    SELECT id FROM background_jobs
                    WHERE queue = :queue AND status = 'QUEUED' AND run_after <= now()
                    ORDER BY run_after, created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, kind, payload, attempts
                """
            ),
            {"queue": queue, "worker": worker},
        ).first()
        db.commit()
    except Exception:
        db.rollback()
        raise
    if row is None:
        return None
    return ClaimedJob(id=row.id, kind=row.kind, payload=dict(row.payload or {}), attempt=row.attempts)


def heartbeat(db: Session, job_ids: list[uuid.UUID]) -> None:
    if not job_ids:
        return
    db.execute(
        text("UPDATE background_jobs SET heartbeat_at = now() WHERE id = ANY(:ids) AND status = 'RUNNING'"),
        {"ids": job_ids},
    )
    db.commit()


def succeed(db: Session, job_id: uuid.UUID) -> None:
    db.execute(
        text(
            "UPDATE background_jobs SET status = :status, finished_at = now(), locked_by = NULL, "
            "last_error = NULL, updated_at = now() WHERE id = :id"
        ),
        {"status": STATUS_SUCCEEDED, "id": job_id},
    )
    db.commit()


def reject(db: Session, job_id: uuid.UUID, reason: str) -> None:
    """Not runnable here at all — an unknown kind. Retrying cannot help."""
    db.execute(
        text(
            "UPDATE background_jobs SET status = :status, finished_at = now(), locked_by = NULL, "
            "last_error = :reason, updated_at = now() WHERE id = :id"
        ),
        {"status": STATUS_REJECTED, "reason": reason[:2000], "id": job_id},
    )
    db.commit()


def fail(db: Session, job_id: uuid.UUID, error: str) -> str:
    """Record a failed attempt: back to the queue with a delay, or FAILED for good.

    Returns the status the job ended in.
    """
    row = db.execute(
        text("SELECT attempts, max_attempts FROM background_jobs WHERE id = :id FOR UPDATE"),
        {"id": job_id},
    ).first()
    if row is None:
        db.rollback()
        return STATUS_FAILED
    status = _requeue_or_fail(db, job_id, row.attempts, row.max_attempts, error)
    db.commit()
    return status


def reap(db: Session, *, queue: str | None = None, stale_after: int | None = None) -> int:
    """Hand back running jobs whose worker stopped heartbeating. Returns how many."""
    queue = queue or settings.JOB_QUEUE
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after or settings.JOB_STALE_SECONDS)
    rows = db.execute(
        text(
            "SELECT id, attempts, max_attempts, locked_by FROM background_jobs "
            "WHERE queue = :queue AND status = 'RUNNING' AND heartbeat_at < :cutoff "
            "FOR UPDATE SKIP LOCKED"
        ),
        {"queue": queue, "cutoff": cutoff},
    ).all()
    for row in rows:
        _requeue_or_fail(
            db, row.id, row.attempts, row.max_attempts,
            f"The worker holding this job ({row.locked_by}) stopped responding.",
        )
    db.commit()
    return len(rows)


def _requeue_or_fail(db: Session, job_id, attempts: int, max_attempts: int, error: str) -> str:
    if attempts < max_attempts:
        delay = RETRY_BASE_SECONDS * (2 ** max(0, attempts - 1))
        db.execute(
            text(
                "UPDATE background_jobs SET status = 'QUEUED', locked_by = NULL, last_error = :error, "
                "run_after = now() + make_interval(secs => :delay), updated_at = now() WHERE id = :id"
            ),
            {"error": error[:2000], "delay": delay, "id": job_id},
        )
        return STATUS_QUEUED
    db.execute(
        text(
            "UPDATE background_jobs SET status = :status, locked_by = NULL, last_error = :error, "
            "finished_at = now(), updated_at = now() WHERE id = :id"
        ),
        {"status": STATUS_FAILED, "error": error[:2000], "id": job_id},
    )
    return STATUS_FAILED


def _jsonable(payload: dict) -> dict:
    """UUIDs as strings: the payload is JSON, and handlers parse what they need."""
    return {key: str(value) if isinstance(value, uuid.UUID) else value for key, value in payload.items()}


__all__ = [
    "ACTIVE_DEDUPE_INDEX", "CLAIM_LOCK_KEY", "ClaimedJob", "STATUS_RUNNING",
    "claim", "enqueue", "fail", "heartbeat", "reap", "reject", "succeed", "worker_identity",
]
