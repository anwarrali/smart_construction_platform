"""Ingestion failure codes, and the two audiences they serve.

Every failure has a machine-readable code that is safe to publish and a
human sentence that says what to do about it. Neither ever carries the
internal detail — a stack frame, a storage path, a library message — because
that detail is what turns an error response into reconnaissance.

The internal message is still recorded, on the row, for whoever is debugging.
`public_error(...)` is what an API response is built from; `IngestedFile.
error_message` is what an operator reads. Same discipline as
`ifc_policy.friendly_ifc_error`, which this deliberately resembles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionErrorInfo:
    title: str
    description: str
    retryable: bool
    action: str


UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
EMPTY_FILE = "EMPTY_FILE"
CONTENT_MISMATCH = "CONTENT_MISMATCH"
ARCHIVE_UNSAFE_ENTRY = "ARCHIVE_UNSAFE_ENTRY"
ARCHIVE_TOO_MANY_ENTRIES = "ARCHIVE_TOO_MANY_ENTRIES"
ARCHIVE_EXPANSION_LIMIT = "ARCHIVE_EXPANSION_LIMIT"
ARCHIVE_CORRUPTED = "ARCHIVE_CORRUPTED"
ARCHIVE_NESTING_LIMIT = "ARCHIVE_NESTING_LIMIT"
NO_PROCESSOR = "NO_PROCESSOR"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
NO_TEXT_LAYER = "NO_TEXT_LAYER"
FORMAT_NOT_PARSED = "FORMAT_NOT_PARSED"
STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
PROCESSING_FAILED = "PROCESSING_FAILED"

ERRORS: dict[str, IngestionErrorInfo] = {
    UNSUPPORTED_FILE_TYPE: IngestionErrorInfo(
        "This file type is not accepted",
        "The platform does not ingest this kind of file yet.",
        False, "Upload a supported document, drawing, model or package"),
    FILE_TOO_LARGE: IngestionErrorInfo(
        "File is too large",
        "The upload exceeds the configured size limit for this project.",
        False, "Split the file or upload a smaller export"),
    EMPTY_FILE: IngestionErrorInfo(
        "File is empty", "Nothing was received.", True, "Check the file and upload it again"),
    CONTENT_MISMATCH: IngestionErrorInfo(
        "File content does not match its name",
        "The bytes are not the format the file extension claims.",
        False, "Rename the file to match its real format, or re-export it"),
    ARCHIVE_UNSAFE_ENTRY: IngestionErrorInfo(
        "Package contains an unsafe entry",
        "An entry in the archive points outside the package.",
        False, "Rebuild the archive with relative paths only"),
    ARCHIVE_TOO_MANY_ENTRIES: IngestionErrorInfo(
        "Package contains too many files",
        "The archive exceeds the configured entry limit.",
        False, "Split the package into smaller deliveries"),
    ARCHIVE_EXPANSION_LIMIT: IngestionErrorInfo(
        "Package expands to more than is allowed",
        "The archive's uncompressed contents exceed the configured limit.",
        False, "Split the package into smaller deliveries"),
    ARCHIVE_CORRUPTED: IngestionErrorInfo(
        "Package could not be read",
        "The archive is damaged or is not a readable ZIP file.",
        True, "Rebuild the archive and upload it again"),
    ARCHIVE_NESTING_LIMIT: IngestionErrorInfo(
        "Package is nested too deeply",
        "Archives inside archives are stored but not expanded.",
        False, "Upload the inner package on its own"),
    NO_PROCESSOR: IngestionErrorInfo(
        "Nothing is extracted from this file yet",
        "The file is stored and downloadable; no processor reads this format.",
        False, "No action needed"),
    EXTRACTION_FAILED: IngestionErrorInfo(
        "Content could not be extracted",
        "The file was stored, but reading its contents did not succeed.",
        True, "Retry processing, or re-export the file"),
    NO_TEXT_LAYER: IngestionErrorInfo(
        "No readable text in this document",
        "The pages carry no text layer, which usually means a scan.",
        False, "Upload a text PDF if the contents need to be searchable"),
    FORMAT_NOT_PARSED: IngestionErrorInfo(
        "This format is stored but not parsed",
        "The file is kept and downloadable; deep reading is not implemented for it.",
        False, "No action needed"),
    STORAGE_UNAVAILABLE: IngestionErrorInfo(
        "The stored file is unavailable",
        "The object could not be read back from storage.",
        True, "Upload the file again"),
    PROCESSING_FAILED: IngestionErrorInfo(
        "Processing did not complete",
        "The file is unchanged. Processing stopped before it finished.",
        True, "Retry processing, then contact support"),
}


def public_error(code: str | None) -> dict | None:
    """The publishable shape of a failure, or None when there is no failure."""
    if not code:
        return None
    info = ERRORS.get(code) or IngestionErrorInfo(
        "Ingestion failed", "The file could not be processed safely.",
        True, "Try again")
    return {
        "code": code,
        "title": info.title,
        "description": info.description,
        "retryable": info.retryable,
        "suggestedAction": info.action,
    }


class IngestionRejected(Exception):
    """Validation refused the file. Nothing has been stored that must persist."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(detail or code)


class ProcessingError(Exception):
    """A processor could not finish. Recorded against the file as FAILED."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail
        super().__init__(detail or code)
