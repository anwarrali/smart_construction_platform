"""Fence every worker transaction, including sessions opened by nested services.

The existing attempts counter is a monotonic lease generation. Locking the job
row in the *publication transaction* serializes it with the reaper/next claim.
A check in a separate session would leave a check/commit race. Manual request
sessions have no worker context and are unaffected.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core.config import settings

current_job = ContextVar("current_background_job", default=None)


class LeaseLost(RuntimeError):
    pass


def assert_owned(db, job, *, lock=True):
    if not getattr(job, "worker", None):
        raise LeaseLost("A claimed lease is required")
    row = db.execute(text(
        "SELECT id FROM background_jobs WHERE id=:id AND status='RUNNING' "
        "AND attempts=:attempt AND locked_by=:worker "
        "AND heartbeat_at > clock_timestamp() - make_interval(secs => :stale) "
        "AND started_at > clock_timestamp() - make_interval(secs => :maximum) "
        + ("FOR UPDATE" if lock else "")
    ), {"id": job.id, "attempt": job.attempt, "worker": job.worker,
        "stale": settings.JOB_STALE_SECONDS, "maximum": settings.JOB_MAX_EXECUTION_SECONDS}).first()
    if row is None:
        raise LeaseLost("Worker lease expired or ownership transferred")


@contextmanager
def execution_lease(job):
    token = current_job.set(job)
    try:
        yield
    finally:
        current_job.reset(token)


@event.listens_for(Session, "before_flush")
def _before_flush(db, *_):
    job = current_job.get()
    if job is not None:
        assert_owned(db, job)


@event.listens_for(Session, "before_commit")
def _before_commit(db):
    job = current_job.get()
    if job is not None:
        assert_owned(db, job)
