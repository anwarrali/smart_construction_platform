"""The unified file ingestion pipeline.

One way into the platform for every file, whatever it is:

    upload → validate → classify → register → store → queue → process
                                                                 ↓
                                                  READY / PARTIAL / FAILED

Read `pipeline.py` first — it is the orchestration and it names every step.
`contracts.py` defines what a processor is; `registry.py` decides which one
runs; `archives.py` holds the ZIP defences; `state.py` is the lifecycle;
`ifc_bridge.py` is how the existing IFC subsystem appears here without being
owned by it.

Nothing in this package embeds, chunks or indexes anything. It produces the
stable file identity, project association, category, normalized metadata and
processing status that a retrieval layer will later consume — and stops there.
"""

from app.services.ingestion.categories import FileCategory
from app.services.ingestion.errors import IngestionRejected, ProcessingError

__all__ = ["FileCategory", "IngestionRejected", "ProcessingError"]
