"""What kind of file is this, in the platform's own vocabulary.

`services/file_intelligence` already answers two narrower questions well, and
neither is replaced here:

  * **What format are these bytes?** — `identify_format`, magic-byte backed.
  * **What kind of construction document is this?** — `classify_document`,
    which reads the filename and, for a PDF, the first pages.

What was missing is the layer between them: a *normalized file category* that
the ingestion pipeline can dispatch on. Without one, "is this a spreadsheet?"
gets re-derived from an extension string at every call site, which is precisely
how an upload gate and a processor end up disagreeing about the same file.

A category is decided from evidence in order of how much it proves:

    detected format (magic bytes)  →  extension  →  UNKNOWN

The extension never overrides a signature that already matched something else;
it only breaks ties the container magic cannot (a .docx and an .xlsx are both
ZIP archives), exactly as `identify_format` already does.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from app.services.file_intelligence import capability_for, classify_document, identify_format


class FileCategory(str, enum.Enum):
    """The normalized kinds the pipeline dispatches on.

    Deliberately about *handling*, not about meaning. "Is this a bill of
    quantities" is a different question with a different answer
    (`document_kind`), because the same XLSX can be a BOQ, a schedule or a
    material list and all three are processed identically.
    """

    IFC = "IFC"
    PDF = "PDF"
    DOC = "DOC"
    DOCX = "DOCX"
    XLS = "XLS"
    XLSX = "XLSX"
    DRAWING = "DRAWING"
    IMAGE = "IMAGE"
    TEXT = "TEXT"
    ZIP_PACKAGE = "ZIP_PACKAGE"
    OTHER = "OTHER"


#: Detected format → category. The format is magic-byte evidence, so this is
#: the strongest mapping available and is consulted first.
FORMAT_CATEGORY: dict[str, FileCategory] = {
    "IFC": FileCategory.IFC,
    "PDF": FileCategory.PDF,
    "DOC": FileCategory.DOC,
    "DOCX": FileCategory.DOCX,
    "XLS": FileCategory.XLS,
    "XLSX": FileCategory.XLSX,
    "DWG": FileCategory.DRAWING,
    "DXF": FileCategory.DRAWING,
    "JPEG": FileCategory.IMAGE,
    "PNG": FileCategory.IMAGE,
    "WEBP": FileCategory.IMAGE,
    "ZIP_CONTAINER": FileCategory.ZIP_PACKAGE,
    "TEXT": FileCategory.TEXT,
}

#: Extension → category, used only when the format is inconclusive. An ASCII
#: DXF is indistinguishable from any other text file by its bytes, so the
#: extension is the only evidence there is; it stays a *claim*, which is why
#: the archive and document processors re-check what they actually open.
EXTENSION_CATEGORY: dict[str, FileCategory] = {
    ".ifc": FileCategory.IFC,
    ".pdf": FileCategory.PDF,
    ".doc": FileCategory.DOC,
    ".docx": FileCategory.DOCX,
    ".xls": FileCategory.XLS,
    ".xlsx": FileCategory.XLSX,
    ".dwg": FileCategory.DRAWING,
    ".dxf": FileCategory.DRAWING,
    ".jpg": FileCategory.IMAGE,
    ".jpeg": FileCategory.IMAGE,
    ".png": FileCategory.IMAGE,
    ".webp": FileCategory.IMAGE,
    ".zip": FileCategory.ZIP_PACKAGE,
    ".txt": FileCategory.TEXT,
}

#: A ZIP whose extension says it is really an Office document. `identify_format`
#: already resolves these when it is given the extension; this records the fact
#: separately so archive inspection never tries to expand a .docx as a package.
OFFICE_ZIP_EXTENSIONS = {".docx", ".xlsx"}


@dataclass(frozen=True)
class FileClassification:
    """Everything ingestion learned about a file before opening it properly.

    Carries its own evidence. A category with no stated reason is a guess that
    nobody can audit later, and this one is written to the database.
    """

    category: FileCategory
    detected_format: str
    #: Advisory construction document kind — BOQ, SCHEDULE, DRAWING… Never
    #: enforced, and never allowed to contradict a person's explicit choice.
    document_kind: str | None
    confidence: float
    #: Which evidence decided the category: FORMAT, EXTENSION or NONE.
    source: str
    #: True when the bytes and the extension disagree about the format. Not
    #: automatically an attack — an IFC exported with a .txt name is honest
    #: enough — but it is recorded so a reviewer can see it.
    extension_mismatch: bool
    classification_json: dict

    @property
    def is_supported(self) -> bool:
        return self.category is not FileCategory.OTHER


def _extension_of(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


def classify_file(
    *,
    filename: str | None,
    head: bytes,
    text_sample: str | None = None,
    declared_type: str | None = None,
) -> FileClassification:
    """Decide the category, the format and the advisory document kind.

    `head` is the first megabyte, which is what every existing upload path
    already reads for signature validation — no second pass over the file.
    """
    extension = _extension_of(filename)
    detected = identify_format(head, extension)

    category = FORMAT_CATEGORY.get(detected)
    source = "FORMAT"
    if category is None:
        category = EXTENSION_CATEGORY.get(extension)
        source = "EXTENSION" if category else "NONE"
    if category is None:
        category = FileCategory.OTHER

    # A ZIP that claims to be a Word or Excel file is one, and must not be
    # walked as a design package. `identify_format` has already resolved it
    # when the extension was available; this covers the case where it was not.
    if category is FileCategory.ZIP_PACKAGE and extension in OFFICE_ZIP_EXTENSIONS:
        category = EXTENSION_CATEGORY[extension]
        source = "EXTENSION"

    expected = EXTENSION_CATEGORY.get(extension)
    mismatch = bool(expected and expected is not category)

    document = classify_document(
        filename=filename, content=head, extension=extension,
        text_sample=text_sample, declared_type=declared_type,
    )
    capability = capability_for(detected)

    payload = {
        "category": category.value,
        "categorySource": source,
        "detectedFormat": detected,
        "declaredExtension": extension or None,
        "extensionMismatch": mismatch,
        "documentKind": document.as_json(),
        "capability": {
            "textExtractable": capability.text_extractable,
            "indexable": capability.indexable,
            "destination": capability.destination,
            "handler": capability.handler,
            "limitation": capability.limitation,
        },
    }
    return FileClassification(
        category=category,
        detected_format=detected,
        document_kind=document.document_type,
        confidence=document.confidence,
        source=source,
        extension_mismatch=mismatch,
        classification_json=payload,
    )
