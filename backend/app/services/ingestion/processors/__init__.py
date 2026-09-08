"""Every processor the platform has, and the registry that wires them.

Adding a file type is: write the class, add one line here. Nothing else in the
pipeline changes — which is the property the registry exists to provide, and
the reason there is no `if category == ...` anywhere in `pipeline.py`.

`build_registry()` returns a fresh registry rather than mutating a module-level
one. That matters for tests: a suite that swaps in a fake processor gets its
own registry instead of leaving a global mutated for whatever runs next.
"""

from __future__ import annotations

from app.services.ingestion.processors.ifc import IFCProcessor
from app.services.ingestion.processors.misc import (
    DrawingProcessor, ImageProcessor, PassthroughProcessor, TextProcessor,
)
from app.services.ingestion.processors.office import (
    DocxProcessor, LegacyOfficeProcessor, XlsxProcessor,
)
from app.services.ingestion.processors.pdf import PDFProcessor
from app.services.ingestion.processors.zip_package import ZipPackageProcessor
from app.services.ingestion.registry import ProcessorRegistry

#: The classes, in one list, so "what can this platform ingest?" is answered by
#: reading eight lines rather than by grepping for a base class.
PROCESSOR_CLASSES = (
    IFCProcessor,
    PDFProcessor,
    DocxProcessor,
    XlsxProcessor,
    LegacyOfficeProcessor,
    DrawingProcessor,
    ImageProcessor,
    TextProcessor,
    ZipPackageProcessor,
)


def build_registry() -> ProcessorRegistry:
    registry = ProcessorRegistry()
    for factory in PROCESSOR_CLASSES:
        registry.register(factory())
    # The fallback is registered for OTHER *and* as the fallback: the first
    # makes it the declared handler for unclassifiable files, the second
    # catches a category added to the enum but not yet to this list.
    passthrough = PassthroughProcessor()
    registry.register(passthrough)
    registry.register_fallback(passthrough)
    return registry


__all__ = ["PROCESSOR_CLASSES", "build_registry"]
