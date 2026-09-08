"""The one bounded pool every heavy file job runs on.

This code was written for IFC and lived in `app/api/ifc.py`. It is moved here
unchanged, and `app.api.ifc` imports it back under the same names, because the
unified ingestion pipeline needs exactly the same ceiling for exactly the same
reason — and a *second* pool would silently double the memory bound the first
one exists to enforce.

The original reasoning, which still holds and now covers both subsystems:

Both kinds of job spawn isolated child processes — the IFC parser worker, the
tessellator and its own `IFC_GEOMETRY_WORKERS`, and the archive and document
readers — against files that may be half a gigabyte. Nothing bounded how many
of those could exist at once: `BackgroundTasks` starts a task per request, so N
simultaneous uploads meant N parsers plus N × `IFC_GEOMETRY_WORKERS`
tessellators, which is a straightforward way for one authenticated uploader to
exhaust the host's memory.

The wait deliberately happens *here* and not on Starlette's threadpool. A sync
`BackgroundTasks` callable runs on the same threadpool every other synchronous
endpoint shares, so blocking there to wait for a free slot would turn a burst
of uploads into a stall on unrelated requests. Submitting and returning keeps
that thread free: the queue forms on this pool instead, and at most
`IFC_MAX_CONCURRENT_PROCESSING` jobs ever run together.

The setting keeps its IFC name. Renaming it would be a breaking configuration
change for every existing deployment, to express something the docstring says
better anyway: it is a memory ceiling for file processing as a whole.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings

logger = logging.getLogger(__name__)

_processing_pool: ThreadPoolExecutor | None = None
_processing_pool_lock = threading.Lock()


def processing_pool() -> ThreadPoolExecutor:
    """The bounded pool, created on first use so it reads current settings."""
    global _processing_pool
    with _processing_pool_lock:
        if _processing_pool is None:
            _processing_pool = ThreadPoolExecutor(
                max_workers=settings.IFC_MAX_CONCURRENT_PROCESSING,
                thread_name_prefix="file-processing",
            )
        return _processing_pool


def reset_processing_pool() -> None:
    """Discard the pool so the next job builds one from the current settings.

    Exists for the tests that vary `IFC_MAX_CONCURRENT_PROCESSING`, and for a
    reconfiguration that wants the new limit without a restart. Shutting down
    without waiting is safe: jobs already running finish on their own threads,
    and each records its own outcome on the row it owns.
    """
    global _processing_pool
    with _processing_pool_lock:
        pool, _processing_pool = _processing_pool, None
    if pool is not None:
        pool.shutdown(wait=False)


def submit(job, *args, **kwargs) -> None:
    """Queue one job, and make sure a failure in it cannot escape unseen.

    A raised exception inside a pool worker lands in a `Future` nobody reads,
    which is silence — so it is logged here. The job itself is still
    responsible for recording the failure against its row, which
    `process_version`, `generate_geometry`, `ingestion.pipeline.run` and
    `rag.ingestion.index_ingested_file_job` all do.

    Keyword arguments are forwarded rather than requiring a `functools.partial`
    at the call site: a partial has no `__name__`, so the log line above would
    degrade to a repr exactly when something has gone wrong.
    """

    def run() -> None:
        try:
            job(*args, **kwargs)
        except Exception:  # pragma: no cover - the jobs record their own failures
            logger.exception("Background file job %s failed", getattr(job, "__name__", job))

    processing_pool().submit(run)
