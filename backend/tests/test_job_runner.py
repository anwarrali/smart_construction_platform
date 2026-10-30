"""The durable job queue and its runner.

Pins what replaced the in-process pool, including the guarantees the pool's own
tests pinned — the ceiling holds, a failing job does not hold its slot,
enqueuing never waits — and what the pool could not do: survive a restart, take
work back from a dead worker, and hold the ceiling across processes.

Every test works in a queue of its own, so nothing here can take, or be taken
by, another test's jobs or the development stack's worker.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.background_job import BackgroundJob
from app.services.jobs import handlers
from app.services.jobs import queue as job_queue
from app.services.jobs.handlers import JobKind
from app.services.jobs.runner import JobRunner, execute, run_pending


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
def queue(db, monkeypatch):
    """A queue nobody else uses, emptied afterwards."""
    name = f"test-runner-{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(settings, "JOB_QUEUE", name)
    yield name
    db.rollback()
    db.execute(text("DELETE FROM background_jobs WHERE queue = :queue"), {"queue": name})
    db.commit()


@pytest.fixture()
def kind(monkeypatch):
    """Register a job kind for the test; returns a registration helper."""
    def register(name, run):
        monkeypatch.setitem(handlers.KINDS, name, JobKind(name, run))
        return name
    return register


def _job(db, job_id) -> BackgroundJob:
    db.expire_all()
    return db.get(BackgroundJob, job_id)


def _claim(queue, capacity=10):
    session = SessionLocal()
    try:
        return job_queue.claim(session, worker="test", capacity=capacity, queue=queue)
    finally:
        session.close()


# --- enqueueing ------------------------------------------------------------------

def test_a_job_exists_only_if_its_transaction_commits(db, queue):
    job_id = job_queue.enqueue(db, "test.noop", {"n": 1})
    db.rollback()
    assert _job(db, job_id) is None, "a rolled-back upload must not leave work behind"

    job_id = job_queue.enqueue(db, "test.noop", {"n": 2})
    db.commit()
    job = _job(db, job_id)
    assert job.status == "QUEUED" and job.queue == queue and job.payload == {"n": 2}


def test_a_dedupe_key_joins_live_work_instead_of_queuing_it_twice(db, queue):
    first = job_queue.enqueue(db, "test.noop", dedupe_key="model:1")
    db.commit()
    second = job_queue.enqueue(db, "test.noop", dedupe_key="model:1")
    db.commit()
    assert second == first
    assert db.query(BackgroundJob).filter(BackgroundJob.queue == queue).count() == 1


def test_finished_work_can_be_queued_again(db, queue, kind):
    kind("test.noop", lambda payload, attempt: None)
    first = job_queue.enqueue(db, "test.noop", dedupe_key="model:2")
    db.commit()
    run_pending(queue=queue)
    again = job_queue.enqueue(db, "test.noop", dedupe_key="model:2")
    db.commit()
    assert again != first


def test_uuids_in_a_payload_are_stored_as_text(db, queue):
    value = uuid.uuid4()
    job_id = job_queue.enqueue(db, "test.noop", {"version_id": value})
    db.commit()
    assert _job(db, job_id).payload == {"version_id": str(value)}


def test_enqueuing_never_waits_for_a_free_slot(db, queue):
    """The pool's guarantee, kept: the request returns; the queue holds the wait."""
    for _ in range(2):
        job_queue.enqueue(db, "test.noop")
    db.commit()
    db.execute(text("UPDATE background_jobs SET status = 'RUNNING', heartbeat_at = now() WHERE queue = :q"),
               {"q": queue})
    db.commit()
    began = time.monotonic()
    job_queue.enqueue(db, "test.noop")
    db.commit()
    assert time.monotonic() - began < 1.0


# --- claiming --------------------------------------------------------------------

def test_claim_takes_the_oldest_due_job_and_marks_it_running(db, queue):
    later = job_queue.enqueue(db, "test.noop", {"order": 2})
    db.commit()
    db.execute(text("UPDATE background_jobs SET run_after = now() + interval '1 hour' WHERE id = :id"),
               {"id": later})
    first = job_queue.enqueue(db, "test.noop", {"order": 1})
    db.commit()

    claimed = _claim(queue)
    assert claimed.id == first and claimed.attempt == 1
    job = _job(db, first)
    assert job.status == "RUNNING" and job.locked_by == "test" and job.heartbeat_at is not None
    assert _claim(queue) is None, "a job not yet due is not claimed"


