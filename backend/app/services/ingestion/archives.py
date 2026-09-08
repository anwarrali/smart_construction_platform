"""Reading a ZIP that somebody else built, without trusting any of it.

A design package is the most hostile input this platform accepts: an
authenticated user hands the server an arbitrary archive and asks it to open
every entry. Four distinct attacks live in that sentence, and each is refused
here by a *specific* check rather than by a general hope that `zipfile` is
careful.

**Path traversal.** An entry named `../../etc/cron.d/x` or `C:\\Windows\\x`
writes outside the extraction root. `zipfile.extractall` sanitises names, but
this module never calls it — entries are read as streams and written under
keys the platform generates itself, so the archive's names are used only as
*labels*. `safe_entry_name` still rejects them outright, because a package
containing such an entry is malicious whatever the writer does with it, and
finding out at ingest time is better than finding out later.

**Zip bombs.** A 42 KB archive can declare petabytes of content. Three
independent ceilings apply: total uncompressed size, per-entry uncompressed
size, and per-entry compression ratio. The declared sizes in the central
directory are checked *first* so a bomb is refused before a byte is read, and
the actual read is then bounded as well — because the declared size is
attacker-controlled too, and a header that lies low is the obvious next move.

**Entry-count exhaustion.** Ten million one-byte entries cost nothing to
compress and a great deal to register. Capped by count.

**Nesting.** An archive inside an archive is stored as a file and never
expanded. Recursive expansion is where a bounded check becomes an unbounded
one, and no evidence yet says construction packages need it.

Nothing here writes to disk or to storage. This module answers "what is safely
in this archive, and may I read it?"; `processors.zip_package` decides what to
do with the answer.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from app.core.config import settings
from app.services.ingestion.errors import (
    ARCHIVE_CORRUPTED, ARCHIVE_EXPANSION_LIMIT, ARCHIVE_TOO_MANY_ENTRIES,
    ARCHIVE_UNSAFE_ENTRY, IngestionRejected,
)

#: The high 16 bits of `external_attr` carry the Unix mode. 0o120000 is
#: S_IFLNK: a symlink entry, whose "content" is a path to follow. Refused —
#: a link is a way to make the reader open something the archive does not
#: contain.
_SYMLINK_MODE = 0o120000

#: Bytes per read while streaming one entry out of the archive.
READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class ArchiveEntry:
    """One file the archive holds, after it has been judged safe."""

    #: The archive's own name for it, sanitised for display. Never used as a
    #: filesystem path.
    name: str
    #: The leaf name, which is what a classifier reads an extension from.
    filename: str
    #: The directory path inside the package, or "" at the root. Display only.
    directory: str
    declared_size: int
    compressed_size: int

    @property
    def compression_ratio(self) -> float:
        if self.compressed_size <= 0:
            # A stored (uncompressed) entry cannot be a bomb by ratio; the
            # absolute size ceilings still apply to it.
            return 1.0
        return self.declared_size / self.compressed_size


@dataclass(frozen=True)
class ArchiveInspection:
    entries: tuple[ArchiveEntry, ...]
    #: Entries deliberately not offered for registration, with the reason.
    #: Skipping is not silence: this is written to the package's metadata so a
    #: person can see exactly what was left out and why.
    skipped: tuple[dict, ...]
    total_declared_size: int


def _is_unsafe_name(raw: str) -> str | None:
    """Why this entry name may not be trusted, or None when it is fine."""
    if not raw or raw.endswith("/"):
        return None  # directories carry no content; the caller filters them
    if "\x00" in raw:
        return "null byte in entry name"
    # Windows-built archives legitimately use backslashes, so both separators
    # are examined. Anything absolute, drive-qualified or containing a parent
    # reference is refused rather than normalised: normalising an attack into
    # something harmless hides that it was attempted.
    normalised = raw.replace("\\", "/")
    if normalised.startswith("/"):
        return "absolute path"
    if PureWindowsPath(raw).drive or PureWindowsPath(raw).is_absolute():
        return "absolute path"
    parts = PurePosixPath(normalised).parts
    if any(part == ".." for part in parts):
        return "parent directory traversal"
    return None


#: A leading `./`, as some archivers write. Stripped as a *prefix*, repeatedly
#: — not with `lstrip("./")`, which removes any run of dots and slashes and so
#: silently renames `.DS_Store` to `DS_Store`, defeating the very check that is
#: supposed to skip it.
_CURRENT_DIR_PREFIX = re.compile(r"^(?:\./)+")


def safe_entry_name(raw: str) -> str:
    """The display name for an entry, or raise if the entry is hostile."""
    reason = _is_unsafe_name(raw)
    if reason:
        raise IngestionRejected(ARCHIVE_UNSAFE_ENTRY, f"{raw!r}: {reason}")
    return _CURRENT_DIR_PREFIX.sub("", raw.replace("\\", "/"))


def inspect(archive: zipfile.ZipFile) -> ArchiveInspection:
    """Judge every entry, and refuse the archive if any of it is dangerous.

    The distinction between *refusing the archive* and *skipping an entry* is
    deliberate:

      * A traversal entry, a symlink or a declared expansion over the limit
        condemns the whole package. These are not accidents, and accepting the
        rest of an archive that contained one would be treating an attack as a
        formatting quirk.
      * A directory, a macOS resource fork, or an entry that is simply empty is
        skipped and recorded. These are ordinary noise in real packages.
    """
    max_entries = settings.INGESTION_ZIP_MAX_ENTRIES
    max_total = settings.INGESTION_ZIP_MAX_TOTAL_MB * 1024 * 1024
    max_entry = settings.INGESTION_ZIP_MAX_ENTRY_MB * 1024 * 1024
    max_ratio = settings.INGESTION_ZIP_MAX_RATIO

    infos = archive.infolist()
    if len(infos) > max_entries:
        raise IngestionRejected(
            ARCHIVE_TOO_MANY_ENTRIES,
            f"{len(infos)} entries exceeds the limit of {max_entries}",
        )

    entries: list[ArchiveEntry] = []
    skipped: list[dict] = []
    total = 0

    for info in infos:
        name = safe_entry_name(info.filename)

        if info.is_dir():
            continue
        if (info.external_attr >> 16) & 0o170000 == _SYMLINK_MODE:
            raise IngestionRejected(ARCHIVE_UNSAFE_ENTRY, f"{name!r}: symbolic link entry")

        leaf = PurePosixPath(name).name
        # Archive utilities on macOS add a parallel `__MACOSX/` tree of
        # resource forks. They are not project content and registering them
        # would double every package's file count.
        if name.startswith("__MACOSX/") or leaf.startswith("._") or leaf == ".DS_Store":
            skipped.append({"name": name, "reason": "ARCHIVE_METADATA"})
            continue
        if not leaf:
            skipped.append({"name": name, "reason": "NO_FILENAME"})
            continue
        if info.file_size == 0:
            skipped.append({"name": name, "reason": "EMPTY_ENTRY"})
            continue

        if info.file_size > max_entry:
            raise IngestionRejected(
                ARCHIVE_EXPANSION_LIMIT,
                f"{name!r} declares {info.file_size} bytes, over the per-entry limit",
            )
        total += info.file_size
        if total > max_total:
            raise IngestionRejected(
                ARCHIVE_EXPANSION_LIMIT,
                f"declared contents exceed {max_total} bytes",
            )

        entry = ArchiveEntry(
            name=name,
            filename=leaf,
            directory=str(PurePosixPath(name).parent) if PurePosixPath(name).parent != PurePosixPath(".") else "",
            declared_size=info.file_size,
            compressed_size=info.compress_size,
        )
        if entry.compression_ratio > max_ratio:
            raise IngestionRejected(
                ARCHIVE_EXPANSION_LIMIT,
                f"{name!r} compresses {entry.compression_ratio:.0f}:1, over the ratio limit",
            )
        entries.append(entry)

    return ArchiveInspection(
        entries=tuple(entries), skipped=tuple(skipped), total_declared_size=total,
    )


def open_archive(path) -> zipfile.ZipFile:
    """Open a ZIP, turning every way it can be unreadable into one error."""
    try:
        return zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise IngestionRejected(ARCHIVE_CORRUPTED, str(exc)) from exc


def read_entry(archive: zipfile.ZipFile, entry: ArchiveEntry, *, limit: int) -> bytes:
    """Read one entry, refusing to exceed `limit` however the header reads.

    Bounded independently of `entry.declared_size` because that number came
    from the archive. An entry that declares a kilobyte and streams a gigabyte
    is the classic form of this attack, and the ceiling that matters is the one
    applied to the bytes actually produced.
    """
    try:
        with archive.open(entry.name) as handle:
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining > 0:
                chunk = handle.read(min(READ_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                chunks.append(chunk)
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError) as exc:
        raise IngestionRejected(ARCHIVE_CORRUPTED, f"{entry.name!r}: {exc}") from exc

    payload = b"".join(chunks)
    if len(payload) > limit:
        raise IngestionRejected(
            ARCHIVE_EXPANSION_LIMIT,
            f"{entry.name!r} produced more bytes than it declared",
        )
    return payload
