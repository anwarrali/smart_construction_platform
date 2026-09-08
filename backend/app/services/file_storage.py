import re
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from app.core.config import settings
from app.services.file_intelligence import identify_format
from urllib.parse import urlparse

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SIGNATURE_VERIFIED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".webp", ".wav", ".ogg", ".m4a", ".mp3", ".dwg", ".ifc",
    # Added with the unified ingestion pipeline. Both are signature-checked
    # below: `.zip` must start with the ZIP local-file-header magic, and `.dxf`
    # must be either the binary DXF sentinel or readable text, which is what an
    # ASCII DXF is. Neither is accepted on its extension alone.
    ".zip", ".dxf",
}

UPLOAD_RULES = {
    "attachments": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".pdf": {"application/pdf"}, ".doc": {"application/msword"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
        ".xls": {"application/vnd.ms-excel"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
    },
    "documents": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".pdf": {"application/pdf"}, ".doc": {"application/msword"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"},
        ".xls": {"application/vnd.ms-excel"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"},
        ".txt": {"text/plain"},
        ".dwg": {"application/acad", "application/dwg", "image/vnd.dwg", "application/octet-stream"},
    },
    "site-reports": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".pdf": {"application/pdf"},
    },
    "field-evidence": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".webp": {"image/webp"},
    },
    "avatars": {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".webp": {"image/webp"},
    },
    "audio": {
        ".mp3": {"audio/mpeg"}, ".wav": {"audio/wav", "audio/x-wav"},
        ".m4a": {"audio/mp4", "audio/x-m4a"}, ".ogg": {"audio/ogg"},
        ".mp4": {"audio/mp4", "video/mp4"}, ".webm": {"audio/webm", "video/webm"},
        ".mpeg": {"audio/mpeg"}, ".mpga": {"audio/mpeg"},
    },
    "ifc": {
        ".ifc": {"application/x-step", "application/step", "text/plain", "application/octet-stream"},
    },
    # The unified ingestion pipeline. It is the union of what the platform
    # already accepts across `documents` and `ifc`, plus the two things a
    # design delivery actually arrives as and no existing category allowed:
    # a ZIP package and a DXF drawing. Deliberately a separate entry rather
    # than a widening of `documents` — nothing that uploads a document today
    # should start accepting archives because ingestion needed to.
    #
    # `application/octet-stream` appears throughout because browsers and
    # site-office clients send it for anything they do not recognise. It is
    # never accepted on its own: every extension listed here is in
    # SIGNATURE_VERIFIED_EXTENSIONS, so the magic bytes still have to agree.
    "ingest": {
        ".pdf": {"application/pdf", "application/octet-stream"},
        ".doc": {"application/msword", "application/octet-stream"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  "application/zip", "application/octet-stream"},
        ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  "application/zip", "application/octet-stream"},
        ".txt": {"text/plain"},
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".png": {"image/png"},
        ".webp": {"image/webp"},
        ".dwg": {"application/acad", "application/dwg", "image/vnd.dwg", "application/octet-stream"},
        ".dxf": {"application/dxf", "image/vnd.dxf", "text/plain", "application/octet-stream"},
        ".ifc": {"application/x-step", "application/step", "text/plain", "application/octet-stream"},
        ".zip": {"application/zip", "application/x-zip-compressed", "application/octet-stream"},
    },
}


#: Which detected format satisfies a claimed extension. Several extensions map
#: to the same container format on purpose — a .docx and an .xlsx are both ZIP
#: archives and magic bytes cannot separate them, so the extension is accepted
#: as the discriminator here exactly as it always was.
EXTENSION_FORMATS: dict[str, set[str]] = {
    ".jpg": {"JPEG"}, ".jpeg": {"JPEG"}, ".png": {"PNG"}, ".pdf": {"PDF"},
    ".docx": {"DOCX", "ZIP_CONTAINER"}, ".xlsx": {"XLSX", "ZIP_CONTAINER"},
    ".doc": {"DOC", "OLE2_CONTAINER"}, ".xls": {"XLS", "OLE2_CONTAINER"},
    ".webp": {"WEBP"}, ".wav": {"WAV"}, ".ogg": {"OGG"},
    ".m4a": {"M4A", "MP4_CONTAINER"}, ".mp4": {"MP4", "MP4_CONTAINER"},
    ".webm": {"WEBM"}, ".mpeg": {"MP3"}, ".mpga": {"MP3"}, ".mp3": {"MP3"},
    ".dwg": {"DWG"}, ".ifc": {"IFC"},
    # A plain `.zip` must be a ZIP container and nothing else. It is
    # deliberately *not* allowed to be DOCX or XLSX: those have their own
    # extensions, and letting a `.zip` resolve to an Office format would let a
    # package upload smuggle in a file the archive walker would then not open.
    ".zip": {"ZIP_CONTAINER"},
    # A DXF is either the binary form, which has a sentinel, or an ASCII text
    # file, which by definition has no signature. TEXT is therefore accepted
    # here for the same reason `.txt` is accepted on its name.
    ".dxf": {"DXF", "TEXT"},
}


