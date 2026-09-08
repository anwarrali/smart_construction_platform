"""IFC, through an adapter — the mature engine is not touched.

`services/ifc_processing_service.py` is 670 lines of parsing, spatial hierarchy
building, element extraction, comparison and coordination analysis, running in
an isolated child process with its own timeout, its own memory ceiling and its
own eight-state machine. Re-implementing any of that behind this interface
would be a rewrite of working, tested code, and the instruction from the
architecture is the opposite: adapt, do not replace.

So this processor never parses anything. It does two things:

**For an IFC file that arrived through the IFC workspace** — where an
`IFCModelVersion` already exists and `source_entity_id` points at it — the
outcome is *projected* from that version's own status. The IFC engine stays
the single source of truth; this row is a view onto it. See
`services.ingestion.ifc_bridge`.

**For a bare IFC uploaded through the unified endpoint** — with no model group
to attach to and therefore no revision semantics — the header is read from the
first bytes and nothing else happens. The STEP header is plain text at the
start of the file, so schema and authoring application come out for free; a
full parse would be doing the IFC subsystem's job in the wrong place and
without its concurrency ceiling. The outcome is PARTIAL, pointing at the IFC
workspace, which is where a model becomes a revision that can be compared,
tessellated and coordinated.
"""

from __future__ import annotations

import re

from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import BaseProcessor, ProcessorContext, ProcessorOutcome
from app.services.ingestion.errors import EXTRACTION_FAILED, FORMAT_NOT_PARSED, ProcessingError

#: How much of the file is read to find the STEP header. `HEADER; ... ENDSEC;`
#: sits at the very top; anything past this is DATA.
HEADER_READ_BYTES = 64 * 1024

_FILE_SCHEMA = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'", re.IGNORECASE)
_FILE_DESCRIPTION = re.compile(r"FILE_DESCRIPTION\s*\(\s*\(\s*'([^']*)'", re.IGNORECASE)
#: FILE_NAME's seventh argument is the originating system, the fifth is the
#: preprocessor version. Both are quoted strings; the regex takes the whole
#: argument list and splits it rather than counting commas inside quotes.
_FILE_NAME = re.compile(r"FILE_NAME\s*\((.*?)\)\s*;", re.IGNORECASE | re.DOTALL)
_QUOTED = re.compile(r"'((?:[^']|'')*)'")


class IFCProcessor(BaseProcessor):
    name = "ifc"
    categories = frozenset({FileCategory.IFC})
    extracts_text = False

    def extract(self, context: ProcessorContext) -> dict:
        try:
            handle = context.storage.open(context.file.storage_key)
        except (OSError, ValueError) as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc
        try:
            with handle:
                head = handle.read(HEADER_READ_BYTES)
        except OSError as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc

        text = head.decode("utf-8", errors="replace")
        schema = _FILE_SCHEMA.search(text)
        description = _FILE_DESCRIPTION.search(text)
        arguments = _FILE_NAME.search(text)
        quoted = _QUOTED.findall(arguments.group(1)) if arguments else []
        return {
            "schema": schema.group(1).strip() if schema else None,
            "description": description.group(1).strip() if description else None,
            # Positions inside FILE_NAME as ISO 10303-21 defines them:
            # (name, time_stamp, author, organization, preprocessor_version,
            #  originating_system, authorization).
            "authoring_application": quoted[5].strip() if len(quoted) > 5 else None,
            "preprocessor": quoted[4].strip() if len(quoted) > 4 else None,
            "source_name": quoted[0].strip() if quoted else None,
        }

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:
        return {
            "ifcSchema": raw.get("schema"),
            "authoringApplication": raw.get("authoring_application"),
            "preprocessorVersion": raw.get("preprocessor"),
            "headerDescription": raw.get("description"),
            "headerName": raw.get("source_name"),
        }

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        # Deferred: `ifc_bridge` imports the models this module's siblings also
        # import, and importing it at module scope would make the processors
        # package depend on the IFC subsystem at import time.
        from app.services.ingestion import ifc_bridge

        linked = ifc_bridge.linked_version(context.db, context.file)
        details = self.normalize(self.extract(context), context)

        if linked is not None:
            return ifc_bridge.outcome_for_version(
                linked, self.envelope(context, {**details, **ifc_bridge.version_details(linked)},
                                      extraction="MODEL"),
            )

        details["limitation"] = (
            "Header only. Spatial hierarchy, elements and properties are "
            "extracted by the IFC workspace, where a model is a revision that "
            "can be compared, tessellated and coordination-checked."
        )
        details["nextStep"] = "Upload this file to an IFC model group to have it parsed."
        return ProcessorOutcome.partial(
            FORMAT_NOT_PARSED,
            self.envelope(context, details, extraction="METADATA"),
            detail="standalone IFC: header read, no model-group revision to parse into",
        )
