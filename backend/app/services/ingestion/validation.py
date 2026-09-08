"""The gate. Every rule here already existed somewhere; none is relaxed.

`file_storage.save_private_upload` is the platform's upload gate: an
extension/MIME allowlist per category, a magic-byte check that the bytes are
what the extension claims, a size ceiling, and a filename sanitiser. The
unified pipeline uses **that function**, under a new `ingest` category, rather
than a parallel implementation — a second gate is a second thing to keep in
step, and the one that drifts is the one nobody is looking at.

What this module adds is the part `save_private_upload` cannot do, because it
operates on an `UploadFile` and package members are bytes in memory:

  * `validate_bytes` applies the same allowlist and the same signature check to
    an extracted archive member, so a `.exe` inside a design package is refused
    exactly as it would be at the front door;
  * `sanitize_filename` is the single definition of a safe leaf name;
  * `size_limit_for` names the ceiling in one place.

## Why the extension is still consulted at all

Because it must be. `.docx` and `.xlsx` are both ZIP archives and `.doc` and
`.xls` are both OLE2 — magic bytes cannot separate them, and no amount of
inspection will. The extension is therefore treated as a *claim that is checked
against the bytes*: it may break a tie between formats sharing a container
magic, and it may never override a signature that matched something else. That
is `file_intelligence.identify_format`'s rule, and this module does not invent
a looser one.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings
from app.services.file_intelligence import identify_format
from app.services.file_storage import EXTENSION_FORMATS, MAX_UPLOAD_BYTES, UPLOAD_RULES
from app.services.ingestion.errors import (
    CONTENT_MISMATCH, EMPTY_FILE, FILE_TOO_LARGE, UNSUPPORTED_FILE_TYPE, IngestionRejected,
)

#: The upload category the unified pipeline stores under. Its allowlist lives
#: in `file_storage.UPLOAD_RULES` beside every other category's, so the rules
#: for "what may be uploaded" stay in one readable table.
INGEST_CATEGORY = "ingest"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
#: Leading dots would produce hidden files and `..` sequences; collapsed rather
#: than stripped so a name never becomes empty by sanitisation alone.
_LEADING_DOTS = re.compile(r"^\.+")


def sanitize_filename(raw: str | None) -> str:
    """A safe leaf name: no directories, no traversal, no control characters.

    `Path(...).name` first, so `../../etc/passwd` becomes `passwd` before any
    character filtering — filtering alone would turn it into `.._.._etc_passwd`,
    which is safe but unreadable, and hides what was attempted.
    """
    leaf = Path((raw or "file").replace("\\", "/")).name
    cleaned = _UNSAFE.sub("_", leaf)
    cleaned = _LEADING_DOTS.sub("", cleaned)
    return (cleaned or "file")[:200]


def size_limit_for(category: str = INGEST_CATEGORY) -> int:
    """The byte ceiling for one upload category."""
    if category == "ifc":
        return settings.IFC_MAX_FILE_MB * 1024 * 1024
    if category == INGEST_CATEGORY:
        return settings.INGESTION_MAX_FILE_MB * 1024 * 1024
    return MAX_UPLOAD_BYTES


def accepted_extensions(category: str = INGEST_CATEGORY) -> list[str]:
    return sorted(UPLOAD_RULES.get(category, {}))


def validate_bytes(*, filename: str, payload: bytes,
                   category: str = INGEST_CATEGORY) -> str:
    """Apply the upload gate to bytes already in memory.

    Returns the detected format. Raises `IngestionRejected` with a code the API
    can publish and nothing an attacker can learn from.
    """
    if not payload:
        raise IngestionRejected(EMPTY_FILE, f"{filename!r} is empty")

    limit = size_limit_for(category)
    if len(payload) > limit:
        raise IngestionRejected(
            FILE_TOO_LARGE, f"{filename!r} is {len(payload)} bytes, over {limit}",
        )

    extension = Path(sanitize_filename(filename)).suffix.lower()
    rules = UPLOAD_RULES.get(category, {})
    if extension not in rules:
        raise IngestionRejected(
            UNSUPPORTED_FILE_TYPE, f"{extension or '(no extension)'} is not accepted",
        )

    # `.txt` has no signature — any byte sequence is arguably text — so it is
    # the one extension accepted on its name alone, exactly as the existing
    # upload gate already treats it.
    if extension == ".txt":
        return identify_format(payload[: 1024 * 1024], extension)

    allowed = EXTENSION_FORMATS.get(extension)
    detected = identify_format(payload[: 1024 * 1024], extension)
    if not allowed or detected not in allowed:
        raise IngestionRejected(
            CONTENT_MISMATCH,
            f"{filename!r} claims {extension} but its bytes are {detected}",
        )
    return detected
