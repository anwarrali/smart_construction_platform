"""Word and Excel, read with the standard library and nothing else.

`docs/FILE_INTELLIGENCE.md` recorded DOCX and XLSX as "stored and downloadable
only — no reader is installed". That was true, and it was also a bigger
limitation than it needed to be: both formats are ZIP archives of XML, and the
two facts the platform actually wants from them — the body text of a
specification, the sheet names of a bill of quantities — are readable with
`zipfile` and no dependency at all.

So this processor does that much, and stops there. It is not a Word engine: it
does not read tables as tables, headers, footnotes, tracked changes, or
formatting, and it does not read *cell values* out of a workbook. Doing those
properly needs `python-docx` and `openpyxl`, which is a dependency decision
with a maintenance cost, and no evidence yet says the project needs it. What it
needs today is enough text to tell a method statement from a bill of
quantities, and enough structure to say what a workbook contains.

The legacy binary formats — `.doc` and `.xls`, both OLE2 — are stored and not
parsed. There is no standard-library path into them at all.

## Security

A DOCX is an archive, so every archive protection applies to it: the entry is
size-bounded on read, the compression ratio is checked, and nothing is written
to disk. A "Word document" that is really a zip bomb is refused by the same
code that refuses one calling itself a design package.
"""

from __future__ import annotations

import re
import zipfile

from app.services.ingestion import archives
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import BaseProcessor, ProcessorContext, ProcessorOutcome
from app.services.ingestion.errors import (
    EXTRACTION_FAILED, FORMAT_NOT_PARSED, IngestionRejected, ProcessingError,
)

#: The part of a .docx that holds the body. Headers, footers and footnotes live
#: in sibling parts and are deliberately not read — they are boilerplate, and
#: including them would put a page number in front of every classification.
DOCX_BODY_PART = "word/document.xml"
#: The part of an .xlsx that names the sheets.
XLSX_WORKBOOK_PART = "xl/workbook.xml"

#: How much decompressed XML one part may produce. A specification is large;
#: a bomb is larger.
MAX_PART_BYTES = 24 * 1024 * 1024
SAMPLE_CHARACTERS = 4000

_TAG = re.compile(rb"<[^>]+>")
#: Word marks paragraph and line breaks with these; turning them into newlines
#: before stripping tags is what stops every heading running into its body.
_BREAKS = re.compile(rb"</w:p>|<w:br\b[^>]*/?>|</w:tr>")
_SHEET_NAME = re.compile(r'<sheet\b[^>]*\bname="([^"]*)"', re.IGNORECASE)


def _entry(archive: zipfile.ZipFile, part: str) -> bytes | None:
    """Read one named part through the archive guard, or None if absent."""
    inspection = archives.inspect(archive)
    for entry in inspection.entries:
        if entry.name == part:
            return archives.read_entry(archive, entry, limit=MAX_PART_BYTES)
    return None


def _open(context: ProcessorContext) -> zipfile.ZipFile:
    with context.storage.local_path(context.file.storage_key) as path:
        return archives.open_archive(path)


class DocxProcessor(BaseProcessor):
    name = "docx"
    categories = frozenset({FileCategory.DOCX})
    extracts_text = True

    def extract(self, context: ProcessorContext) -> dict:
        try:
            archive = _open(context)
        except IngestionRejected as exc:
            raise ProcessingError(exc.code, exc.detail) from exc
        try:
            with archive:
                payload = _entry(archive, DOCX_BODY_PART)
        except IngestionRejected as exc:
            raise ProcessingError(exc.code, exc.detail) from exc
        except Exception as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc

        if payload is None:
            # A ZIP whose extension says .docx but which holds no Word body.
            # Not necessarily hostile — some tools emit flat OPC — but nothing
            # here can read it, and saying so beats returning empty text.
            return {"text": "", "body_present": False, "paragraphs": 0}

        spaced = _BREAKS.sub(b"\n", payload)
        text = _TAG.sub(b"", spaced).decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines()]
        kept = [line for line in lines if line]
        return {"text": "\n".join(kept), "body_present": True, "paragraphs": len(kept)}

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:
        text = raw.get("text") or ""
        return {
            "bodyPresent": raw.get("body_present", False),
            "paragraphCount": raw.get("paragraphs", 0),
            "textCharacters": len(text),
            "textSample": text[:SAMPLE_CHARACTERS] or None,
        }

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        self.validate(context)
        details = self.normalize(self.extract(context), context)
        has_text = bool(details["textCharacters"])
        envelope = self.envelope(context, details, extraction="TEXT" if has_text else "NONE")
        if not has_text:
            return ProcessorOutcome.partial(
                EXTRACTION_FAILED, envelope,
                detail="no readable body text in word/document.xml",
            )
        return ProcessorOutcome.ready(envelope)


class XlsxProcessor(BaseProcessor):
    name = "xlsx"
    categories = frozenset({FileCategory.XLSX})
    #: Sheet names are structure, not content. Nothing here reads cell values.
    extracts_text = False

    def extract(self, context: ProcessorContext) -> dict:
        try:
            archive = _open(context)
        except IngestionRejected as exc:
            raise ProcessingError(exc.code, exc.detail) from exc
        try:
            with archive:
                payload = _entry(archive, XLSX_WORKBOOK_PART)
        except IngestionRejected as exc:
            raise ProcessingError(exc.code, exc.detail) from exc
        except Exception as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc

        if payload is None:
            return {"sheets": []}
        xml = payload.decode("utf-8", errors="replace")
        return {"sheets": [name.strip() for name in _SHEET_NAME.findall(xml) if name.strip()]}

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:
        sheets = raw.get("sheets") or []
        return {
            "sheetCount": len(sheets),
            "sheetNames": sheets,
            "cellValuesRead": False,
            "limitation": (
                "Sheet names only. Reading cell values needs a spreadsheet "
                "library, which is not installed."
            ),
        }

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        self.validate(context)
        details = self.normalize(self.extract(context), context)
        envelope = self.envelope(context, details, extraction="METADATA")
        if not details["sheetCount"]:
            return ProcessorOutcome.partial(
                EXTRACTION_FAILED, envelope, detail="no sheets found in xl/workbook.xml",
            )
        # PARTIAL, not READY: the workbook's actual contents — the quantities,
        # the rates, the dates — were not read. Calling this READY would tell
        # a person their BOQ had been understood.
        return ProcessorOutcome.partial(
            FORMAT_NOT_PARSED, envelope, detail="sheet names extracted; cell values not read",
        )


class LegacyOfficeProcessor(BaseProcessor):
    """`.doc` and `.xls`: stored, downloadable, and not read.

    A processor that does nothing is still worth writing down. Without it,
    "why is there no text from this file?" has no answer in the code, and the
    file falls through to a generic fallback that cannot say which format's
    limitation it hit.
    """

    name = "legacy-office"
    categories = frozenset({FileCategory.DOC, FileCategory.XLS})
    extracts_text = False

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        details = {
            "limitation": (
                "The pre-2007 binary Office formats (OLE2) have no standard-library "
                "reader. The file is stored and downloadable."
            ),
            "recommendation": "Save as .docx or .xlsx for the contents to be readable.",
        }
        return ProcessorOutcome.partial(
            FORMAT_NOT_PARSED,
            self.envelope(context, details, extraction="NONE"),
            detail="legacy OLE2 office format",
        )
