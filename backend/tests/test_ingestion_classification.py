"""Classification and validation, pinned without a database.

These are the rules everything else in the pipeline is built on: what a file
*is*, and whether it may be accepted at all. They are tested in isolation from
storage, sessions and HTTP so that a failure here points at the rule rather
than at the wiring around it — `test_ingestion_pipeline.py` covers the wiring.

The security assertions in this file are the important ones. Every "unsupported
type" and "content does not match its name" test corresponds to a way the
platform could be persuaded to store something it does not think it is storing.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.ingestion.categories import FileCategory, classify_file
from app.services.ingestion.errors import (
    CONTENT_MISMATCH, EMPTY_FILE, FILE_TOO_LARGE, UNSUPPORTED_FILE_TYPE, IngestionRejected,
)
from app.services.ingestion.validation import (
    accepted_extensions, sanitize_filename, size_limit_for, validate_bytes,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
ZIP = b"PK\x03\x04" + b"\x00" * 32
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
DWG = b"AC1027" + b"\x00" * 32
IFC = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


# --- Category from evidence -------------------------------------------------

@pytest.mark.parametrize(
    "filename,head,expected",
    [
        ("spec.pdf", PDF, FileCategory.PDF),
        ("tower.ifc", IFC, FileCategory.IFC),
        ("method-statement.docx", ZIP, FileCategory.DOCX),
        ("boq.xlsx", ZIP, FileCategory.XLSX),
        ("legacy.doc", OLE2, FileCategory.DOC),
        ("legacy.xls", OLE2, FileCategory.XLS),
        ("plan.dwg", DWG, FileCategory.DRAWING),
        ("photo.png", PNG, FileCategory.IMAGE),
        ("package.zip", ZIP, FileCategory.ZIP_PACKAGE),
        ("notes.txt", b"just some words", FileCategory.TEXT),
    ],
)
def test_every_supported_kind_lands_in_its_own_category(filename, head, expected):
    assert classify_file(filename=filename, head=head).category is expected


def test_a_zip_named_as_an_office_document_is_never_walked_as_a_package():
    """The distinction that keeps the archive walker away from a .docx.

    Both are `PK\\x03\\x04`. If a .docx resolved to ZIP_PACKAGE, every Word
    document would be expanded into its XML parts as separate project files.
    """
    for name, expected in (("a.docx", FileCategory.DOCX), ("b.xlsx", FileCategory.XLSX)):
        assert classify_file(filename=name, head=ZIP).category is expected


def test_the_bytes_beat_the_extension_when_they_disagree():
    """A PDF called `.xlsx` is a PDF, and the disagreement is recorded."""
    result = classify_file(filename="quantities.xlsx", head=PDF)
    assert result.category is FileCategory.PDF
    assert result.detected_format == "PDF"
    assert result.extension_mismatch is True
    assert result.classification_json["extensionMismatch"] is True


def test_an_unrecognisable_file_is_OTHER_rather_than_a_guess():
    result = classify_file(filename="mystery.bin", head=b"\x00\x01\x02\x03\xff\xfe")
    assert result.category is FileCategory.OTHER
    assert result.is_supported is False


def test_an_empty_file_is_reported_as_empty_not_as_text():
    assert classify_file(filename="x.pdf", head=b"").detected_format == "EMPTY"


def test_classification_carries_the_evidence_it_decided_on():
    result = classify_file(
        filename="scan.pdf", head=PDF, text_sample="BILL OF QUANTITIES\nItem 1",
    )
    assert result.document_kind == "BOQ"
    assert result.classification_json["documentKind"]["source"] == "CONTENT"
    assert result.classification_json["documentKind"]["evidence"] == "bill of quantities"
    assert result.classification_json["categorySource"] == "FORMAT"


def test_a_drawing_format_implies_a_drawing_kind_whatever_it_is_named():
    result = classify_file(filename="untitled-3.dwg", head=DWG)
    assert result.category is FileCategory.DRAWING
    assert result.document_kind == "DRAWING"


# --- The gate ---------------------------------------------------------------

def test_the_accepted_list_covers_what_a_design_delivery_actually_contains():
    accepted = set(accepted_extensions())
    assert {".pdf", ".docx", ".xlsx", ".dwg", ".dxf", ".ifc", ".zip"} <= accepted


def test_an_executable_is_refused_however_it_is_labelled():
    with pytest.raises(IngestionRejected) as refusal:
        validate_bytes(filename="setup.exe", payload=b"MZ\x90\x00" + b"\x00" * 64)
    assert refusal.value.code == UNSUPPORTED_FILE_TYPE


def test_a_file_with_no_extension_is_refused():
    with pytest.raises(IngestionRejected) as refusal:
        validate_bytes(filename="README", payload=b"text")
    assert refusal.value.code == UNSUPPORTED_FILE_TYPE


def test_renaming_an_executable_to_pdf_does_not_get_it_in():
    """MIME/extension spoofing. The magic bytes are the authority."""
    with pytest.raises(IngestionRejected) as refusal:
        validate_bytes(filename="invoice.pdf", payload=b"MZ\x90\x00" + b"\x00" * 64)
    assert refusal.value.code == CONTENT_MISMATCH


def test_an_empty_payload_is_refused_before_anything_else():
    with pytest.raises(IngestionRejected) as refusal:
        validate_bytes(filename="a.pdf", payload=b"")
    assert refusal.value.code == EMPTY_FILE


def test_the_size_ceiling_is_enforced_on_bytes_in_memory(monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_MAX_FILE_MB", 1)
    with pytest.raises(IngestionRejected) as refusal:
        validate_bytes(filename="big.pdf", payload=PDF + b"\x00" * (2 * 1024 * 1024))
    assert refusal.value.code == FILE_TOO_LARGE


def test_the_size_ceiling_follows_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "INGESTION_MAX_FILE_MB", 7)
    assert size_limit_for() == 7 * 1024 * 1024


def test_a_text_file_is_accepted_on_its_name_because_it_has_no_signature():
    """The one documented exception, unchanged from the existing upload gate."""
    assert validate_bytes(filename="site-notes.txt", payload=b"anything at all") == "TEXT"


def test_an_ascii_dxf_is_accepted_and_a_disguised_binary_is_not():
    assert validate_bytes(filename="plan.dxf", payload=b"0\nSECTION\n2\nHEADER\n") == "TEXT"
    with pytest.raises(IngestionRejected):
        validate_bytes(filename="plan.dxf", payload=PNG)


# --- Filenames --------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("/absolute/path/plan.pdf", "plan.pdf"),
        ("....//spec.pdf", "spec.pdf"),
        (".hidden", "hidden"),
        ("عربي.pdf", "____.pdf"),
        ("a b;c|d.pdf", "a_b_c_d.pdf"),
        (None, "file"),
        ("", "file"),
    ],
)
def test_a_filename_can_never_become_a_path(raw, expected):
    assert sanitize_filename(raw) == expected


def test_a_sanitised_name_is_never_empty():
    """An empty name would produce a storage key ending in a separator."""
    for raw in ("...", "///", "\\\\"):
        assert sanitize_filename(raw)


def test_a_very_long_name_is_bounded():
    assert len(sanitize_filename("x" * 5000)) <= 200