def test_the_ceiling_is_counted_across_every_process(db, queue):
    """Two jobs RUNNING anywhere — any process, any host — fill a ceiling of two."""
    for _ in range(3):
        job_queue.enqueue(db, "test.noop")
    db.commit()
    assert _claim(queue, capacity=2) is not None
    assert _claim(queue, capacity=2) is not None
    assert _claim(queue, capacity=2) is None


def test_one_queue_does_not_take_another_queues_work(db, queue):
    job_queue.enqueue(db, "test.noop", queue=f"{queue}-other")
    db.commit()
    try:
        assert _claim(queue) is None
    finally:
        db.execute(text("DELETE FROM background_jobs WHERE queue = :q"), {"q": f"{queue}-other"})
        db.commit()


# --- running -----------------------------------------------------------------------

def test_a_job_runs_with_its_payload_and_attempt_and_is_marked_done(db, queue, kind):
    seen = []
    kind("test.record", lambda payload, attempt: seen.append((payload, attempt)))
    job_id = job_queue.enqueue(db, "test.record", {"x": "y"})
    db.commit()
    assert run_pending(queue=queue) == [("test.record", "SUCCEEDED")]
    assert seen == [({"x": "y"}, 1)]
    job = _job(db, job_id)
    assert job.status == "SUCCEEDED" and job.finished_at is not None and job.locked_by is None


def test_a_failure_is_retried_later_then_given_up(db, queue, kind):
    def boom(payload, attempt):
        raise RuntimeError(f"parser exploded on attempt {attempt}")
    kind("test.boom", boom)
    job_id = job_queue.enqueue(db, "test.boom", max_attempts=2)
    db.commit()

    assert run_pending(queue=queue) == [("test.boom", "QUEUED")]
    job = _job(db, job_id)
    assert job.status == "QUEUED" and job.attempts == 1
    assert "attempt 1" in job.last_error
    assert job.run_after > datetime.now(timezone.utc), "a retry waits"

    db.execute(text("UPDATE background_jobs SET run_after = now() WHERE id = :id"), {"id": job_id})
    db.commit()
    assert run_pending(queue=queue) == [("test.boom", "FAILED")]
    job = _job(db, job_id)
    assert job.status == "FAILED" and job.attempts == 2 and job.finished_at is not None


def test_a_failing_job_does_not_hold_its_slot(db, queue, kind):
    """The pool's guarantee, kept: with a ceiling of one, the next job still runs."""
    ran = []
    kind("test.boom", lambda payload, attempt: (_ for _ in ()).throw(RuntimeError("no")))
    kind("test.after", lambda payload, attempt: ran.append(True))
    job_queue.enqueue(db, "test.boom", max_attempts=1)
    job_queue.enqueue(db, "test.after")
    db.commit()
    first = _claim(queue, capacity=1)
    assert execute(first) == "FAILED"
    second = _claim(queue, capacity=1)
    assert second is not None, "the failed job left the only slot occupied"
    execute(second)
    assert ran == [True]


def test_an_unknown_kind_is_rejected_not_retried(db, queue):
    job_id = job_queue.enqueue(db, "test.never_registered")
    db.commit()
    assert run_pending(queue=queue) == [("test.never_registered", "REJECTED")]
    assert "Unknown job kind" in _job(db, job_id).last_error


def test_the_runner_never_runs_more_than_the_ceiling(db, queue, kind, monkeypatch):
    """The pool's headline guarantee, now held by the database across threads."""
    monkeypatch.setattr(settings, "IFC_MAX_CONCURRENT_PROCESSING", 2)
    gate = threading.Event()
    lock = threading.Lock()
    state = {"running": 0, "peak": 0, "done": 0}

    def held(payload, attempt):
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        gate.wait(timeout=20)
        with lock:
            state["running"] -= 1
            state["done"] += 1

    kind("test.held", held)
    for _ in range(6):
        job_queue.enqueue(db, "test.held")
    db.commit()

    # Four threads competing for a ceiling of two: the database must refuse two of them.
    runner = JobRunner(queue=queue, concurrency=4, poll_seconds=0.05)
    runner.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and state["peak"] < 2:
            time.sleep(0.02)
        time.sleep(0.5)
        assert state["peak"] == 2, f"{state['peak']} jobs ran at once against a ceiling of 2"
        gate.set()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and state["done"] < 6:
            time.sleep(0.05)
        assert state["done"] == 6, "every queued job must still run"
    finally:
        gate.set()
        runner.stop(timeout=10)


# --- surviving a dead worker -----------------------------------------------------------

