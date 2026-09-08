"""Background scheduler for recurring platform jobs.

Deliberately built on asyncio and a PostgreSQL advisory lock rather than a new
broker or scheduler dependency: the API already runs with several uvicorn
workers, and the advisory lock is what stops every worker from dispatching the
same reminder. If the lock is held elsewhere the tick is skipped, not queued.

Two sweeps run on the one loop:

  * **reminders** — `services/reminder_service.py`, every
    `REMINDER_SCHEDULER_INTERVAL_SECONDS`;
  * **the RAG reaper** — `services/rag/maintenance.py`, every
    `RAG_REAPER_INTERVAL_MINUTES`, taking back rows left in INDEXING by a
    worker that died.

One loop rather than two, because a second asyncio task and a second sleep
schedule is a second thing to reason about for work that is measured in
milliseconds. They hold **different** advisory locks, so a slow reminder
sweep on one worker cannot stop the reaper running on another.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.services.reminder_service import evaluate_all_projects

# Uvicorn configures this logger, so scheduler activity is visible in container
# logs without the app installing its own logging configuration.
logger = logging.getLogger("uvicorn.error").getChild("scheduler")

# Arbitrary but stable keys so every worker competes for the same lock.
# Separate keys on purpose: a slow reminder sweep must not delay the reaper.
REMINDER_LOCK_KEY = 776_120_431
RAG_REAPER_LOCK_KEY = 776_120_432

_task: asyncio.Task | None = None
_last_run: dict = {"startedAt": None, "finishedAt": None, "result": None, "skipped": 0}
_last_reaper_run: dict = {"startedAt": None, "finishedAt": None, "result": None, "skipped": 0}


def run_reminder_tick() -> dict:
    """One reminder sweep. Returns a result dict, or a skip marker if another worker holds the lock.

    The lock lives on its own connection: a PostgreSQL session advisory lock is
    bound to the backend connection, and the ORM session commits once per
    project, which would hand its connection back to the pool mid-sweep.
    """
    lock_connection = engine.connect()
    try:
        acquired = lock_connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": REMINDER_LOCK_KEY},
        ).scalar()
        if not acquired:
            return {"skipped": True, "reason": "another worker holds the reminder lock"}
        db = SessionLocal()
        try:
            return evaluate_all_projects(db)
        finally:
            db.close()
    finally:
        try:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": REMINDER_LOCK_KEY})
            lock_connection.commit()
        finally:
            lock_connection.close()


def run_rag_reaper_tick() -> dict:
    """One stale-index sweep, guarded by its own advisory lock.

    Same shape as the reminder tick and for the same reason: several uvicorn
    workers each run this loop, and exactly one should do the work. The lock
    lives on its own connection because the ORM session commits inside the
    sweep, which would hand its connection back to the pool mid-run.

    Deferred import: `rag.maintenance` pulls in the models and the processing
    pool, and the scheduler module is imported at application start whether or
    not RAG is enabled.
    """
    from app.services.rag.maintenance import recover_stale_jobs

    lock_connection = engine.connect()
    try:
        acquired = lock_connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": RAG_REAPER_LOCK_KEY},
        ).scalar()
        if not acquired:
            return {"skipped": True, "reason": "another worker holds the reaper lock"}
        db = SessionLocal()
        try:
            report = recover_stale_jobs(db)
            return {
                "documents": report.documents,
                "files": report.files,
                "jobs": report.jobs,
                "total": report.total,
            }
        finally:
            db.close()
    finally:
        try:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": RAG_REAPER_LOCK_KEY},
            )
            lock_connection.commit()
        finally:
            lock_connection.close()


async def _loop() -> None:
    interval = max(60, settings.REMINDER_SCHEDULER_INTERVAL_SECONDS)
    reaper_interval = max(60, settings.RAG_REAPER_INTERVAL_MINUTES * 60)
    # Tracked in seconds since the last reaper sweep rather than as its own
    # sleep schedule: one loop, two cadences.
    since_reaper = 0.0
    # Stagger the first sweep so a rolling restart does not have every worker
    # wake at the same instant.
    await asyncio.sleep(min(30, interval))
    while True:
        started = datetime.now(timezone.utc)
        try:
            result = await asyncio.to_thread(run_reminder_tick)
            if result.get("skipped"):
                _last_run["skipped"] += 1
            else:
                _last_run.update({"startedAt": started, "finishedAt": datetime.now(timezone.utc), "result": result})
                if result.get("created"):
                    logger.info("reminder sweep created %s reminder(s) across %s project(s)",
                                result["created"], result["projects"])
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed sweep must never kill the loop; the next tick retries.
            logger.exception("reminder sweep failed")

        since_reaper += interval
        if settings.RAG_REAPER_ENABLED and since_reaper >= reaper_interval:
            since_reaper = 0.0
            reaper_started = datetime.now(timezone.utc)
            try:
                result = await asyncio.to_thread(run_rag_reaper_tick)
                if result.get("skipped"):
                    _last_reaper_run["skipped"] += 1
                else:
                    _last_reaper_run.update({
                        "startedAt": reaper_started,
                        "finishedAt": datetime.now(timezone.utc),
                        "result": result,
                    })
                    if result.get("total"):
                        logger.info(
                            "RAG reaper recovered %s stranded indexing run(s)",
                            result["total"],
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                # Same rule as above: a failed sweep must not kill the loop.
                logger.exception("RAG stale-index sweep failed")

        await asyncio.sleep(interval)


def start() -> None:
    global _task
    if not settings.REMINDER_SCHEDULER_ENABLED:
        logger.info("reminder scheduler disabled by configuration")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop(), name="reminder-scheduler")
    logger.info("reminder scheduler started (every %ss)", settings.REMINDER_SCHEDULER_INTERVAL_SECONDS)


async def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None


def status() -> dict:
    return {
        "enabled": settings.REMINDER_SCHEDULER_ENABLED,
        "intervalSeconds": settings.REMINDER_SCHEDULER_INTERVAL_SECONDS,
        "running": bool(_task and not _task.done()),
        "lastRun": _last_run,
        "ragReaper": {
            "enabled": settings.RAG_REAPER_ENABLED,
            "intervalMinutes": settings.RAG_REAPER_INTERVAL_MINUTES,
            "staleAfterMinutes": settings.RAG_INDEX_STALE_MINUTES,
            "lastRun": _last_reaper_run,
        },
    }
