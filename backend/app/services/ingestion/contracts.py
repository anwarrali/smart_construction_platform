"""What a processor is, so that adding a file type is adding a class.

The alternative — and the thing this exists to prevent — is one `process_file`
function with a growing `if category == ...` chain. That function accumulates
every format's quirks in one place, its error handling drifts per branch, and
nobody can test one format without constructing the whole world.

A processor answers four questions about one category of file, in order:

    validate()   may this file be processed at all?
    extract()    what is in it? (raw, format-shaped)
    normalize()  what does that mean in the platform's vocabulary?
    process()    the three above, plus a settled outcome

`process()` has a default implementation on `BaseProcessor` that sequences the
other three, so a concrete processor usually implements `extract` and
`normalize` only. Overriding `process` is for the cases where the sequence
itself is wrong — the ZIP processor registers child files, which is neither
extraction nor normalization.

## Why the context carries a session

Two processors need to write rows: the ZIP processor creates children, and the
IFC adapter reads the version it mirrors. Passing the session explicitly rather
than opening one inside the processor is what keeps the whole run in a single
transaction, so a failure half-way through registering a package leaves no
half-registered package behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.models.ingestion import IngestedFile
from app.services.ingestion.categories import FileCategory
from app.services.ingestion.state import FAILED, OUTCOME_STATUSES, PARTIAL, READY
from app.services.private_storage import PrivateStorage


@dataclass(frozen=True)
class ProcessorContext:
    """Everything a processor may use, and nothing it may not.

    Notably absent: the request, the current user, and any filesystem path.
    A processor that could reach those would be able to make an authorization
    decision, and authorization is decided once at the API boundary — see
    `api/ingestion.py`. Storage is reached through the abstraction, so the same
    processor works unchanged against local disk or object storage.
    """

    db: Session
    file: IngestedFile
    storage: PrivateStorage
    #: How deep inside packages this file is. 0 for a direct upload. The ZIP
    #: processor refuses to expand beyond `INGESTION_ZIP_MAX_DEPTH`.
    depth: int = 0


@dataclass
class ProcessorOutcome:
    """How processing settled, and what it produced.

    `status` is restricted to the three terminal outcomes on purpose. A
    processor cannot leave a file in PROCESSING or send it back to QUEUED;
    the lifecycle belongs to the pipeline, and a processor that could drive it
    would be a second scheduler.
    """

    status: str
    metadata: dict = field(default_factory=dict)
    #: Set on PARTIAL and FAILED. A code from `services.ingestion.errors`.
    error_code: str | None = None
    #: Internal detail for operators. Never returned by the API.
    error_message: str | None = None
    #: Files registered as children of this one (ZIP members).
    children: list[IngestedFile] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in OUTCOME_STATUSES:
            raise ValueError(f"{self.status!r} is not a processor outcome")
        if self.status in {PARTIAL, FAILED} and not self.error_code:
            raise ValueError(f"a {self.status} outcome must carry an error code")

    @classmethod
    def ready(cls, metadata: dict | None = None) -> "ProcessorOutcome":
        return cls(status=READY, metadata=metadata or {})

    @classmethod
    def partial(cls, code: str, metadata: dict | None = None,
                detail: str | None = None) -> "ProcessorOutcome":
        """Completed, but delivered less than the declared capability.

        The reason is a first-class field rather than a note in the metadata,
        because "why is this only partly processed" is the question a person
        actually asks, and it must survive into the API response.
        """
        return cls(status=PARTIAL, metadata=metadata or {},
                   error_code=code, error_message=detail)

    @classmethod
    def failed(cls, code: str, detail: str | None = None,
               metadata: dict | None = None) -> "ProcessorOutcome":
        return cls(status=FAILED, metadata=metadata or {},
                   error_code=code, error_message=detail)


@runtime_checkable
class FileProcessor(Protocol):
    """The contract every processor satisfies."""

    #: Stable identifier recorded on the file row. Changing it makes past rows
    #: untraceable, so it is treated as an API.
    name: str
    #: Categories this processor claims. The registry refuses two processors
    #: claiming the same category, so dispatch is never ambiguous.
    categories: frozenset[FileCategory]

    def validate(self, context: ProcessorContext) -> None:
        """Refuse a file this processor must not touch. Raises IngestionRejected."""

    def extract(self, context: ProcessorContext) -> dict:
        """Pull raw, format-shaped facts out of the stored object."""

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:
        """Turn those facts into the platform's normalized metadata shape."""

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        """Run the whole thing and report how it settled."""


class BaseProcessor:
    """Sequencing, error discipline and the normalized envelope, once.

    Every processor's metadata carries the same outer keys — `processor`,
    `category`, `extraction` — so a consumer (the API, and later RAG 2.0) can
    read any file's metadata without knowing which processor produced it.
    Per-format detail lives under `details`.
    """

    name: str = "base"
    categories: frozenset[FileCategory] = frozenset()
    #: What this processor claims it can pull out. Written down so that
    #: "we store this and read nothing from it" is a visible statement rather
    #: than something a reader infers from missing code.
    extracts_text: bool = False

    def validate(self, context: ProcessorContext) -> None:  # noqa: D102
        return None

    def extract(self, context: ProcessorContext) -> dict:  # noqa: D102
        return {}

    def normalize(self, raw: dict, context: ProcessorContext) -> dict:  # noqa: D102
        return dict(raw)

    def envelope(self, context: ProcessorContext, details: dict, *,
                 extraction: str) -> dict:
        """The outer shape every processor's metadata shares.

        `extraction` says what was actually obtained: TEXT, METADATA, PACKAGE
        or NONE. A consumer can therefore ask "is there text behind this file"
        without a table of which processors produce text.
        """
        return {
            "processor": self.name,
            "category": context.file.file_category,
            "extraction": extraction,
            "details": details,
        }

    def process(self, context: ProcessorContext) -> ProcessorOutcome:
        self.validate(context)
        details = self.normalize(self.extract(context), context)
        return ProcessorOutcome.ready(
            self.envelope(context, details,
                          extraction="TEXT" if self.extracts_text else "METADATA")
        )
