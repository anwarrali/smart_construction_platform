"""Getting indexable text out of an `IngestedFile`, without a second extractor.

The unified ingestion pipeline already read every one of these files once and
recorded what it found. Two things follow, and they pull in opposite
directions:

**The decision is free.** `metadata_json.extraction` already says whether the
file yielded text. Reopening a 300-page specification to rediscover that it is
a scan is work the pipeline has already done and paid for, so `is_indexable`
answers from the record and never touches storage.

**The content is not.** The pipeline stores a ~4 KB *sample*, deliberately —
`metadata_json` is a metadata column, not a text store. So the full text does
have to be read again for chunking. That is not the same as re-deciding
whether it exists.

## Why this delegates to the processors

Each format's extraction already lives in
`services/ingestion/processors/`, complete with its archive guards, its size
ceilings and its error handling. Reimplementing DOCX text extraction here
would produce a second answer to "what does this Word file say", and the two
would drift the first time one of them was fixed. So this module calls the
same processor the pipeline used, and only adds what RAG needs on top:
`PageText`, in order, with page numbers that can be cited.

## Pages, for formats that have none

A PDF has real pages and they are used. A Word document or a text file does
not have pages until something renders it, so its text becomes a single page 1.
That is truthful rather than convenient: `DocumentChunk.page_number` is NOT
NULL because an uncitable chunk is useless, and "page 1" is exactly where a
reader opening that file would find the passage.
"""

from __future__ import annotations

from app.models.ingestion import IngestedFile
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import ProcessorContext
from app.services.ingestion.errors import ProcessingError
from app.services.private_storage import private_storage
from app.services.rag.pdf_text import DocumentTextError, PageText, extract_pages

#: The one value of `metadata_json.extraction` that means "there is text here".
#: The others — METADATA, PACKAGE, MODEL, NONE — all mean there is not.
EXTRACTION_TEXT = "TEXT"

#: Formats whose text this module knows how to read back in full. A file may
#: report `extraction == "TEXT"` and still not be here if a future processor
#: starts producing text for a format RAG has no reader for; refusing loudly
#: is better than indexing an empty string.
SUPPORTED_CATEGORIES = frozenset({
    FileCategory.PDF, FileCategory.DOCX, FileCategory.TEXT,
})


def extraction_kind(file: IngestedFile) -> str | None:
    """What the ingestion pipeline says it obtained from this file."""
    metadata = file.metadata_json or {}
    value = metadata.get("extraction")
    return str(value) if value else None


def is_indexable(file: IngestedFile) -> bool:
    """Can this file be indexed at all — answered without opening it.

    Both conditions matter. The extraction verdict is the pipeline's, and the
    category check is this module's: they disagree only when a processor is
    changed without a reader being added here, and that is a bug worth
    surfacing rather than silently indexing nothing.
    """
    if extraction_kind(file) != EXTRACTION_TEXT:
        return False
    try:
        return FileCategory(file.file_category) in SUPPORTED_CATEGORIES
    except ValueError:
        # A category this build of the code does not know. Rows outlive code.
        return False


def why_not_indexable(file: IngestedFile) -> str:
    """A sentence a person can act on, for a file that cannot be indexed.

    Phrased from what the pipeline recorded rather than from a lookup table,
    so the answer stays true when a processor's capability changes.
    """
    kind = extraction_kind(file)
    if kind is None:
        return (
            "This file has not finished processing yet, so there is nothing to index. "
            "Wait for processing to complete, then try again."
        )
    if kind != EXTRACTION_TEXT:
        limitation = ((file.metadata_json or {}).get("details") or {}).get("limitation")
        base = (
            f"No readable text was extracted from this file "
            f"({file.file_category.lower()}), so it cannot be indexed."
        )
        return f"{base} {limitation}"[:500] if limitation else base
    return (
        f"Text was extracted from this file, but indexing {file.file_category} "
        "files is not supported yet."
    )


def _context(db, file: IngestedFile) -> ProcessorContext:
    return ProcessorContext(db=db, file=file, storage=private_storage, depth=0)


def _pdf_pages(db, file: IngestedFile) -> list[PageText]:
    """Real pages, through the same extractor the Document path uses.

    `extract_pages` takes a filesystem path, so the object is materialised
    through the storage abstraction rather than by joining `PRIVATE_UPLOAD_DIR`
    to a key — which would work today and break the moment storage moves to
    S3/R2, exactly as `private_storage` documents.
    """
    with private_storage.local_path(file.storage_key) as path:
        if not path.is_file():
            raise DocumentTextError("The stored file is missing from storage")
        return extract_pages(path)


def _single_page(text: str) -> list[PageText]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise DocumentTextError(
            "The file contained no readable text when it was read back for indexing"
        )
    return [PageText(page_number=1, text=cleaned)]


def _processor_text(db, file: IngestedFile, processor) -> list[PageText]:
    """Full text from a processor's own `extract`, as one page.

    Any processor failure becomes a `DocumentTextError`, because that is the
    exception the indexing state machine knows how to persist as a readable
    `index_error`. The processor's internal detail is kept in the message for
    an operator and is not published — see `services/ingestion/errors.py`.
    """
    try:
        raw = processor.extract(_context(db, file))
    except ProcessingError as error:
        raise DocumentTextError(
            f"The file could not be read for indexing ({error.code})"
        ) from error
    except Exception as error:  # pragma: no cover - defensive
        raise DocumentTextError(f"The file could not be read for indexing: {error}") from error
    return _single_page(raw.get("text", ""))


def pages_for(db, file: IngestedFile) -> list[PageText]:
    """Every page of indexable text, in order.

    Raises `DocumentTextError` — the same exception the Document path raises —
    so the indexing state machine handles both sources identically.
    """
    if not is_indexable(file):
        raise DocumentTextError(why_not_indexable(file))

    category = FileCategory(file.file_category)
    if category is FileCategory.PDF:
        return _pdf_pages(db, file)

    # Imported here rather than at module scope: `processors/__init__` builds
    # the whole registry, and RAG has no reason to pull that in unless it is
    # actually reading one of these formats.
    if category is FileCategory.DOCX:
        from app.services.ingestion.processors.office import DocxProcessor

        return _processor_text(db, file, DocxProcessor())

    from app.services.ingestion.processors.misc import TextProcessor

    return _processor_text(db, file, TextProcessor())
