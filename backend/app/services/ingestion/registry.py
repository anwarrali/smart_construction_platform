"""Which processor handles which category, decided once.

The registry is a mapping, not a chain of `isinstance` checks, and it refuses
a second processor for a category that already has one. That refusal is the
whole point: two handlers for `.pdf` is not a merge conflict anybody notices,
and the one that happens to be registered first silently wins. Failing at
import time turns that into a five-second fix.

A category with no processor is not an error. `OTHER` and the formats nothing
reads yet resolve to the passthrough processor, which stores the file, records
that nothing was extracted and why, and settles as READY. "We accept this and
extract nothing" is a supported outcome, stated out loud.
"""

from __future__ import annotations

from app.services.ingestion.categories import FileCategory
from app.services.ingestion.contracts import FileProcessor


class ProcessorRegistry:
    def __init__(self) -> None:
        self._by_category: dict[FileCategory, FileProcessor] = {}
        self._fallback: FileProcessor | None = None

    def register(self, processor: FileProcessor) -> FileProcessor:
        for category in processor.categories:
            existing = self._by_category.get(category)
            if existing is not None and existing is not processor:
                raise ValueError(
                    f"{category.value} is already handled by {existing.name!r}; "
                    f"{processor.name!r} cannot also claim it"
                )
            self._by_category[category] = processor
        return processor

    def register_fallback(self, processor: FileProcessor) -> FileProcessor:
        self._fallback = processor
        return processor

    def for_category(self, category: FileCategory) -> FileProcessor:
        processor = self._by_category.get(category)
        if processor is not None:
            return processor
        if self._fallback is None:  # pragma: no cover - the default registry sets one
            raise LookupError(f"No processor for {category.value} and no fallback")
        return self._fallback

    def select(self, file) -> FileProcessor:
        """The processor for a stored file row.

        A category string the enum no longer knows about resolves to the
        fallback rather than raising. Rows outlive code: a category retired in
        a later release must still be listable, not a 500 on the file list.
        """
        try:
            category = FileCategory(file.file_category)
        except ValueError:
            return self.for_category(FileCategory.OTHER)
        return self.for_category(category)

    @property
    def categories(self) -> frozenset[FileCategory]:
        return frozenset(self._by_category)
