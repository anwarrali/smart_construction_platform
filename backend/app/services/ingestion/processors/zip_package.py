"""A design package: one upload, many files, one authorization decision.

A consultant issues "Rev C — For Construction" as a single ZIP holding
architectural sheets, structural sheets, MEP layouts, a specification, a
schedule and sometimes a federated model. Ingesting it must produce a *file
each*, classified individually, or none of the downstream work — retrieval,
cross-document reasoning, linking a drawing to a task — has anything to
operate on.

Three properties this implementation holds to:

**The archive's names are labels, never paths.** Every member is stored under a
key the platform generates. `archives.safe_entry_name` still refuses traversal
outright, so a hostile package is rejected rather than quietly neutralised, but
even if that check were removed, no attacker-controlled string reaches the
filesystem.

**Members are registered, not extracted to disk.** Each is read as a bounded
stream and written straight through the storage abstraction, so a package
behaves identically on local disk and on object storage.

**A nested archive is stored, not opened.** `INGESTION_ZIP_MAX_DEPTH` bounds
recursion at one level by default. Unbounded recursion is how every "we check
the total size" defence is defeated — the check is per-archive, and the attack
is a million archives.

The package itself settles READY when every member was registered, and PARTIAL
when some were skipped or rejected — with the list of what was left out, so
"my package has 40 drawings but I see 38" has an answer on the record.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.services.ingestion import archives
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import BaseProcessor, ProcessorContext, ProcessorOutcome
from app.services.ingestion.errors import (
    ARCHIVE_NESTING_LIMIT, EXTRACTION_FAILED, IngestionRejected, ProcessingError,
)
from app.services.ingestion.state import PARTIAL, READY

logger = logging.getLogger("uvicorn.error").getChild("ingestion.zip")


class ZipPackageProcessor(BaseProcessor):
    name = "zip-package"
    categories = frozenset({FileCategory.ZIP_PACKAGE})
    extracts_text = False

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        self.validate(context)
        # Deferred: the pipeline imports the registry, which imports the
        # processors. Importing it at module scope would close that circle.
        from app.services.ingestion import pipeline

        if context.depth >= settings.INGESTION_ZIP_MAX_DEPTH:
            details = {
                "limitation": (
                    "Archives nested deeper than the configured limit are stored "
                    "but not expanded."
                ),
                "depth": context.depth,
                "maxDepth": settings.INGESTION_ZIP_MAX_DEPTH,
            }
            return ProcessorOutcome.partial(
                ARCHIVE_NESTING_LIMIT,
                self.envelope(context, details, extraction="NONE"),
                detail=f"depth {context.depth} reached the nesting limit",
            )

        try:
            with context.storage.local_path(context.file.storage_key) as path:
                archive = archives.open_archive(path)
                with archive:
                    inspection = archives.inspect(archive)
                    registered, rejected = self._register_members(
                        context, archive, inspection, pipeline,
                    )
        except IngestionRejected as exc:
            # A hostile or unreadable archive fails the package outright. It is
            # not PARTIAL: nothing about it can be trusted, so nothing from it
            # is kept.
            raise ProcessingError(exc.code, exc.detail) from exc
        except ProcessingError:
            raise
        except Exception as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc

        skipped = [dict(item) for item in inspection.skipped] + rejected
        details = {
            "entryCount": len(inspection.entries),
            "registeredCount": len(registered),
            "skippedCount": len(skipped),
            "declaredUncompressedBytes": inspection.total_declared_size,
            "skipped": skipped[:100],
            "members": [
                {
                    "fileId": str(child.id),
                    "name": child.original_filename,
                    "category": child.file_category,
                    "documentKind": child.document_kind,
                }
                for child in registered[:200]
            ],
        }
        envelope = self.envelope(context, details, extraction="PACKAGE")
        if skipped:
            return ProcessorOutcome(
                status=PARTIAL, metadata=envelope, children=registered,
                error_code=EXTRACTION_FAILED,
                error_message=f"{len(skipped)} of {len(inspection.entries) + len(inspection.skipped)} entries were not registered",
            )
        return ProcessorOutcome(status=READY, metadata=envelope, children=registered)

    def _register_members(self, context, archive, inspection, pipeline):
        """Store and register every safe entry; report the ones that could not be.

        A single bad member does not condemn the package. `inspect` has already
        refused everything that makes the *archive* untrustworthy — traversal,
        symlinks, declared expansion over the ceiling — so what can still go
        wrong here is one entry that is corrupt or that validation refuses on
        its own terms (an executable in a drawings package, say). Dropping that
        one and recording why is what a person doing this by hand would do.
        """
        registered = []
        rejected = []
        limit = settings.INGESTION_ZIP_MAX_ENTRY_MB * 1024 * 1024
        for entry in inspection.entries:
            try:
                payload = archives.read_entry(archive, entry, limit=limit)
                child = pipeline.register_bytes(
                    context.db,
                    project_id=context.file.project_id,
                    uploader_id=context.file.uploaded_by_id,
                    filename=entry.filename,
                    payload=payload,
                    parent=context.file,
                    depth=context.depth + 1,
                    package_path=entry.name,
                )
            except IngestionRejected as exc:
                rejected.append({"name": entry.name, "reason": exc.code})
                continue
            except Exception:
                # One unreadable member must not take the package with it, and
                # it must not vanish either.
                logger.exception("[Ingestion] package member %r failed", entry.name)
                rejected.append({"name": entry.name, "reason": EXTRACTION_FAILED})
                continue
            registered.append(child)

        # Members are processed after all of them are registered, so a package
        # whose 200th entry fails still has its first 199 on the record.
        for child in registered:
            pipeline.run(context.db, child, depth=context.depth + 1)
        return registered, rejected
