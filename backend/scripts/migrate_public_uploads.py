"""Move the four sensitive upload categories out of the public tree.

Run once, after `alembic upgrade head`, on any deployment that has data
predating the withdrawal of the public `/uploads` mount:

    docker compose exec backend python scripts/migrate_public_uploads.py --dry-run
    docker compose exec backend python scripts/migrate_public_uploads.py

## What it does

For every `Document` and `Attachment` row whose bytes still sit under
`UPLOAD_DIR`, it copies the file into `PRIVATE_UPLOAD_DIR` under the same
relative key, points the row at it, and only then removes the public copy.

## Why a script and not a migration

Three reasons, and the first is sufficient on its own:

  * **A file move is not transactional.** Alembic runs inside a database
    transaction it can roll back; the filesystem is not part of it. A migration
    that moved bytes and then failed would leave the database rolled back and
    the files gone.
  * **It has to be re-runnable.** A half-finished run is the normal case for
    anything touching thousands of files — an operator interrupts it, a volume
    fills up. Every step below is idempotent, so running it again finishes the
    job rather than corrupting what already succeeded.
  * **The two volumes may not both be mounted** in whatever container happens to
    run migrations. This fails loudly on that; a migration would fail silently
    partway.

## Ordering, and why copy-then-delete

Copy, commit the row, *then* unlink the original. If the process dies between
the copy and the commit, the next run finds the public file still present and
redoes the copy — wasteful, harmless. Had it moved first and committed second, a
death in that same window would leave a row pointing at a location whose bytes
were already gone, which is unrecoverable without a backup.

A row whose public file is already missing is reported and left alone. Inventing
a `storage_key` for bytes that do not exist would turn a visible 404 into a row
that claims to be fine.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

# Run as a script rather than a module (`python scripts/migrate_public_uploads.py`),
# so the backend root is not on the path yet. Added here rather than requiring a
# `-m` invocation, because the command in this module's docstring is the one an
# operator will actually paste.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Imported for the side effect of registering every mapper before a query runs.
from app import models  # noqa: E402,F401
from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.attachment import Attachment  # noqa: E402
from app.models.document import Document  # noqa: E402

PRIVATE_SCHEME = "private://"

#: Schemes that mean "these bytes were never in the public tree".
#:
#: `private://` is what this script writes. `protected://` predates it: voice
#: command and voice analysis attachments have always been stored under
#: `PRIVATE_UPLOAD_DIR` and carry a synthetic URL naming the owning record
#: rather than a location (see `api/voice.py` and `api/ai.py`). A first draft of
#: this script skipped only `private://` and reported all 130 of them as
#: "missing", which read as data loss and was nothing of the kind — they were
#: already safe, and the report was wrong rather than the data.
ALREADY_PRIVATE_SCHEMES = (PRIVATE_SCHEME, "protected://")


def public_relative_path(file_url: str | None) -> str | None:
    """The path under `UPLOAD_DIR` a legacy `file_url` refers to, if any.

    Returns None for a row whose bytes are already out of the public tree, so
    the caller can skip it without a second predicate.
    """
    if not file_url or file_url.startswith(ALREADY_PRIVATE_SCHEMES):
        return None
    path_part = urlparse(file_url).path if "://" in file_url else file_url
    path_part = unquote(path_part)
    marker = "/uploads/"
    relative = path_part.split(marker, 1)[1] if marker in path_part else path_part.lstrip("/")
    return relative or None


def _within(root: Path, candidate: Path) -> bool:
    """Guard against a stored value that would escape its root."""
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def migrate_row(row, *, dry_run: bool) -> str:
    """Move one row's bytes into private storage. Returns an outcome word."""
    relative = public_relative_path(row.file_url)
    if relative is None:
        return "already-private"

    public_root = Path(settings.UPLOAD_DIR).resolve()
    private_root = Path(settings.PRIVATE_UPLOAD_DIR).resolve()
    source = public_root / relative
    target = private_root / relative

    if not _within(public_root, source) or not _within(private_root, target):
        return "unsafe-path"

    already_there = target.exists()
    if not source.exists() and not already_there:
        return "missing"

    if dry_run:
        return "would-move"

    if not already_there:
        target.parent.mkdir(parents=True, exist_ok=True)
        # copy2 preserves mtime, which is the only file metadata anything here
        # reads. The original is removed after the row is committed, below.
        shutil.copy2(source, target)

    row.storage_key = relative
    row.file_url = f"{PRIVATE_SCHEME}{relative}"
    return "moved"


def run(*, dry_run: bool) -> int:
    session = SessionLocal()
    counts: dict[str, int] = {}
    moved_sources: list[Path] = []
    public_root = Path(settings.UPLOAD_DIR).resolve()

    try:
        documents = session.query(Document).all()
        # Avatars are deliberately excluded: they remain public and are served
        # from their own narrow mount. Only the four sensitive categories move.
        attachments = session.query(Attachment).all()

        for row in [*documents, *attachments]:
            relative = public_relative_path(row.file_url)
            outcome = migrate_row(row, dry_run=dry_run)
            counts[outcome] = counts.get(outcome, 0) + 1
            if outcome == "moved" and relative:
                moved_sources.append(public_root / relative)
            if outcome in {"missing", "unsafe-path"}:
                print(f"  {outcome}: {type(row).__name__} {row.id} -> {row.file_url}")

        if dry_run:
            session.rollback()
        else:
            session.commit()
            # Only now is it safe to drop the public copies: the rows that
            # depend on the new location are durable.
            for source in moved_sources:
                source.unlink(missing_ok=True)
    finally:
        session.close()

    print("\nResult:")
    for outcome in sorted(counts):
        print(f"  {outcome}: {counts[outcome]}")
    failures = counts.get("missing", 0) + counts.get("unsafe-path", 0)
    if failures:
        print(
            f"\n{failures} row(s) could not be migrated. They keep their old value and "
            "their download endpoint will report the file as unavailable, which is "
            "accurate — the bytes are not where the row says they are."
        )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would move without copying anything or writing to the database.",
    )
    args = parser.parse_args()
    print(f"Public root : {settings.UPLOAD_DIR}")
    print(f"Private root: {settings.PRIVATE_UPLOAD_DIR}")
    print(f"Mode        : {'dry run' if args.dry_run else 'apply'}\n")
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