def _matches_signature(extension: str, content: bytes) -> bool:
    """Does the content match the extension it claims to be?

    The magic-byte knowledge lives in `file_intelligence.FORMAT_SIGNATURES`, so
    the upload gate and the classifier can never end up disagreeing about the
    same bytes. This function still answers only the security question: is this
    file allowed to call itself `.pdf`?

    `.txt` has no signature — any byte sequence is arguably text — so it stays
    the one extension accepted on its name alone, as before.
    """
    if extension == ".txt":
        return True
    allowed = EXTENSION_FORMATS.get(extension)
    if not allowed:
        return False
    return identify_format(content, extension) in allowed

async def save_upload(file: UploadFile, category: str) -> tuple[str, int]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "file").name)
    extension = Path(safe_name).suffix.lower()
    rules = UPLOAD_RULES.get(category)
    mime_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    mime_is_allowed = (
        rules is not None
        and extension in rules
        and (
            mime_type in rules[extension]
            or (mime_type == "application/octet-stream" and extension in SIGNATURE_VERIFIED_EXTENSIONS)
        )
    )
    if not mime_is_allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported file type for {category}")
    first_chunk = await file.read(1024 * 1024)
    if not first_chunk:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if not _matches_signature(extension, first_chunk):
        raise HTTPException(status_code=415, detail="File content does not match its extension")
    relative = Path(category) / f"{uuid.uuid4()}_{safe_name}"
    target = Path(settings.UPLOAD_DIR).resolve() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as output:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds the 25 MB limit")
                output.write(chunk)
                chunk = await file.read(1024 * 1024)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return f"{settings.BACKEND_URL.rstrip('/')}/uploads/{relative.as_posix()}", size


def _private_size_limit(category: str) -> int:
    """The byte ceiling for one private-storage category.

    A table rather than the inline conditional it replaces, because there are
    now three answers instead of two and a third `if` on that line would be the
    point at which nobody can see what the limits are.
    """
    if category == "ifc":
        return settings.IFC_MAX_FILE_MB * 1024 * 1024
    if category == "ingest":
        return settings.INGESTION_MAX_FILE_MB * 1024 * 1024
    return MAX_UPLOAD_BYTES


async def save_private_upload(file: UploadFile, category: str) -> tuple[str, int]:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(file.filename or "file").name)
    extension = Path(safe_name).suffix.lower()
    rules = UPLOAD_RULES.get(category)
    mime_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    allowed = (
        rules is not None
        and extension in rules
        and (
            mime_type in rules[extension]
            or (mime_type == "application/octet-stream" and extension in SIGNATURE_VERIFIED_EXTENSIONS)
        )
    )
    if not allowed:
        raise HTTPException(status_code=415, detail=f"Unsupported file type for {category}")
    first_chunk = await file.read(1024 * 1024)
    if not first_chunk:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if not _matches_signature(extension, first_chunk):
        raise HTTPException(status_code=415, detail="File content does not match its extension")
    storage_key = (Path(category) / f"{uuid.uuid4()}_{safe_name}").as_posix()
    target = resolve_private_storage_key(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as output:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                limit = _private_size_limit(category)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {limit // (1024 * 1024)} MB limit")
                output.write(chunk)
                chunk = await file.read(1024 * 1024)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return storage_key, size

def delete_upload(file_url: str | None) -> None:
    if not file_url:
        return
    marker = "/uploads/"
    path = urlparse(file_url).path
    if marker not in path:
        return
    relative = path.split(marker, 1)[1]
    root = Path(settings.UPLOAD_DIR).resolve()
    target = (root / relative).resolve()
    if root == target or root not in target.parents:
        return
    target.unlink(missing_ok=True)


def resolve_storage_key(storage_key: str) -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    target = (root / storage_key).resolve()
    if root == target or root not in target.parents:
        raise ValueError("Invalid storage key")
    return target


def resolve_private_storage_key(storage_key: str) -> Path:
    root = Path(settings.PRIVATE_UPLOAD_DIR).resolve()
    target = (root / storage_key).resolve()
    if root == target or root not in target.parents:
        raise ValueError("Invalid private storage key")
    return target
