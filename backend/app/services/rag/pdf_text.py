"""Getting text out of a stored PDF, one page at a time.

Page-at-a-time is the whole point. If pages were concatenated before chunking,
every citation would be a guess, and a system that cites the wrong page is
worse than one that cites nothing — it is confidently wrong about where a
contract clause lives.

This module also owns the awkward part: `documents.file_url` is an absolute
URL (`{BACKEND_URL}/uploads/<relative>`), not a path, because `save_upload`
builds it for browsers. Turning it back into a file on disk is done here,
once, with a traversal guard — rather than with string surgery at each call
site, where the guard would eventually be omitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import settings


class DocumentTextError(Exception):
    """The document cannot be turned into indexable text.

    Carries a message meant for the user, because every one of these lands in
    `documents.index_error` and is shown in the status endpoint. "PDF has no
    extractable text layer" tells someone what to do next; a stack trace does
    not.
    """


@dataclass(frozen=True)
class PageText:
    page_number: int  #: 1-based, as a reader would count
    text: str


def resolve_upload_path(file_url: str) -> Path:
    """Map a stored `file_url` back to a path inside UPLOAD_DIR.

    Rejects anything that escapes the upload directory. The input is
    database-held and was produced by our own uploader, but a path traversal
    guard that only runs on untrusted input is one refactor away from not
    running at all.
    """
    path_part = urlparse(file_url).path if "://" in file_url else file_url
    path_part = unquote(path_part)

    marker = "/uploads/"
    if marker in path_part:
        relative = path_part.split(marker, 1)[1]
    else:
        relative = path_part.lstrip("/")
    if not relative:
        raise DocumentTextError("The stored file location is empty or malformed")

    root = Path(settings.UPLOAD_DIR).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise DocumentTextError("The stored file location is outside the upload directory")
    return candidate


def assert_indexable(path: Path) -> int:
    """Check the file exists, is a real PDF, and is within the size limit.

    Returns its size in bytes. The magic-byte check matters more than the
    extension: `mime_type` is client-supplied at upload, and a file named
    `.pdf` that is actually a ZIP would otherwise reach pypdf and fail with
    something unreadable.
    """
    if not path.is_file():
        raise DocumentTextError("The document file is missing from storage")

    size = path.stat().st_size
    limit = settings.RAG_MAX_FILE_MB * 1024 * 1024
    if size > limit:
        raise DocumentTextError(
            f"The document is {size / 1024 / 1024:.1f} MB, above the "
            f"{settings.RAG_MAX_FILE_MB} MB indexing limit"
        )
    if size == 0:
        raise DocumentTextError("The document file is empty")

    with path.open("rb") as handle:
        if not handle.read(5).startswith(b"%PDF-"):
            raise DocumentTextError("Only PDF documents can be indexed")
    return size


def extract_pages(path: Path) -> list[PageText]:
    """Every page's text, in order, with blank pages dropped.

    Blank pages are dropped rather than kept as empty chunks: a scanned page
    with no text layer yields "", and indexing it would produce a chunk that
    can be retrieved but says nothing.
    """
    # Imported lazily so the application starts, and every non-RAG test runs,
    # without pypdf installed. RAG is optional; its dependency should be too.
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:  # pragma: no cover - only in a build without pypdf
        raise DocumentTextError("PDF support is not installed on this server")

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            # An empty-password decrypt covers PDFs that are "encrypted" only
            # to set permissions, which is common for issued drawings.
            try:
                reader.decrypt("")
            except Exception:
                raise DocumentTextError("The document is password protected")
        total_pages = len(reader.pages)
    except DocumentTextError:
        raise
    except (PdfReadError, Exception) as error:
        raise DocumentTextError(f"The document could not be read as a PDF: {error}")

    if total_pages > settings.RAG_MAX_PAGES:
        raise DocumentTextError(
            f"The document has {total_pages} pages, above the "
            f"{settings.RAG_MAX_PAGES} page indexing limit"
        )

    pages: list[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # One unreadable page must not lose the other 200.
            text = ""
        text = text.strip()
        if text:
            pages.append(PageText(page_number=index, text=text))

    if not pages:
        # The single most likely real-world failure, and the one where a vague
        # message wastes the most time. OCR is explicitly out of scope for the
        # MVP, so say so instead of letting someone retry forever.
        raise DocumentTextError(
            "This PDF has no extractable text layer — it is probably a scan. "
            "OCR is not supported yet."
        )
    return pages
