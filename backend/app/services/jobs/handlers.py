"""Every kind of background job, and what running one means.

A handler takes the job's payload and its attempt number. The domain functions
it calls already open their own sessions and record their own outcome on the
row they own — a failed parse marks the IFC version FAILED, it does not raise —
so a handler returning normally means "the work ran", not "the work succeeded".
The domain row stays the authority on that.

## Retries after a crash

A worker that dies mid-job leaves its domain row wherever it was: an IFC
version reading PARSING, a file reading INDEXING. The reaper requeues the job,
but the domain functions refuse to restart work that looks in progress — which
is what stops two workers running it at once. So a handler on attempt 2+ first
**recovers** that stranded state: it records why the earlier attempt stopped,
then lets the domain function start over.

Imports are deferred into each handler: the worker process imports this module
at start, and the IFC, RAG and agent stacks are heavy and import each other.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Callable

from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

INTERRUPTED = "Processing was interrupted (the worker stopped) and has been restarted."

#: IFC states that mean "a worker was in the middle of this".
_IFC_IN_PROGRESS = frozenset({
    "QUEUED", "PARSING", "BUILDING_HIERARCHY", "EXTRACTING_ELEMENTS",
    "EXTRACTING_PROPERTIES", "QUALITY_CHECKS", "ANALYZING",
})


@dataclass(frozen=True)
class JobKind:
    name: str
    run: Callable[[dict, int], None]


def _uuid(payload: dict, key: str) -> uuid.UUID:
    return uuid.UUID(str(payload[key]))


# --- IFC ------------------------------------------------------------------------

def run_ifc_processing(payload: dict, attempt: int) -> None:
    from app.services.ifc_processing_service import process_version

    version_id = _uuid(payload, "version_id")
    actor_id = uuid.UUID(payload["actor_id"]) if payload.get("actor_id") else None
    db = SessionLocal()
    try:
        if attempt > 1:
            _recover_ifc_processing(db, version_id)
        process_version(db, version_id, actor_id)
    finally:
        db.close()


def _recover_ifc_processing(db, version_id: uuid.UUID) -> None:
    from app.models.ifc import IFCModelVersion, IFCProcessingJob
    from app.services.ifc_processing_service import transition_version

    version = db.get(IFCModelVersion, version_id)
    if version is None or version.processing_status not in _IFC_IN_PROGRESS:
        return
    transition_version(version, "FAILED", version.processing_progress or 0)
    for job in db.query(IFCProcessingJob).filter(
        IFCProcessingJob.version_id == version_id, IFCProcessingJob.status.in_(["QUEUED", "RUNNING"]),
    ):
        job.status = "FAILED"
        job.failure_code = "INTERRUPTED"
        job.failure_message = INTERRUPTED
    db.commit()
    logger.warning("[Jobs] recovered IFC version %s stranded mid-processing", version_id)


def run_ifc_geometry(payload: dict, attempt: int) -> None:
    from app.services.ifc_geometry_service import generate_geometry
    from app.services.ifc_processing_service import run_interference_analysis

    version_id = _uuid(payload, "version_id")
    db = SessionLocal()
    try:
        # Restartable as it stands: it sets GEOMETRY_PROCESSING itself and
        # rewrites the geometry from scratch.
        generate_geometry(db, version_id)
        # Fresh element extents mean the interference findings derived from
        # them are rebuilt to match; reviewed pairs keep their decision.
        run_interference_analysis(db, version_id)
    finally:
        db.close()


# --- Ingestion and RAG ------------------------------------------------------------

def run_ingestion(payload: dict, attempt: int) -> None:
    from app.services.ingestion.pipeline import process_file

    process_file(_uuid(payload, "file_id"))


def run_rag_file_index(payload: dict, attempt: int) -> None:
    from app.services.rag.ingestion import index_ingested_file_job

    # A retry finds the row still INDEXING from the attempt that died, which
    # is exactly the state `force` exists to take back.
    index_ingested_file_job(_uuid(payload, "file_id"), force=bool(payload.get("force")) or attempt > 1)


def run_rag_project_reindex(payload: dict, attempt: int) -> None:
    from app.services.rag.maintenance import run_project_reindex

    run_project_reindex(_uuid(payload, "job_id"))


# --- Agents -------------------------------------------------------------------------

def run_agent_event(payload: dict, attempt: int) -> None:
    """Automatic analysis of one domain event, in a transaction of its own.

    It used to run inside the transaction that emitted the event, so a slow
    analysis held the user's write open. `handle_event` re-checks
    AGENT_AUTO_ANALYSIS_ENABLED, so switching the feature off also stops
    analysis already queued.
    """
    from app.models.ai_governance import DomainEvent
    from app.services.agents.event_subscriber import handle_event

    db = SessionLocal()
    try:
        event = db.get(DomainEvent, _uuid(payload, "event_id"))
        if event is None:
            return
        handle_event(db, event)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


KINDS: dict[str, JobKind] = {
    kind.name: kind for kind in (
        JobKind("ifc.process_version", run_ifc_processing),
        JobKind("ifc.generate_geometry", run_ifc_geometry),
        JobKind("ingestion.process_file", run_ingestion),
        JobKind("rag.index_file", run_rag_file_index),
        JobKind("rag.project_reindex", run_rag_project_reindex),
        JobKind("agents.handle_event", run_agent_event),
    )
}
