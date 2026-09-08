"""PDF: page count, text-layer presence, and a sample worth classifying on.

Reuses `pypdf`, which the RAG layer already depends on — no new dependency,
and no second opinion about what a page is. What it deliberately does **not**
do is chunk or embed: that is `services/rag/ingestion.py`, and duplicating it
here would produce two indexes that disagree.

The one judgement this processor makes is the scanned-PDF one. A PDF with
pages but no extractable characters is a photograph of a document: everything
downstream that promises to read it will silently return nothing. Reporting
that as PARTIAL with `NO_TEXT_LAYER` is the difference between a person
knowing their specification is not searchable and finding out when an answer
comes back empty.
"""

from __future__ import annotations

from app.core.config import settings
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import BaseProcessor, ProcessorContext, ProcessorOutcome
from app.services.ingestion.errors import EXTRACTION_FAILED, NO_TEXT_LAYER, ProcessingError

#: Pages read for the sample. The document's kind is announced on its cover or
#: in the first sheet's title block; reading further costs time on every upload
#: and adds nothing. Matches `file_intelligence.CLASSIFICATION_SAMPLE_PAGES`.
SAMPLE_PAGES = 3
#: Characters kept from the sample. Enough to classify on, small enough that a
#: JSONB column never becomes a text store by accident.
SAMPLE_CHARACTERS = 4000


class PDFProcessor(BaseProcessor):
    name = "pdf"
    categories = frozenset({FileCategory.PDF})
    extracts_text = True

    def extract(self, context: ProcessorContext) -> dict:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - pypdf is a hard requirement
            raise ProcessingError(EXTRACTION_FAILED, f"pypdf unavailable: {exc}") from exc

        try:
            with context.storage.local_path(context.file.storage_key) as path:
                reader = PdfReader(str(path))
                # A page count is cheap; reading every page's text on a
                # 300-page specification is not, and nothing here needs it.
                page_count = len(reader.pages)
                capped = min(page_count, settings.RAG_MAX_PAGES)
                sample_pages = reader.pages[:SAMPLE_PAGES]
                sample = "\n".join((page.extract_text() or "") for page in sample_pages)
                info = reader.metadata or {}
                title = str(info.get("/Title") or "").strip() or None
        except ProcessingError:
            raise
        except Exception as exc:
            # Any pypdf failure — encryption, a malformed xref, a truncated
            # upload — is one outcome. The specific library message is kept
            # for operators and never published.
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc

        return {
            "page_count": page_count,
            "indexable_pages": capped,
            "sample": sample,
            "title": title,
        }

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:
        sample = (raw.get("sample") or "").strip()
        return {
            "pageCount": raw.get("page_count"),
            "indexablePages": raw.get("indexable_pages"),
            "hasTextLayer": bool(sample),
            "textSampleCharacters": len(sample),
            "textSample": sample[:SAMPLE_CHARACTERS] or None,
            "embeddedTitle": raw.get("title"),
        }

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        self.validate(context)
        details = self.normalize(self.extract(context), context)
        envelope = self.envelope(
            context, details, extraction="TEXT" if details["hasTextLayer"] else "NONE",
        )
        if not details["hasTextLayer"]:
            return ProcessorOutcome.partial(
                NO_TEXT_LAYER, envelope,
                detail=f"{details['pageCount']} page(s), no extractable characters",
            )
        return ProcessorOutcome.ready(envelope)
