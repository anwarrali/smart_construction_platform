"""Storage abstraction for private artefacts (IFC sources, geometry, voice audio).

Development runs on the local filesystem. Moving to Cloudflare R2 or any other
S3-compatible service means adding one class that satisfies `PrivateStorage`
and setting PRIVATE_STORAGE_BACKEND — no IFC, geometry or voice code changes.

`local_path` is the contract that makes that possible: ifcopenshell and the
geometry pipeline need a real file on disk, so a remote backend materialises the
object into a temporary file and reports it here, while the local backend simply
returns the file it already has.
"""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol, runtime_checkable

from fastapi import UploadFile

from app.core.config import settings


@runtime_checkable
class PrivateStorage(Protocol):
    """Everything the platform needs from private object storage."""

    async def save(self, file: UploadFile, category: str) -> tuple[str, int]:
        """Persist an upload and return (storage_key, size_in_bytes)."""

    def exists(self, key: str) -> bool: ...

    def size(self, key: str) -> int | None: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        """A real filesystem path for READING with tools that cannot take a stream."""
        ...

    @contextmanager
    def writable_local_path(self, key: str) -> Iterator[Path]:
        """A real filesystem path to WRITE to; the result is committed on clean exit.

        Separate from `local_path` on purpose: a remote backend has to upload the
        produced file, and a reader-only contract would drop it silently.
        """
        ...

    def put_local_file(self, source: Path, key: str) -> int:
        """Store a file produced on disk under `key`."""


class LocalFilesystemStorage:
    """Filesystem-backed implementation rooted at settings.PRIVATE_UPLOAD_DIR."""

    backend_name = "local"

    def _resolve(self, key: str) -> Path:
        root = Path(settings.PRIVATE_UPLOAD_DIR).resolve()
        target = (root / key).resolve()
        # Reject traversal: the key must land strictly inside the root.
        if root == target or root not in target.parents:
            raise ValueError("Invalid private storage key")
        return target

    async def save(self, file: UploadFile, category: str) -> tuple[str, int]:
        from app.services.file_storage import save_private_upload

        return await save_private_upload(file, category)

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).exists()
        except ValueError:
            return False

    def size(self, key: str) -> int | None:
        try:
            target = self._resolve(key)
            return target.stat().st_size if target.exists() else None
        except ValueError:
            return None

    def open(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)
        except ValueError:
            return

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        yield self._resolve(key)

    @contextmanager
    def writable_local_path(self, key: str) -> Iterator[Path]:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # The local backend writes straight into place; there is nothing to upload.
        yield target

    def put_local_file(self, source: Path, key: str) -> int:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target:
            shutil.move(str(source), target)
        return target.stat().st_size


_BACKENDS = {"local": LocalFilesystemStorage}


def _build() -> PrivateStorage:
    name = (settings.PRIVATE_STORAGE_BACKEND or "local").strip().lower()
    factory = _BACKENDS.get(name)
    if not factory:
        raise ValueError(
            f"Unsupported PRIVATE_STORAGE_BACKEND '{name}'. Available: {', '.join(sorted(_BACKENDS))}"
        )
    return factory()


private_storage: PrivateStorage = _build()
