"""Streaming a private object back to a caller, in one implementation.

This code was written for IFC downloads and lived in `app/api/ifc.py`; it is
moved here unchanged so the unified file endpoint uses the same one. The
reasoning that produced it is security-relevant enough to keep verbatim, and
duplicating it for a second endpoint is how one of the two copies eventually
stops escaping a filename.

`_stored_file_response` used to hand `FileResponse` a path obtained from
`private_storage.local_path(...)` *inside* a `with` block, and that is correct
only by accident of the local backend. Starlette opens and reads the file after
the handler has returned — by which time the context manager has already
exited. `LocalFilesystemStorage.local_path` yields the real file and cleans up
nothing, so the path stays valid and the download works. The moment a backend
materialises the object into a temporary file and removes it on exit — the
exact contract `private_storage` documents for the planned R2/S3 move — every
download would return a path to a file that no longer exists, failing in
production while passing every local test.

Reading through `open()` makes the response independent of where the object
actually lives, and streaming in chunks keeps a half-gigabyte model off the
heap. The filesystem path never leaves the server either way.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.services.private_storage import private_storage

#: Anything that would let a filename break out of a quoted header value.
_HEADER_UNSAFE = re.compile(r'[\\"\r\n]')
#: Bytes per read while streaming a stored object back to the caller.
DOWNLOAD_CHUNK_BYTES = 64 * 1024


def attachment_headers(filename: str, size: int | None) -> dict[str, str]:
    """`Content-Disposition` for a download, in both the forms RFC 6266 wants.

    Composed here rather than delegated to `FileResponse`, which is no longer
    used. An ASCII `filename` every client understands, plus `filename*`
    carrying the real name for those that read it, so an Arabic model name
    survives without breaking older clients.

    The substitution is the header-injection defence: a filename containing a
    carriage return would otherwise let an uploader append headers of their own
    choosing to every download response.
    """
    safe = _HEADER_UNSAFE.sub("_", filename).strip() or "download"
    ascii_name = safe.encode("ascii", "ignore").decode("ascii").strip() or "download"
    quoted = quote(safe, safe="")
    disposition = f'attachment; filename="{ascii_name}"'
    if quoted != ascii_name:
        disposition += f"; filename*=utf-8''{quoted}"
    headers = {"Content-Disposition": disposition}
    if size is not None:
        headers["Content-Length"] = str(size)
    return headers


def stored_file_response(storage_key: str, *, filename: str,
                         media_type: str) -> StreamingResponse:
    """Stream a private object to the caller, through the storage abstraction."""
    try:
        handle = private_storage.open(storage_key)
    except (OSError, ValueError) as exc:
        # Lost between the existence check and this line, or an unusable key.
        raise HTTPException(status_code=404, detail="Stored file is unavailable") from exc

    def stream():
        try:
            while chunk := handle.read(DOWNLOAD_CHUNK_BYTES):
                yield chunk
        finally:
            handle.close()

    return StreamingResponse(
        stream(), media_type=media_type,
        headers=attachment_headers(filename, private_storage.size(storage_key)),
    )
