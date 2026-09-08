"""The processors whose honest answer is "stored, and not read".

Four of them, and each exists so that a limitation has a name and a place
rather than being the absence of code:

  * **Drawings** (DWG/DXF) — DWG is a closed binary format needing a licensed
    SDK or an external converter; DXF is readable in principle and reading it
    usefully means understanding entities and layers, which is a drawing
    engine, not a line of code. Both are stored, classified as drawings, and
    reported PARTIAL with the reason.
  * **Images** — evidence, not text. Nothing is extracted and that is the
    complete, correct outcome, so this one settles READY.
  * **Plain text** — the bytes *are* the content, so a sample is taken.
  * **Everything else** — the fallback. A file that passed validation but has
    no processor is registered, stored and reported with `NO_PROCESSOR`, which
    is the "explicit outcome for an unsupported file" the pipeline promises
    instead of a silent nothing.
"""

from __future__ import annotations

from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import BaseProcessor, ProcessorContext, ProcessorOutcome
from app.services.ingestion.errors import (
    EXTRACTION_FAILED, FORMAT_NOT_PARSED, NO_PROCESSOR, ProcessingError,
)

SAMPLE_CHARACTERS = 4000
#: How much of a text file is read for the sample. A CSV export of a schedule
#: can be tens of megabytes and none of it after the first pages changes what
#: the file is.
TEXT_READ_BYTES = 256 * 1024


class DrawingProcessor(BaseProcessor):
    name = "drawing"
    categories = frozenset({FileCategory.DRAWING})
    extracts_text = False

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        details = {
            "limitation": (
                "Drawings are stored and downloadable; no geometry, layer or "
                "annotation data is extracted. DWG is a closed binary format "
                "requiring a licensed SDK or an external converter."
            ),
            "nextStep": (
                "DXF is the cheaper first step if drawing extraction becomes "
                "necessary; it is text-based and documented."
            ),
        }
        return ProcessorOutcome.partial(
            FORMAT_NOT_PARSED,
            self.envelope(context, details, extraction="NONE"),
            detail="drawing formats are not parsed",
        )


class ImageProcessor(BaseProcessor):
    name = "image"
    categories = frozenset({FileCategory.IMAGE})
    extracts_text = False

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        # READY rather than PARTIAL, and the distinction is not pedantic: this
        # processor declares no text capability, so it delivered everything it
        # claims. PARTIAL would push people to retry something already complete.
        details = {
            "limitation": (
                "Images are evidence. No vision extraction or OCR is implemented."
            ),
        }
        return ProcessorOutcome.ready(
            self.envelope(context, details, extraction="NONE")
        )


class TextProcessor(BaseProcessor):
    name = "text"
    categories = frozenset({FileCategory.TEXT})
    extracts_text = True

    def extract(self, context: ProcessorContext) -> dict:
        try:
            handle = context.storage.open(context.file.storage_key)
        except (OSError, ValueError) as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc
        try:
            with handle:
                payload = handle.read(TEXT_READ_BYTES)
        except OSError as exc:
            raise ProcessingError(EXTRACTION_FAILED, f"{type(exc).__name__}: {exc}") from exc
        return {"text": payload.decode("utf-8", errors="replace")}

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:
        text = (raw.get("text") or "").strip()
        return {
            "textCharacters": len(text),
            "textSample": text[:SAMPLE_CHARACTERS] or None,
            "truncated": context.file.file_size_bytes > TEXT_READ_BYTES,
        }


class PassthroughProcessor(BaseProcessor):
    """The fallback. Accepted, stored, and explicitly not understood."""

    name = "passthrough"
    categories = frozenset({FileCategory.OTHER})
    extracts_text = False

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        details = {
            "limitation": (
                "No processor claims this file category. The file is stored, "
                "downloadable and classified; nothing was extracted from it."
            ),
            "detectedFormat": context.file.detected_format,
        }
        return ProcessorOutcome.partial(
            NO_PROCESSOR,
            self.envelope(context, details, extraction="NONE"),
            detail=f"no processor for category {context.file.file_category}",
        )
