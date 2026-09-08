"""One place that answers *what is this file, and what can we do with it?*

The platform already ingests IFC, PDFs, spreadsheets, drawings, photos and
audio, but each path grew its own answers. Two gaps followed from that.

The first is identity. Every uploader checks that a file's bytes match the
extension it claims, which is a security gate and answers only yes or no. It
never records what the file actually *is*, so nothing downstream can act on the
format without re-deriving it.

The second is kind. `documents.document_type` is whatever the uploader picked
from a dropdown, defaulting to "other" — an unverified claim. A bill of
quantities filed as "other" is invisible to anything that reasons about
document types, and nothing has ever looked inside a file to disagree.

This module supplies both, and a registry declaring, per format, what can be
extracted and where it goes. Classification is *evidence-backed and advisory*:
it reports what it saw and how sure it is, and never silently overwrites a
person's explicit choice. The human stays authoritative; this records a second
opinion, and says when the two disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- IDENTIFY ---------------------------------------------------------------

#: Magic-byte signatures, as (offset, bytes) pairs that must all match. This is
#: the single source of truth: `file_storage._matches_signature` validates a
#: claimed extension against it, and `identify_format` asks it what a file is.
#: Two copies of this knowledge is how an upload gate and a classifier end up
#: disagreeing about the same bytes.
FORMAT_SIGNATURES: dict[str, tuple[tuple[int, bytes], ...]] = {
    "JPEG": ((0, b"\xff\xd8\xff"),),
    "PNG": ((0, b"\x89PNG\r\n\x1a\n"),),
    "PDF": ((0, b"%PDF-"),),
    "ZIP_CONTAINER": ((0, b"PK\x03\x04"),),
    "OLE2_CONTAINER": ((0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),),
    "WEBP": ((0, b"RIFF"), (8, b"WEBP")),
    "WAV": ((0, b"RIFF"), (8, b"WAVE")),
    "OGG": ((0, b"OggS"),),
    "MP4_CONTAINER": ((4, b"ftyp"),),
    "WEBM": ((0, b"\x1a\x45\xdf\xa3"),),
    "DWG": ((0, b"AC10"),),
    # Binary DXF announces itself. An *ASCII* DXF has no signature at all —
    # it is a text file — and is identified as TEXT, which is why
    # `file_storage.EXTENSION_FORMATS` accepts both for a `.dxf`.
    "DXF": ((0, b"AutoCAD Binary DXF"),),
}

#: Extensions whose real format cannot be told apart by magic bytes alone.
#: `.docx` and `.xlsx` are both ZIP; `.doc` and `.xls` are both OLE2. The
#: extension is the only available discriminator, and is treated as a claim.
CONTAINER_FORMATS = {
    "ZIP_CONTAINER": {".docx": "DOCX", ".xlsx": "XLSX"},
    "OLE2_CONTAINER": {".doc": "DOC", ".xls": "XLS"},
    "MP4_CONTAINER": {".m4a": "M4A", ".mp4": "MP4"},
}


def _is_ifc(content: bytes) -> bool:
    sample = content[:65536].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").upper()
    return sample.startswith(b"ISO-10303-21;") and b"HEADER;" in sample and b"DATA;" in sample


def _is_mpeg_audio(content: bytes) -> bool:
    return content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)


def identify_format(content: bytes, extension: str | None = None) -> str:
    """What these bytes actually are, regardless of what they were called.

    `extension` only breaks ties between formats that share a container magic
    (a .docx and an .xlsx are both ZIP archives). It is never allowed to
    override a signature that already matched something else.
    """
    if not content:
        return "EMPTY"
    if _is_ifc(content):
        return "IFC"
    for name, parts in FORMAT_SIGNATURES.items():
        if all(content[offset:offset + len(value)] == value for offset, value in parts):
            resolved = CONTAINER_FORMATS.get(name)
            if resolved:
                return resolved.get((extension or "").lower(), name)
            return name
    if _is_mpeg_audio(content):
        return "MP3"
    if _looks_like_text(content):
        return "TEXT"
    return "UNKNOWN"


def _looks_like_text(content: bytes) -> bool:
    sample = content[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


# --- THE REGISTRY -----------------------------------------------------------

@dataclass(frozen=True)
class FormatCapability:
    """What the platform can do with one format, and where the result lands.

    Written down rather than implied so that "we accept this file but extract
    nothing from it" is a visible, testable statement instead of something a
    reader has to infer from the absence of code.
    """

    format_id: str
    label: str
    #: Can readable text be pulled out of it today?
    text_extractable: bool
    #: Can it be embedded and retrieved by the RAG layer?
    indexable: bool
    #: Where extracted information is stored. None when nothing is extracted.
    destination: str | None
    #: The component that does the extracting.
    handler: str | None
    #: Why, when the answer is "nothing".
    limitation: str | None = None


REGISTRY: dict[str, FormatCapability] = {
    "IFC": FormatCapability(
        "IFC", "IFC building model", text_extractable=False, indexable=False,
        destination="ifc_elements / ifc_spatial_nodes / ifc_coordination_findings",
        handler="services.ifc_parser",
    ),
    "PDF": FormatCapability(
        "PDF", "PDF document", text_extractable=True, indexable=True,
        destination="document_chunks", handler="services.rag.pdf_text",
        limitation="A scanned PDF with no text layer cannot be indexed; OCR is not supported.",
    ),
    "DWG": FormatCapability(
        "DWG", "AutoCAD drawing", text_extractable=False, indexable=False,
        destination=None, handler=None,
        limitation=(
            "Stored and downloadable, but nothing is extracted. DWG is a closed binary "
            "format; reading it needs either a licensed SDK or an external converter, "
            "and no evidence yet shows the project needs that. DXF would be the "
            "cheaper first step if it does."
        ),
    ),
    "DOCX": FormatCapability(
        "DOCX", "Word document", text_extractable=True, indexable=False,
        destination="ingested_files.metadata_json",
        handler="services.ingestion.processors.office",
        limitation=(
            "Body text only, read from word/document.xml with the standard library. "
            "Tables are flattened to their cell text; headers, footers, footnotes and "
            "tracked changes are not read, and the text is not indexed for retrieval."
        ),
    ),
    "XLSX": FormatCapability(
        "XLSX", "Excel workbook", text_extractable=False, indexable=False,
        destination="ingested_files.metadata_json",
        handler="services.ingestion.processors.office",
        limitation=(
            "Sheet names only. Cell values are not read, so a BOQ or schedule is "
            "identified and stored, not parsed. That needs a spreadsheet library."
        ),
    ),
    "DXF": FormatCapability(
        "DXF", "AutoCAD exchange drawing", text_extractable=False, indexable=False,
        destination=None, handler=None,
        limitation=(
            "Stored and downloadable. DXF is readable in principle — it is text — "
            "but reading it usefully means interpreting entities and layers, which "
            "is a drawing engine rather than a parser."
        ),
    ),
    "ZIP_CONTAINER": FormatCapability(
        "ZIP_CONTAINER", "Design package", text_extractable=False, indexable=False,
        destination="ingested_files (one row per member)",
        handler="services.ingestion.processors.zip_package",
        limitation=(
            "Members are registered and classified individually. Archives nested "
            "deeper than INGESTION_ZIP_MAX_DEPTH are stored, not expanded."
        ),
    ),
    "TEXT": FormatCapability(
        "TEXT", "Plain text", text_extractable=True, indexable=False,
        destination=None, handler=None,
        limitation="Text is readable but plain-text indexing is not wired into the RAG pipeline.",
    ),
    "JPEG": FormatCapability("JPEG", "Photograph", False, False, "media_assets", None,
                             "Images are evidence, not text. No vision extraction is implemented."),
    "PNG": FormatCapability("PNG", "Image", False, False, "media_assets", None,
                            "Images are evidence, not text. No vision extraction is implemented."),
    "WEBP": FormatCapability("WEBP", "Image", False, False, "media_assets", None,
                             "Images are evidence, not text. No vision extraction is implemented."),
}

#: Formats accepted somewhere in the platform but carrying no project content.
#: ZIP_CONTAINER left this set when the ingestion pipeline gave it a real
#: destination: a design package is now expanded into one registered file per
#: member, which is exactly the "extraction path" whose absence put it here.
AUXILIARY_FORMATS = {"WAV", "OGG", "MP3", "M4A", "MP4", "WEBM", "DOC", "XLS",
                     "OLE2_CONTAINER", "MP4_CONTAINER"}


def capability_for(format_id: str) -> FormatCapability:
    return REGISTRY.get(format_id) or FormatCapability(
        format_id, format_id.replace("_", " ").title(), False, False, None, None,
        "This format has no declared extraction capability.",
    )


# --- CLASSIFY ---------------------------------------------------------------

#: Construction document kinds, and the wording that identifies each. Arabic
#: terms sit beside English because the platform is used in both, and a
#: bilingual project files documents in both.
#:
#: Ordering matters: the first kind whose evidence is found wins, so the more
#: specific kinds are listed before the general ones. "Bill of quantities" must
#: beat "specification" when a document says both.
TYPE_TERMS: list[tuple[str, tuple[str, ...]]] = [
    ("BOQ", ("bill of quantities", "boq", "bills of quantities", "quantity schedule",
             "priced bill", "جدول الكميات", "جداول الكميات", "حصر الكميات")),
    ("SCHEDULE", ("construction programme", "construction schedule", "project programme",
                  "baseline programme", "gantt", "look ahead", "lookahead", "work programme",
                  "الجدول الزمني", "البرنامج الزمني", "جدول المشروع")),
    ("CONTRACT", ("contract agreement", "conditions of contract", "subcontract",
                  "letter of award", "tender agreement", "عقد", "اتفاقية", "شروط العقد")),
    ("SPECIFICATION", ("technical specification", "specification", "particular specification",
                       "method statement", "مواصفات", "المواصفات الفنية")),
    ("PERMIT", ("building permit", "work permit", "permit to work", "approval certificate",
                "تصريح", "رخصة", "إذن عمل")),
    ("INVOICE", ("invoice", "payment certificate", "interim payment", "tax invoice",
                 "فاتورة", "شهادة دفع", "مستخلص")),
    ("DRAWING", ("drawing", "drawing register", "shop drawing", "as-built drawing",
                 "general arrangement", "layout plan", "مخطط", "مخططات", "رسم تنفيذي")),
    ("REPORT", ("site report", "progress report", "inspection report", "daily report",
                "monthly report", "تقرير", "تقرير يومي", "تقرير تقدم")),
]

#: Formats that are a document kind by their nature, whatever they are named.
FORMAT_IMPLIES_TYPE = {"DWG": "DRAWING", "DXF": "DRAWING", "IFC": "DRAWING"}

CONFIDENCE_BY_SOURCE = {"CONTENT": 0.9, "FILENAME": 0.7, "FORMAT": 0.8}


#: Pages read to classify a document. The kind is announced on the cover or in
#: the header of the first sheet; reading further costs time on every upload
#: and adds nothing.
CLASSIFICATION_SAMPLE_PAGES = 2
#: Above this, no sample is taken. Classification is a convenience, and it must
#: never turn a large upload into a slow one.
CLASSIFICATION_MAX_SAMPLE_BYTES = 40 * 1024 * 1024


def text_sample(path, format_id: str, *, max_pages: int = CLASSIFICATION_SAMPLE_PAGES) -> str | None:
    """A short readable sample, or None when the format cannot give one.

    Deliberately total: any failure returns None. Classification is advisory,
    so a PDF that pypdf dislikes must fall back to filename evidence rather
    than break an upload that has otherwise succeeded.
    """
    if format_id != "PDF":
        return None
    try:
        if path.stat().st_size > CLASSIFICATION_MAX_SAMPLE_BYTES:
            return None
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = reader.pages[:max_pages]
        return "\n".join((page.extract_text() or "") for page in pages).strip() or None
    except Exception:
        return None


@dataclass(frozen=True)
class Classification:
    """A second opinion about what a document is, with its reasons attached."""

    document_type: str
    confidence: float
    source: str
    evidence: str | None
    detected_format: str
    #: True when a person explicitly chose a different type. Not an error —
    #: they may well be right — but worth surfacing rather than hiding.
    disagrees_with_declared: bool = False
    declared_type: str | None = None
    considered: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        return {
            "documentType": self.document_type, "confidence": self.confidence,
            "source": self.source, "evidence": self.evidence,
            "detectedFormat": self.detected_format,
            "disagreesWithDeclared": self.disagrees_with_declared,
            "declaredType": self.declared_type,
            "considered": self.considered,
        }


def _normalise(value: str | None) -> str:
    """Fold to a form where whole-phrase matching is meaningful."""
    return " ".join(re.findall(r"[\w]+", str(value or "").casefold(), flags=re.UNICODE))


def _match_terms(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    for document_type, terms in TYPE_TERMS:
        # Longest first, so a document saying "drawing register" is recorded as
        # having said that rather than merely "drawing". The evidence string is
        # shown to a person, and the more specific phrase is the better reason.
        for term in sorted(terms, key=len, reverse=True):
            normalised = _normalise(term)
            if normalised and re.search(rf"(?<!\w){re.escape(normalised)}(?!\w)", text):
                return document_type, term
    return None


def classify_document(
    *,
    filename: str | None,
    content: bytes | None = None,
    text_sample: str | None = None,
    declared_type: str | None = None,
    extension: str | None = None,
) -> Classification:
    """Decide what kind of construction document this is, and say why.

    Evidence is weighed in order of how much it proves. Words inside the
    document are the strongest signal, the filename is weaker but usually
    deliberate, and the format itself settles cases where the content cannot be
    read at all — a DWG is a drawing whatever it is called.

    Nothing here guesses. A document with no recognisable evidence is returned
    as OTHER at low confidence, which is a truthful "I don't know" rather than
    a plausible-looking label.
    """
    detected = identify_format(content or b"", extension) if content is not None else "UNKNOWN"
    considered: dict = {}

    from_content = _match_terms(_normalise(text_sample))
    if from_content:
        considered["content"] = from_content[1]
    from_filename = _match_terms(_normalise(filename))
    if from_filename:
        considered["filename"] = from_filename[1]
    from_format = FORMAT_IMPLIES_TYPE.get(detected)
    if from_format:
        considered["format"] = detected

    if from_content:
        document_type, evidence, source = from_content[0], from_content[1], "CONTENT"
    elif from_format:
        document_type, evidence, source = from_format, f"File format is {detected}", "FORMAT"
    elif from_filename:
        document_type, evidence, source = from_filename[0], from_filename[1], "FILENAME"
    else:
        return Classification(
            document_type="OTHER", confidence=0.2, source="NONE", evidence=None,
            detected_format=detected, declared_type=declared_type,
            disagrees_with_declared=False, considered=considered,
        )

    declared = (declared_type or "").strip().upper() or None
    return Classification(
        document_type=document_type,
        confidence=CONFIDENCE_BY_SOURCE[source],
        source=source,
        evidence=evidence,
        detected_format=detected,
        declared_type=declared,
        # A declared "OTHER" is a default, not a decision, so differing from it
        # is not a disagreement worth flagging to anyone.
        disagrees_with_declared=bool(declared and declared not in {"OTHER", document_type}),
        considered=considered,
    )
