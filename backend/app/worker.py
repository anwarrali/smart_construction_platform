"""The dedicated background worker: `python -m app.worker`.

Runs the job runner in its own process, so IFC parsing, file ingestion, RAG
indexing and agent analysis stop competing with request serving. The API
container runs migrations; this process only waits until the database is at
the head revision its code expects, then starts claiming — a worker that
started first would otherwise run new code against an old schema.

SIGTERM (what `docker stop` sends) stops claiming and gives running jobs the
grace period to finish; anything still running after that is handed back by
the reaper once its heartbeat goes stale.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.models  # noqa: F401 - configure all SQLAlchemy relationships
from app.core.config import settings
from app.db.database import SessionLocal
from app.services.jobs.runner import JobRunner

logger = logging.getLogger("worker")

#: How long to wait for running jobs on shutdown. Docker's default stop grace
#: is 10s; compose gives the worker longer (`stop_grace_period`).
SHUTDOWN_GRACE_SECONDS = 50


def _expected_head() -> str:
    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {len(heads)}")
    return heads[0]


def wait_for_schema(stop: threading.Event, poll_seconds: float = 5) -> bool:
    """Block until the database is at head. False if asked to stop first."""
    expected = _expected_head()
    while not stop.is_set():
        db = SessionLocal()
        try:
            current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception as exc:  # table missing before the first migration
            current = f"unavailable ({type(exc).__name__})"
        finally:
            db.close()
        if current == expected:
            return True
        logger.info("waiting for migrations: database at %s, worker expects %s", current, expected)
        stop.wait(poll_seconds)
    return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()

    def request_stop(signum, _frame):
        logger.info("received %s; finishing running jobs", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    if not wait_for_schema(stop):
        return 0
    runner = JobRunner()
    runner.start()
    logger.info("worker ready (queue=%s)", settings.JOB_QUEUE)
    while not stop.wait(1):
        pass
    runner.stop(SHUTDOWN_GRACE_SECONDS)
    logger.info("worker stopped after %s job(s)", runner.completed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
