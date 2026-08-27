"""Format identification, the capability registry, and document classification.

The upload signature gate is security-relevant and predates this module, so the
first section pins the refactor: `_matches_signature` now asks
`identify_format` instead of carrying its own copy of the magic bytes, and must
answer exactly as it did before for every extension and every payload.
"""

import pytest

from app.services.file_intelligence import (
    AUXILIARY_FORMATS,
    REGISTRY,
    Classification,
    capability_for,
    classify_document,
    identify_format,
)
from app.services.file_storage import SIGNATURE_VERIFIED_EXTENSIONS, _matches_signature

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF"
ZIP = b"PK\x03\x04" + b"\x00" * 32
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "
WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "
OGG = b"OggS" + b"\x00" * 32
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 16
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
MP3 = b"ID3\x03\x00\x00\x00" + b"\x00" * 32
DWG = b"AC1027" + b"\x00" * 32
IFC = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\nENDSEC;\n"
TEXT = b"Bill of Quantities\nItem 1\n"


def _original_matches_signature(extension: str, content: bytes) -> bool:
    """The implementation as it stood before the shared table existed."""
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".pdf":
        return content.startswith(b"%PDF-")
    if extension in {".docx", ".xlsx"}:
        return content.startswith(b"PK\x03\x04")
    if extension in {".doc", ".xls"}:
        return content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if extension == ".webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if extension == ".wav":
        return content.startswith(b"RIFF") and content[8:12] == b"WAVE"
    if extension == ".ogg":
        return content.startswith(b"OggS")
    if extension in {".m4a", ".mp4"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if extension == ".webm":
        return content.startswith(b"\x1a\x45\xdf\xa3")
    if extension in {".mpeg", ".mpga", ".mp3"}:
        return content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    if extension == ".dwg":
        return content.startswith(b"AC10")
    if extension == ".ifc":
        sample = content[:65536].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").upper()
        return sample.startswith(b"ISO-10303-21;") and b"HEADER;" in sample and b"DATA;" in sample
    return extension == ".txt"


PAYLOADS = {
    "pdf": PDF, "png": PNG, "jpeg": JPEG, "zip": ZIP, "ole2": OLE2, "webp": WEBP,
    "wav": WAV, "ogg": OGG, "m4a": M4A, "webm": WEBM, "mp3": MP3, "dwg": DWG,
    "ifc": IFC, "text": TEXT, "empty": b"", "junk": b"\x01\x02\x03\x04\x05",
    "html": b"<html><body>hi</body></html>",
    "frame_sync_mp3": b"\xff\xfb\x90\x00" + b"\x00" * 32,
}
EXTENSIONS = sorted(SIGNATURE_VERIFIED_EXTENSIONS | {".txt", ".mp4", ".webm", ".mpeg", ".mpga", ".zip", ""})


@pytest.mark.parametrize("extension", EXTENSIONS)
@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_the_signature_gate_answers_exactly_as_it_did_before(extension, name):
    content = PAYLOADS[name]
    assert _matches_signature(extension, content) == _original_matches_signature(extension, content)


def test_the_signature_gate_still_rejects_a_disguised_file():
    assert not _matches_signature(".pdf", b"<script>alert(1)</script>")
    assert not _matches_signature(".ifc", b"ISO-10303-21;\nHEADER;\n")
    assert not _matches_signature(".png", JPEG)


# --- Identification ---------------------------------------------------------

@pytest.mark.parametrize("content, expected", [
    (PDF, "PDF"), (PNG, "PNG"), (JPEG, "JPEG"), (WEBP, "WEBP"), (WAV, "WAV"),
    (OGG, "OGG"), (WEBM, "WEBM"), (MP3, "MP3"), (DWG, "DWG"), (IFC, "IFC"),
    (TEXT, "TEXT"), (b"", "EMPTY"), (b"\x01\x02\x03\x00\xff", "UNKNOWN"),
])
def test_a_file_is_identified_from_its_bytes(content, expected):
    assert identify_format(content) == expected


def test_the_extension_only_breaks_ties_between_container_formats():
    assert identify_format(ZIP, ".docx") == "DOCX"
    assert identify_format(ZIP, ".xlsx") == "XLSX"
    assert identify_format(OLE2, ".doc") == "DOC"
    assert identify_format(OLE2, ".xls") == "XLS"
    # Without the hint the honest answer is the container itself.
    assert identify_format(ZIP) == "ZIP_CONTAINER"


def test_an_extension_cannot_override_a_signature_that_already_matched():
    # A PDF called `.xlsx` is still a PDF. Identification reports what it is.
    assert identify_format(PDF, ".xlsx") == "PDF"
    assert identify_format(IFC, ".pdf") == "IFC"


def test_ifc_is_recognised_despite_a_byte_order_mark_and_leading_whitespace():
    assert identify_format(b"\xef\xbb\xbf\n  " + IFC) == "IFC"


# --- The registry -----------------------------------------------------------

def test_every_registered_format_either_has_a_destination_or_explains_why_not():
    """The gate's "extracted information has a clear destination", enforced.

    Being readable is not the same as being stored: plain text can be read but
    nothing keeps it, and saying so is the honest declaration. What must never
    happen is a format that neither names a destination nor explains its
    absence, because that leaves a reader guessing.
    """
    for capability in REGISTRY.values():
        assert capability.destination or capability.limitation, \
            f"{capability.format_id} names no destination and gives no reason"


def test_an_indexable_format_can_actually_have_text_pulled_out_of_it():
    for capability in REGISTRY.values():
        if capability.indexable:
            assert capability.text_extractable
            assert capability.handler


def test_ifc_routes_to_the_ifc_tables_and_is_not_treated_as_a_document():
    ifc = capability_for("IFC")
    assert "ifc_elements" in ifc.destination
    assert ifc.indexable is False


def test_pdf_is_the_indexable_document_format():
    pdf = capability_for("PDF")
    assert pdf.indexable is True
    assert pdf.destination == "document_chunks"
    assert "OCR" in pdf.limitation


def test_dwg_is_declared_as_stored_but_not_extracted():
    """The Phase 3 decision, written down where it can be checked."""
    dwg = capability_for("DWG")
    assert dwg.text_extractable is False
    assert dwg.destination is None
    assert "DXF" in dwg.limitation


def test_a_spreadsheet_is_honest_about_not_being_parsed():
    xlsx = capability_for("XLSX")
    assert xlsx.destination is None
    assert "BOQ" in xlsx.limitation


def test_an_unregistered_format_reports_no_capability_rather_than_failing():
    unknown = capability_for("SOMETHING_NEW")
    assert unknown.text_extractable is False
    assert unknown.limitation


def test_auxiliary_formats_are_deliberately_outside_the_registry():
    # Audio and legacy Office containers carry no project document content;
    # listing them would imply an extraction path that does not exist.
    assert not AUXILIARY_FORMATS & set(REGISTRY)


# --- Classification ---------------------------------------------------------

def classify(**kwargs) -> Classification:
    kwargs.setdefault("filename", None)
    return classify_document(**kwargs)


def test_content_wording_identifies_a_bill_of_quantities():
    result = classify(filename="scan_004.pdf", content=PDF,
                      text_sample="BILL OF QUANTITIES\nSection A — Substructure")
    assert result.document_type == "BOQ"
    assert result.source == "CONTENT"
    assert result.evidence == "bill of quantities"
    assert result.confidence == 0.9


def test_arabic_content_is_classified_too():
    result = classify(filename="doc.pdf", content=PDF, text_sample="جدول الكميات للمشروع")
    assert result.document_type == "BOQ"
    assert result.source == "CONTENT"


def test_the_filename_is_used_when_the_content_says_nothing():
    result = classify(filename="Contract Agreement - Package 2.pdf", content=PDF, text_sample="")
    assert result.document_type == "CONTRACT"
    assert result.source == "FILENAME"
    assert result.confidence == 0.7


def test_content_outranks_the_filename():
    result = classify(filename="drawing register.pdf", content=PDF,
                      text_sample="BILL OF QUANTITIES")
    assert result.document_type == "BOQ"
    assert result.considered["filename"] == "drawing register"


def test_a_drawing_format_is_a_drawing_whatever_it_is_called():
    result = classify(filename="untitled.dwg", content=DWG)
    assert result.document_type == "DRAWING"
    assert result.source == "FORMAT"
    assert result.detected_format == "DWG"


def test_a_document_with_no_evidence_is_not_given_a_plausible_label():
    result = classify(filename="scan_0012.pdf", content=PDF, text_sample="Page 1 of 4")
    assert result.document_type == "OTHER"
    assert result.source == "NONE"
    assert result.confidence <= 0.2
    assert result.evidence is None


def test_a_partial_word_does_not_count_as_evidence():
    # "invoiced" in a sentence is not an invoice.
    result = classify(filename="notes.pdf", content=PDF,
                      text_sample="The works were invoiced separately last month")
    assert result.document_type == "OTHER"


def test_a_more_specific_kind_wins_over_a_general_one():
    result = classify(filename="x.pdf", content=PDF,
                      text_sample="Bill of quantities prepared against the technical specification")
    assert result.document_type == "BOQ"


def test_a_schedule_is_recognised_from_programme_wording():
    assert classify(filename="p.pdf", content=PDF,
                    text_sample="CONSTRUCTION PROGRAMME — Rev C").document_type == "SCHEDULE"


# --- Advisory, never authoritative -----------------------------------------

def test_disagreement_with_a_declared_type_is_reported_not_enforced():
    result = classify(filename="x.pdf", content=PDF, text_sample="BILL OF QUANTITIES",
                      declared_type="CONTRACT")
    assert result.document_type == "BOQ"
    assert result.declared_type == "CONTRACT"
    assert result.disagrees_with_declared is True


def test_agreeing_with_the_declared_type_is_not_a_disagreement():
    result = classify(filename="x.pdf", content=PDF, text_sample="BILL OF QUANTITIES",
                      declared_type="BOQ")
    assert result.disagrees_with_declared is False


def test_the_default_dropdown_value_is_not_treated_as_a_decision():
    # "OTHER" is what the form sends when nobody chose anything. Flagging a
    # disagreement with it would make the flag meaningless.
    result = classify(filename="x.pdf", content=PDF, text_sample="BILL OF QUANTITIES",
                      declared_type="OTHER")
    assert result.disagrees_with_declared is False


def test_the_classification_serialises_with_its_reasons_intact():
    payload = classify(filename="boq.pdf", content=PDF, text_sample="BILL OF QUANTITIES").as_json()
    assert payload["documentType"] == "BOQ"
    assert payload["evidence"] == "bill of quantities"
    assert payload["detectedFormat"] == "PDF"
    assert payload["source"] == "CONTENT"
