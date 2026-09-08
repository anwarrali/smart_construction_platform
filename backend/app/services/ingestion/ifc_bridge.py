"""Making IFC files visible to the unified pipeline without owning them.

The IFC subsystem is complete and validated, and its `IFCModelVersion` row is
the authority on an IFC file's processing state. The unified pipeline needs
those files to appear in a project-wide file view — otherwise "show me every
file on this project" is a lie the moment somebody uploads a model.

The tempting solution is to copy the version's status onto the `IngestedFile`
row whenever it changes. That means editing `ifc_processing_service` at every
terminal point, and it means a mirror that is wrong for as long as an update is
missed. Both are worse than the alternative.

So the status is **derived, never stored twice**: the ingested-file row records
that the file exists and which version owns it, and the processor asks the
version for its state at process time. `IFC_STATUS_MAP` is the one place the
two vocabularies meet.

`register_version` is the only write, and it is called from the IFC upload
endpoint *after* the version is committed. It is deliberately failure-tolerant:
a bookkeeping row that could not be written must never fail an upload the IFC
subsystem has already accepted. That is not swallowing an error — it is logged
and the version is intact and fully usable; the file simply does not appear in
the unified list until the next upload or a backfill.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.ifc import IFCModelVersion
from app.models.ingestion import IngestedFile
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import ProcessorOutcome
from app.services.ingestion.errors import PROCESSING_FAILED, FORMAT_NOT_PARSED
from app.services.ingestion.state import PARTIAL, PROCESSING, QUEUED, READY

logger = logging.getLogger("uvicorn.error").getChild("ingestion.ifc")

SOURCE_ENTITY_TYPE = "IFC_MODEL_VERSION"

#: The IFC engine's eight processing states, mapped onto the ingestion
#: lifecycle. Only the settled ones matter to a caller of `outcome_for_version`;
#: the working states are here so the mapping is total and a new IFC state
#: shows up as a KeyError in tests rather than as a silently wrong status.
IFC_STATUS_MAP: dict[str, str] = {
    "UPLOADED": QUEUED,
    "VALIDATING": PROCESSING,
    "QUEUED": QUEUED,
    "PARSING": PROCESSING,
    "BUILDING_HIERARCHY": PROCESSING,
    "EXTRACTING_ELEMENTS": PROCESSING,
    "EXTRACTING_PROPERTIES": PROCESSING,
    "QUALITY_CHECKS": PROCESSING,
    "ANALYZING": PROCESSING,
    "READY": READY,
    # The IFC engine's own distinction: extraction completed but quality checks
    # raised warnings. That is exactly what PARTIAL means here.
    "READY_WITH_WARNINGS": PARTIAL,
    "FAILED": "FAILED",
    "ARCHIVED": PARTIAL,
}


def linked_version(db: Session, file: IngestedFile) -> IFCModelVersion | None:
    """The IFC revision this file is, when it is one."""
    if file.source_entity_type != SOURCE_ENTITY_TYPE or not file.source_entity_id:
        return None
    return db.get(IFCModelVersion, file.source_entity_id)


def version_details(version: IFCModelVersion) -> dict:
    """The normalized facts the IFC engine already established.

    Read from the version rather than re-derived from the file, because the
    engine's answer is better than anything a header read can produce: it comes
    from a full parse.
    """
    return {
        "ifcVersionId": str(version.id),
        "ifcModelGroupId": str(version.model_group_id),
        "ifcVersionNumber": version.version_number,
        "ifcSchema": version.ifc_schema,
        "authoringApplication": version.authoring_application,
        "entityCount": version.entity_count,
        "discipline": version.discipline,
        "isActive": version.is_active,
        "isBaseline": version.is_baseline,
        "ifcProcessingStatus": version.processing_status,
        "geometryStatus": version.geometry_status,
    }


def outcome_for_version(version: IFCModelVersion, envelope: dict) -> ProcessorOutcome:
    """Project the IFC engine's verdict into an ingestion outcome."""
    status = IFC_STATUS_MAP.get(version.processing_status)
    if status == READY:
        return ProcessorOutcome.ready(envelope)
    if status == "FAILED":
        return ProcessorOutcome.failed(
            version.parsing_error_code or PROCESSING_FAILED,
            detail=version.parsing_error_message,
            metadata=envelope,
        )
    # Still working, warned, or archived. PARTIAL rather than a working state,
    # because a processor may only return a settled outcome — and the IFC
    # workspace, not this row, is where progress is watched.
    return ProcessorOutcome.partial(
        version.parsing_error_code or FORMAT_NOT_PARSED,
        envelope,
        detail=f"IFC version is {version.processing_status}",
    )


def register_version(db: Session, version: IFCModelVersion) -> IngestedFile | None:
    """Record an IFC revision as a file in the unified pipeline.

    Idempotent: a second call for the same version returns the existing row.
    Returns None when the row could not be written, having logged why — see
    the module docstring for why that is not allowed to be an exception.

    **The write happens inside a SAVEPOINT**, and that is the part that makes
    the "cannot raise" promise true rather than merely intended. Catching the
    exception is not enough on its own: a failed `flush` leaves the session's
    transaction in a state where the *caller's* next statement raises
    `PendingRollbackError`, so a swallowed IntegrityError here would still take
    down the IFC upload — in exactly the case the try/except exists to survive.
    `begin_nested` confines the rollback to this block and leaves the outer
    transaction usable.
    """
    try:
        existing = (
            db.query(IngestedFile)
            .filter(
                IngestedFile.source_entity_type == SOURCE_ENTITY_TYPE,
                IngestedFile.source_entity_id == version.id,
            )
            .first()
        )
        if existing is not None:
            return existing

        savepoint = db.begin_nested()
        file = IngestedFile(
            project_id=version.project_id,
            uploaded_by_id=version.uploaded_by_id,
            original_filename=version.original_filename[:255],
            normalized_filename=version.original_filename[:255],
            content_type="application/x-step",
            detected_format="IFC",
            file_category=FileCategory.IFC.value,
            document_kind="DRAWING",
            classification_json={
                "category": FileCategory.IFC.value,
                "categorySource": "IFC_SUBSYSTEM",
                "detectedFormat": "IFC",
            },
            file_size_bytes=version.file_size,
            storage_key=version.storage_key,
            checksum_sha256=version.file_hash,
            status=QUEUED,
            processor_name="ifc",
            source_entity_type=SOURCE_ENTITY_TYPE,
            source_entity_id=version.id,
        )
        db.add(file)
        try:
            db.flush()
        except Exception:
            savepoint.rollback()
            raise
        return file
    except Exception:
        logger.exception(
            "[Ingestion] could not register IFC version %s as a unified file", version.id,
        )
        return None


def backfill_project(db: Session, project_id: uuid.UUID) -> int:
    """Register every IFC revision on a project that has no file row yet.

    Exists because the migration that created `ingested_files` deliberately
    backfills nothing (see its docstring): inventing classification for files
    nobody looked at is indistinguishable from having looked. This makes the
    backfill an explicit, per-project, repeatable operation instead.
    """
    linked = {
        row[0]
        for row in db.query(IngestedFile.source_entity_id).filter(
            IngestedFile.project_id == project_id,
            IngestedFile.source_entity_type == SOURCE_ENTITY_TYPE,
        )
    }
    versions = (
        db.query(IFCModelVersion)
        .filter(IFCModelVersion.project_id == project_id)
        .all()
    )
    created = 0
    for version in versions:
        if version.id in linked:
            continue
        if register_version(db, version) is not None:
            created += 1
    return created