def test_work_abandoned_by_a_dead_worker_is_handed_back(db, queue):
    job_id = job_queue.enqueue(db, "test.noop")
    db.commit()
    _claim(queue)
    db.execute(text("UPDATE background_jobs SET heartbeat_at = now() - interval '1 hour' WHERE id = :id"),
               {"id": job_id})
    db.commit()

    assert job_queue.reap(db, queue=queue, stale_after=60) == 1
    job = _job(db, job_id)
    assert job.status == "QUEUED" and job.locked_by is None
    assert "stopped responding" in job.last_error


def test_a_live_heartbeat_keeps_a_job(db, queue):
    job_id = job_queue.enqueue(db, "test.noop")
    db.commit()
    _claim(queue)
    job_queue.heartbeat(db, [job_id])
    assert job_queue.reap(db, queue=queue, stale_after=60) == 0
    assert _job(db, job_id).status == "RUNNING"


def test_a_job_that_keeps_killing_its_worker_is_eventually_given_up(db, queue):
    job_id = job_queue.enqueue(db, "test.noop", max_attempts=1)
    db.commit()
    _claim(queue)
    db.execute(text("UPDATE background_jobs SET heartbeat_at = now() - interval '1 hour' WHERE id = :id"),
               {"id": job_id})
    db.commit()
    job_queue.reap(db, queue=queue, stale_after=60)
    assert _job(db, job_id).status == "FAILED"


# --- the handlers -----------------------------------------------------------------------

def test_every_producer_kind_has_a_handler():
    assert set(handlers.KINDS) >= {
        "ifc.process_version", "ifc.generate_geometry", "ingestion.process_file",
        "rag.index_file", "rag.project_reindex", "agents.handle_event",
    }


def test_a_retried_ifc_parse_first_recovers_the_version_it_stranded(monkeypatch):
    """A worker that died mid-parse left the version PARSING; the domain code
    refuses to restart work that looks in progress, so the retry resets it."""
    recovered, processed = [], []
    monkeypatch.setattr(handlers, "_recover_ifc_processing", lambda db, version_id: recovered.append(version_id))
    monkeypatch.setattr(
        "app.services.ifc_processing_service.process_version",
        lambda db, version_id, actor_id=None: processed.append(version_id),
    )
    version_id = uuid.uuid4()
    handlers.run_ifc_processing({"version_id": str(version_id), "actor_id": None}, attempt=1)
    assert recovered == [] and processed == [version_id]
    handlers.run_ifc_processing({"version_id": str(version_id), "actor_id": None}, attempt=2)
    assert recovered == [version_id] and processed == [version_id, version_id]


def test_a_retried_index_forces_past_the_row_its_dead_attempt_left(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.rag.ingestion.index_ingested_file_job",
                        lambda file_id, force=False: calls.append(force))
    handlers.run_rag_file_index({"file_id": str(uuid.uuid4()), "force": False}, attempt=1)
    handlers.run_rag_file_index({"file_id": str(uuid.uuid4()), "force": False}, attempt=2)
    assert calls == [False, True]


def test_an_ifc_job_closes_its_session_even_when_processing_fails(monkeypatch):
    """Carried over from the pool's tests: a failed job must not leak its session."""
    closed = []

    class _Session:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(handlers, "SessionLocal", lambda: _Session())

    def boom(db, version_id, actor_id=None):
        raise RuntimeError("processing exploded")

    monkeypatch.setattr("app.services.ifc_processing_service.process_version", boom)
    with pytest.raises(RuntimeError):
        handlers.run_ifc_processing({"version_id": str(uuid.uuid4())}, attempt=1)
    assert closed == [True]


# --- the producers -------------------------------------------------------------------------

def test_the_ifc_routes_queue_work_rather_than_running_it(db, queue):
    from app.api import ifc as ifc_api

    version_id, actor_id = uuid.uuid4(), uuid.uuid4()
    ifc_api._background_process(db, version_id, actor_id, None)
    ifc_api._background_geometry(db, version_id, None)
    db.commit()
    jobs = {job.kind: job for job in db.query(BackgroundJob).filter(BackgroundJob.queue == queue)}
    assert jobs["ifc.process_version"].payload == {"version_id": str(version_id), "actor_id": str(actor_id)}
    assert jobs["ifc.process_version"].dedupe_key == f"ifc.process:{version_id}"
    assert jobs["ifc.generate_geometry"].dedupe_key == f"ifc.geometry:{version_id}"


def test_the_worker_waits_for_the_schema_its_code_expects():
    from app.worker import wait_for_schema

    assert wait_for_schema(threading.Event(), poll_seconds=0.01) is True


def test_a_stop_request_ends_the_wait():
    from app.worker import wait_for_schema

    stop = threading.Event()
    stop.set()
    assert wait_for_schema(stop) is False
