"""The process that takes jobs off the queue and runs them.

`JobRunner` is a set of threads, each claiming one job at a time, plus one
maintenance thread that keeps this process's running jobs heartbeating and
hands back jobs other processes abandoned. It runs either inside the API
process (`JOB_RUNNER_EMBEDDED`, the single-container default) or as its own
process (`python -m app.worker`), and the two can coexist: the queue, not the
process, enforces the concurrency ceiling.

Threads rather than asyncio, because every job is blocking work — a parse in a
child process, an embedding call, a database walk — and the domain functions
are synchronous.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.db.database import SessionLocal
from app.services.jobs import queue as job_queue
from app.services.jobs.handlers import KINDS

logger = logging.getLogger("uvicorn.error").getChild("jobs")


def execute(job: job_queue.ClaimedJob) -> str:
    """Run one claimed job and record its outcome. Returns the final status."""
    kind = KINDS.get(job.kind)
    if kind is None:
        _record(job_queue.reject, job.id, f"Unknown job kind {job.kind!r} on this deployment.")
        logger.error("[Jobs] rejected %s: unknown kind %r", job.id, job.kind)
        return job_queue.STATUS_REJECTED
    started = time.perf_counter()
    try:
        kind.run(job.payload, job.attempt)
    except Exception as exc:
        logger.exception("[Jobs] %s %s failed on attempt %s", job.kind, job.id, job.attempt)
        status = _record(job_queue.fail, job.id, f"{type(exc).__name__}: {exc}")
        return status or job_queue.STATUS_FAILED
    _record(job_queue.succeed, job.id)
    logger.info("[Jobs] %s %s finished in %.1fs", job.kind, job.id, time.perf_counter() - started)
    return job_queue.STATUS_SUCCEEDED


def _record(operation, *args):
    db = SessionLocal()
    try:
        return operation(db, *args)
    finally:
        db.close()


def run_pending(*, queue: str | None = None, limit: int = 100) -> list[tuple[str, str]]:
    """Run due jobs in the calling thread until none are left. Returns (kind, status) pairs.

    The same claim and execute path the runner uses, without threads — for the
    test suite and for an operator draining a queue by hand. The ceiling is not
    applied: whoever calls this has chosen to do the work now.
    """
    results = []
    for _ in range(limit):
        db = SessionLocal()
        try:
            job = job_queue.claim(db, worker=job_queue.worker_identity(), capacity=10**9, queue=queue)
        finally:
            db.close()
        if job is None:
            break
        results.append((job.kind, execute(job)))
    return results


class JobRunner:
    def __init__(self, *, queue: str | None = None, concurrency: int | None = None,
                 poll_seconds: float | None = None) -> None:
        self.queue = queue or settings.JOB_QUEUE
        self.concurrency = concurrency or settings.IFC_MAX_CONCURRENT_PROCESSING
        self.poll_seconds = poll_seconds if poll_seconds is not None else settings.JOB_POLL_INTERVAL_SECONDS
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._running: dict[uuid.UUID, str] = {}
        self._lock = threading.Lock()
        self.completed = 0
        self.started_at: datetime | None = None

    # --- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        self.started_at = datetime.now(timezone.utc)
        for index in range(self.concurrency):
            self._spawn(self._work, f"job-worker-{index}")
        self._spawn(self._maintain, "job-maintenance")
        logger.info("job runner started (queue=%s, threads=%s, fleet ceiling=%s)",
                    self.queue, self.concurrency, settings.IFC_MAX_CONCURRENT_PROCESSING)

    def stop(self, timeout: float = 30) -> None:
        """Stop claiming, and wait up to `timeout` for running jobs to finish.

        A job still running at the deadline is left RUNNING; its heartbeat
        stops with this process, and the reaper on a surviving runner hands it
        back once it goes stale.
        """
        self._stop.set()
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        unfinished = [thread.name for thread in self._threads if thread.is_alive()]
        if unfinished:
            logger.warning("job runner stopped with jobs still running: %s", self.running())
        self._threads = []

    def _spawn(self, target, name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        self._threads.append(thread)

    def running(self) -> dict[str, str]:
        with self._lock:
            return {str(job_id): kind for job_id, kind in self._running.items()}

    # --- threads ----------------------------------------------------------------

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._claim()
            except Exception:
                logger.exception("[Jobs] claiming failed; retrying")
                self._stop.wait(self.poll_seconds)
                continue
            if job is None:
                self._stop.wait(self.poll_seconds)
                continue
            with self._lock:
                self._running[job.id] = job.kind
            try:
                execute(job)
                self.completed += 1
            finally:
                with self._lock:
                    self._running.pop(job.id, None)

    def _claim(self) -> job_queue.ClaimedJob | None:
        db = SessionLocal()
        try:
            return job_queue.claim(
                db, worker=job_queue.worker_identity(),
                capacity=settings.IFC_MAX_CONCURRENT_PROCESSING, queue=self.queue,
            )
        finally:
            db.close()

    def _maintain(self) -> None:
        reap_every = max(settings.JOB_HEARTBEAT_SECONDS, settings.JOB_STALE_SECONDS // 2)
        since_reap = reap_every  # reap once at start: a restart is when strays exist
        while not self._stop.wait(0 if since_reap >= reap_every else settings.JOB_HEARTBEAT_SECONDS):
            db = SessionLocal()
            try:
                with self._lock:
                    held = list(self._running)
                job_queue.heartbeat(db, held)
                if since_reap >= reap_every:
                    since_reap = 0
                    returned = job_queue.reap(db, queue=self.queue)
                    if returned:
                        logger.warning("[Jobs] handed back %s job(s) from a worker that stopped", returned)
                else:
                    since_reap += settings.JOB_HEARTBEAT_SECONDS
            except Exception:
                logger.exception("[Jobs] heartbeat/reap failed; retrying")
            finally:
                db.close()

    def status(self) -> dict:
        return {
            "queue": self.queue,
            "threads": self.concurrency,
            "running": self.running(),
            "completed": self.completed,
            "startedAt": self.started_at,
        }


_embedded: JobRunner | None = None


def start_embedded() -> JobRunner | None:
    """The API process's runner, when this deployment has no separate worker."""
    global _embedded
    if not settings.JOB_RUNNER_EMBEDDED:
        logger.info("embedded job runner disabled; jobs run on a dedicated worker")
        return None
    if _embedded is None:
        _embedded = JobRunner()
        _embedded.start()
    return _embedded


def stop_embedded(timeout: float = 10) -> None:
    global _embedded
    if _embedded is not None:
        _embedded.stop(timeout)
        _embedded = None
